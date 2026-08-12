#!/usr/bin/env bash
# Make sudo actually authenticate by removing NOPASSWD from the %sudo rule,
# so that the face-auth PAM rule has something to do.
#
# A malformed /etc/sudoers breaks sudo for everyone, immediately and totally.
# Two independent protections, because a rollback that needs sudo to run is
# not a rollback:
#
#   1. The candidate file is validated with `visudo -c` and only installed if
#      it parses. A syntax error never reaches /etc/sudoers at all.
#   2. A detached root process restores the original unless confirmed within
#      the grace period, covering the case where the file parses but the
#      resulting policy is wrong.
set -euo pipefail

SUDOERS=/etc/sudoers
BACKUP=/etc/sudoers.irfa-backup
KEEP_FLAG=/run/irfa-keep-sudoers
GRACE="${GRACE:-180}"

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }

if [[ "${1:-}" == "--restore" ]]; then
  [[ -f "$BACKUP" ]] || { echo "no backup at $BACKUP" >&2; exit 1; }
  visudo -c -f "$BACKUP" >/dev/null
  install -m 0440 -o root -g root "$BACKUP" "$SUDOERS"
  rm -f "$KEEP_FLAG"
  echo "restored $SUDOERS from backup"
  exit 0
fi

grep -qE '^\s*%sudo\s+.*NOPASSWD' "$SUDOERS" || {
  echo "no %sudo NOPASSWD rule found; nothing to change"
  exit 0
}

cp "$SUDOERS" "$BACKUP"
chmod 0440 "$BACKUP"

TMP="$(mktemp /tmp/sudoers.irfa.XXXXXX)"
trap 'rm -f "$TMP"' EXIT
sed -E 's/^(\s*%sudo\s+ALL=\(ALL:ALL\)\s+)NOPASSWD:ALL\s*$/\1ALL/' "$SUDOERS" > "$TMP"

if ! diff -q "$SUDOERS" "$TMP" >/dev/null; then
  echo "proposed change:"
  diff "$SUDOERS" "$TMP" | sed 's/^/    /' || true
else
  echo "rule did not match the expected pattern; refusing to guess" >&2
  exit 1
fi

# Gate 1: never install a file that does not parse.
if ! visudo -c -f "$TMP" >/dev/null 2>&1; then
  echo "VALIDATION FAILED -- /etc/sudoers left untouched" >&2
  visudo -c -f "$TMP" || true
  exit 1
fi
echo "visudo validation passed"

rm -f "$KEEP_FLAG"
# Gate 2: arm the rollback before installing.
setsid nohup bash -c "
  for _ in \$(seq $GRACE); do
    [ -f '$KEEP_FLAG' ] && exit 0
    sleep 1
  done
  install -m 0440 -o root -g root '$BACKUP' '$SUDOERS'
  logger -t irfa-pam 'grace expired; rolled back /etc/sudoers'
" >/dev/null 2>&1 < /dev/null &
echo "rollback armed: /etc/sudoers reverts in ${GRACE}s unless confirmed"

install -m 0440 -o root -g root "$TMP" "$SUDOERS"
echo "installed. sudo now requires authentication."
echo "confirm with:  sudo touch $KEEP_FLAG"
