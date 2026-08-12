#!/usr/bin/env bash
# Enable or disable face auth for a single PAM service, with automatic rollback.
#
#   enable.sh polkit-1
#   enable.sh gdm-password
#   enable.sh sudo --grace 180
#   enable.sh gdm-password --disable
#
# THE HAZARD
# ----------
# A broken /etc/pam.d/<service> can lock you out of the very tool you would
# need to repair it. On this machine that risk is sharper than usual: amir is
# the only member of the sudo group and root's password is locked, so a
# thoroughly broken sudo means booting to recovery.
#
# So the edit is never made without an armed rollback. A detached root process
# holds the original file and restores it unless the caller confirms, within
# the grace period, that the system still works. Confirming requires working
# privileges, so a broken system cannot disarm its own safety net.
#
# One service at a time, and never common-auth: editing that would change every
# consumer on the machine simultaneously.
set -euo pipefail

SERVICE="${1:-}"
shift || true
GRACE=90
ACTION=enable

while [[ $# -gt 0 ]]; do
  case "$1" in
    --disable) ACTION=disable ;;
    --grace) GRACE="$2"; shift ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
  shift
done

[[ -n "$SERVICE" ]] || { echo "usage: enable.sh <pam-service> [--disable] [--grace N]" >&2; exit 1; }
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }

case "$SERVICE" in
  common-*) echo "refusing to edit $SERVICE: it affects every PAM consumer at once" >&2; exit 1 ;;
esac

PAM_FILE="/etc/pam.d/$SERVICE"
VENDOR_FILE="/usr/lib/pam.d/$SERVICE"
BACKUP="/etc/pam.d/.$SERVICE.irfa-backup"
ABSENT_FLAG="/etc/pam.d/.$SERVICE.irfa-was-absent"
KEEP_FLAG="/run/irfa-keep-$SERVICE"

MARKER='# ir-face-auth: face first, password on any failure'
RULE='auth    sufficient  pam_exec.so quiet /usr/local/bin/irfa-pam-verify'

if [[ "$ACTION" == disable ]]; then
  if [[ -f "$ABSENT_FLAG" ]]; then
    # We created this override; removing it restores the vendor default.
    rm -f "$PAM_FILE" "$ABSENT_FLAG" "$BACKUP"
    echo "removed $PAM_FILE (falls back to $VENDOR_FILE)"
  elif [[ -f "$BACKUP" ]]; then
    cp "$BACKUP" "$PAM_FILE"
    rm -f "$BACKUP"
    echo "restored $PAM_FILE"
  else
    echo "nothing to restore for $SERVICE" >&2
    exit 1
  fi
  rm -f "$KEEP_FLAG"
  exit 0
fi

[[ -x /usr/local/bin/irfa-pam-verify ]] || { echo "helper not installed; run install.sh" >&2; exit 1; }

if [[ -f "$PAM_FILE" ]] && grep -q "irfa-pam-verify" "$PAM_FILE"; then
  echo "already enabled for $SERVICE"
  exit 0
fi

# Materialise an override from the vendor config if there is no /etc copy.
if [[ ! -f "$PAM_FILE" ]]; then
  [[ -f "$VENDOR_FILE" ]] || { echo "no such PAM service: $SERVICE" >&2; exit 1; }
  cp "$VENDOR_FILE" "$PAM_FILE"
  touch "$ABSENT_FLAG"
  echo "created $PAM_FILE from vendor default"
fi

grep -q "@include common-auth" "$PAM_FILE" || {
  echo "$PAM_FILE has no '@include common-auth' to anchor to; refusing to guess" >&2
  exit 1
}

cp "$PAM_FILE" "$BACKUP"
rm -f "$KEEP_FLAG"

# Arm BEFORE editing, detached via setsid so closing this terminal cannot take
# the safety net down with it.
setsid nohup bash -c "
  for _ in \$(seq $GRACE); do
    [ -f '$KEEP_FLAG' ] && exit 0
    sleep 1
  done
  if [ -f '$ABSENT_FLAG' ]; then rm -f '$PAM_FILE' '$ABSENT_FLAG'; else cp '$BACKUP' '$PAM_FILE'; fi
  logger -t irfa-pam 'grace expired; rolled back $PAM_FILE'
" >/dev/null 2>&1 < /dev/null &

echo "rollback armed: $SERVICE reverts in ${GRACE}s unless confirmed"

awk -v marker="$MARKER" -v rule="$RULE" '
  /^@include common-auth/ && !done { print marker; print rule; print ""; done=1 }
  { print }
' "$BACKUP" > "$PAM_FILE"

echo "edited $PAM_FILE"
echo "confirm with:  sudo touch $KEEP_FLAG"
