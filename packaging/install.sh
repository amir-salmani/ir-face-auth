#!/usr/bin/env bash
# Install the PAM verification helper. Does NOT enable face auth anywhere:
# it only puts the pieces in place and creates an isolated test service.
# Enabling for sudo is a separate, deliberate step (see enable-sudo.sh).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNTIME_DIR=/usr/local/lib/irfa
STORE_DIR=/var/lib/irfa
SERVICE_USER=irfa

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }

echo "==> service user"
if ! getent passwd "$SERVICE_USER" >/dev/null; then
  # No login shell, no home, no password: this account exists solely to own
  # the camera-facing process and must never be usable interactively.
  useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
  echo "    created $SERVICE_USER"
fi
usermod -aG video "$SERVICE_USER"
echo "    $SERVICE_USER in groups: $(id -nG "$SERVICE_USER" | tr ' ' ',')"

echo "==> runtime code (root-owned; root must not exec user-writable code)"
rm -rf "$RUNTIME_DIR"
install -d -o root -g root -m 0755 "$RUNTIME_DIR"
cp -r "$REPO/src/irfa" "$RUNTIME_DIR/irfa"
cp -r "$REPO/models" "$RUNTIME_DIR/models"
find "$RUNTIME_DIR" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
chown -R root:root "$RUNTIME_DIR"
chmod -R go-w "$RUNTIME_DIR"

install -o root -g root -m 0755 "$REPO/packaging/irfa-pam-verify" /usr/local/bin/irfa-pam-verify
echo "    installed /usr/local/bin/irfa-pam-verify"

echo "==> enrollment store"
# 0700 root-only: these embeddings are a credential. The unprivileged camera
# child must not be able to read them, which is what makes the split meaningful.
install -d -o root -g root -m 0700 "$STORE_DIR"

echo "==> isolated PAM test service"
# A service nothing on the system consumes, so a broken rule here cannot affect
# login, sudo, or the display manager.
cat > /etc/pam.d/irfa-test <<'EOF'
# Isolated test service for ir-face-auth. Nothing depends on this file.
auth    sufficient  pam_exec.so quiet /usr/local/bin/irfa-pam-verify
auth    required    pam_deny.so
account required    pam_permit.so
EOF
chmod 0644 /etc/pam.d/irfa-test
echo "    wrote /etc/pam.d/irfa-test"

echo
echo "Installed. Face auth is NOT enabled for any real service."
echo "Next: enroll into the system store, then test in isolation:"
echo "  sudo $REPO/packaging/enroll-system.sh \$USER"
echo "  pamtester irfa-test \$USER authenticate"
