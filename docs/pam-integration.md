# PAM integration

> **Read this section before running anything here.** A broken
> `/etc/pam.d/<service>` can lock you out of the tool you would need to repair
> it. Everything below is designed around that hazard, but the design only
> helps if you follow the order.

## Order of operations

1. `sudo packaging/install.sh` — installs the pieces, enables nothing
2. `sudo packaging/enroll-system.sh $USER` — root-owned enrollment
3. `sudo pamtester irfa-test $USER authenticate` — **verify in isolation first**
4. `sudo packaging/enable.sh <service>` — one service at a time
5. Confirm within the grace period, or it rolls back automatically

Step 3 is not optional. `/etc/pam.d/irfa-test` is consumed by nothing, so a
failure there costs you nothing.

## How the rollback works

Editing a PAM file has a bootstrapping problem: if the edit breaks
authentication, you need privileges to fix it, and you no longer have them.

So `enable.sh` arms a detached root process **before** making any change. That
process holds the original file and restores it unless you confirm, within a
grace period, that the system still works:

```bash
sudo packaging/enable.sh sudo --grace 300
# ... verify in another terminal that sudo still works ...
sudo touch /run/irfa-keep-sudo          # confirm
```

Confirming requires working privileges. **A broken system cannot disarm its own
safety net.** Do nothing and the original file comes back.

`setsid` detaches the watcher, so closing your terminal does not take the
safety net with it.

## Which services

| Service | Covers | Risk if broken |
|---|---|---|
| `polkit-1` | GUI "Authentication required" dialogs | Low — degrades to a password dialog |
| `sudo` | Terminal privilege escalation | Medium — check for other admin accounts first |
| `gdm-password` | GDM login **and** lock screen | High — but a TTY (`Ctrl+Alt+F3`) bypasses GDM entirely |

Start with `polkit-1`. Do `gdm-password` last.

### Why never `common-auth`

`enable.sh` refuses to touch it. `common-auth` is included by GDM, sudo, ssh,
polkit, `su`, `login` and cron simultaneously — one mistake there breaks every
authentication path on the machine at once. Editing individual services keeps
the blast radius to one thing.

### Services in `/usr/lib/pam.d`

Some services (notably `polkit-1` on recent distros) ship their config in the
vendor directory with no `/etc` copy. `enable.sh` materialises an override into
`/etc/pam.d/` and records that it did so, so `--disable` removes the override
and restores the vendor default rather than leaving a stale copy behind.

## Does your sudo even authenticate?

```bash
sudo grep -E "^\s*%sudo" /etc/sudoers
```

If that shows `NOPASSWD:ALL`, sudo never authenticates and a face rule there
would **never execute**. Check before concluding the integration failed.

To make sudo authenticate:

```bash
sudo packaging/require-sudo-password.sh
```

This changes `%sudo ALL=(ALL:ALL) NOPASSWD:ALL` → `ALL`, with two independent
protections: the candidate file must pass `visudo -c` before it is installed at
all, and the same rollback watcher covers the case where it parses but the
policy is wrong.

> **Before you run it:** confirm you know your password, and check whether any
> automation depends on passwordless sudo. If you are the only member of the
> `sudo` group and root is locked — common on Ubuntu — a broken sudo means
> booting to recovery.

## Testing correctly

```bash
sudo -k                                  # clear the timestamp
sudo -S true < /dev/null && echo "authenticated by face"
```

Closing stdin means no password *could* be supplied, so success proves the face
rule carried it.

**Do not use `sudo -n` for this.** With `-n`, sudo errors out with "interactive
authentication is required" *before* running the auth stack, so it tests
nothing and looks like a failure.

Watch what actually happened:

```bash
sudo journalctl -t irfa-pam -f
```

```
irfa: accepted amir: 6/6 frames, best 0.853
irfa: denied amir: 1/6 frames, best 0.31
```

## Rule semantics

```
auth    sufficient  pam_exec.so quiet /usr/local/bin/irfa-pam-verify
@include common-auth
```

`sufficient` means success short-circuits the stack, and **any** failure falls
through to the next rule — the normal password path. Face auth can only ever
*add* a way in; it can never block one. It is never `required` or `requisite`,
and a contribution making it so will be rejected.

### Consequence: the GNOME keyring

Because the rule sits ahead of `pam_gnome_keyring` and short-circuits on
success, a face match means the keyring never receives your password.

- **Lock screen:** harmless — the keyring was unlocked at login.
- **Cold GDM login:** the keyring stays locked and apps needing it will prompt
  separately. Log in with your password when you want it unlocked.

## Undoing everything

```bash
sudo packaging/enable.sh gdm-password --disable
sudo packaging/enable.sh polkit-1 --disable
sudo packaging/enable.sh sudo --disable
sudo packaging/require-sudo-password.sh --restore   # restores NOPASSWD
```

Originals are kept at `/etc/pam.d/.<service>.irfa-backup` and
`/etc/sudoers.irfa-backup`. If you are locked out of a graphical session,
switch to a TTY with `Ctrl+Alt+F3` and run these there.
