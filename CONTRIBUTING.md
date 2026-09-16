# Contributing

The most valuable contribution to this project is **not code**. It is data from
hardware I do not own.

## The single most useful thing you can do

This has been developed against exactly one camera: a Chicony `04f2:b7fe` in an
HP Pavilion Plus 14-ew1xxx. Every threshold in the codebase was measured on
that sensor. Whether the strobe pattern, the liveness metrics, or the
recognition thresholds generalise to other Windows Hello cameras is genuinely
unknown.

If you have an IR camera, run this and open a
[hardware report](https://github.com/amir-salmani/ir-face-auth/issues/new?template=hardware-report.yml):

```bash
git clone https://github.com/amir-salmani/ir-face-auth
cd ir-face-auth
./scripts/fetch-models.sh
sudo apt install python3-opencv          # or your distro's equivalent
PYTHONPATH=src python3 -m irfa.cli doctor
```

Paste the output. Even a failure is useful — especially a failure. "No IR
capture device found" on a laptop that has one tells us the sysfs name
detection is too narrow.

## The second most useful thing: attack data

The anti-spoofing claims are reasoned from physics and **have not been tested
against real attacks**. If you are willing to try to break it, please do, and
report what happened:

```bash
PYTHONPATH=src python3 -m irfa.cli enroll --samples 12
PYTHONPATH=src python3 -m irfa.cli collect --label live --samples 40
PYTHONPATH=src python3 -m irfa.cli collect --label spoof-phone --samples 25
PYTHONPATH=src python3 -m irfa.cli collect --label spoof-print --samples 25
PYTHONPATH=src python3 -m irfa.cli analyze
```

`analyze` will tell you plainly if a metric cannot separate live faces from
your attack. **A successful attack is a headline result, not a bug report to be
embarrassed about.** It will be credited and acted on.

Impostor data — two people, one enrolled, the other attempting — is equally
valuable and currently missing entirely.

### Please do not send face images

Open an issue with **numbers**, never photographs. The `collect` command
records only scalar metrics; `.gitignore` excludes `captures/` and `*.npz` so
biometric data cannot be committed by accident. Keep it that way.

## Code contributions

Development setup:

```bash
./scripts/fetch-models.sh
PYTHONPATH=src python3 -m irfa.cli doctor
```

Nothing compiles. If you find yourself adding a dependency that needs a C++
toolchain at install time, stop and reconsider — that choice is precisely why
the incumbent in this space is unbuildable on current distros.

### What review will focus on

This is authentication code, so the bar is different from ordinary software:

- **Does it fail closed?** Every error path must deny.
- **Does it stay `sufficient`?** No change may make face auth able to *block*
  a login. It may only ever add a way in.
- **Does it keep untrusted input out of root?** Camera I/O, image decoding and
  model parsing belong in the unprivileged child. Root does arithmetic on a
  bounded, validated array and nothing else.
- **Can it hang?** Anything in the auth path needs a bound. A stuck camera must
  not freeze every `sudo` on the machine.

See [docs/threat-model.md](docs/threat-model.md) for the reasoning behind these.

### Claims must cite measurements

If a change alters a threshold or asserts a security property, include the data.
"This felt more reliable" is not sufficient for something guarding a login.
Separate the evidence from the conclusion so a reviewer can check the former
independently of the latter.

## Testing PAM changes safely

**Never test against `sudo` or `gdm-password` directly.** The installer creates
an isolated service that nothing on the system consumes:

```bash
sudo pamtester irfa-test $USER authenticate
```

`enable.sh` arms an automatic rollback before every edit and refuses to touch
`common-auth`. If you are changing that script, test it on a VM. A mistake in
it can lock a real person out of a real machine.

## Style

Match the surrounding code. Comments explain **why**, not what — particularly
where a decision looks arbitrary but is protecting against something specific.
Those comments are load-bearing; do not strip them.
