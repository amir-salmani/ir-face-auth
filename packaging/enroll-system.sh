#!/usr/bin/env bash
# Promote a user's development enrollment into the root-owned system store.
set -euo pipefail

USERNAME="${1:-}"
STORE_DIR=/var/lib/irfa
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
[[ -n "$USERNAME" ]] || { echo "usage: enroll-system.sh <username>" >&2; exit 1; }

HOME_DIR="$(getent passwd "$USERNAME" | cut -d: -f6)"
SRC="$HOME_DIR/.local/share/irfa/$USERNAME.npz"
DEST="$STORE_DIR/$USERNAME.npz"

[[ -f "$SRC" ]] || { echo "no enrollment at $SRC -- run 'irfa enroll' first" >&2; exit 1; }

install -d -o root -g root -m 0700 "$STORE_DIR"
install -o root -g root -m 0600 "$SRC" "$DEST"
echo "enrolled $USERNAME -> $DEST"
echo
# Worth being explicit about: the source file lives in the user's own home and
# is therefore user-writable. That is acceptable here because the user is
# enrolling their own face for their own account, but it means the system store
# is only as trustworthy as the account it was copied from. A hardened
# deployment would capture enrollment under root control instead.
echo "note: copied from a user-writable path; see the comment in this script."
