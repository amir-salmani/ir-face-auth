# Installation

## Requirements

| | |
|---|---|
| OS | Linux with a UVC infrared camera (Windows Hello class) |
| Python | 3.9 or newer |
| OpenCV | 4.5.4 or newer, with `FaceDetectorYN` and `FaceRecognizerSF` |
| For PAM integration | `pam_exec.so` (standard on Debian/Ubuntu/Fedora), root access |

Nothing compiles. If an install step is asking you for a C++ compiler,
something has gone wrong.

### Verifying OpenCV

```bash
python3 -c "import cv2; print(cv2.__version__, hasattr(cv2,'FaceDetectorYN'), hasattr(cv2,'FaceRecognizerSF'))"
```

You want a version ≥ 4.5.4 and two `True`s. Install with your distro package
manager, not pip:

```bash
sudo apt install python3-opencv          # Debian / Ubuntu
sudo dnf install python3-opencv          # Fedora
sudo pacman -S python-opencv             # Arch
```

The distro build is compiled against your system interpreter and includes the
DNN support this project needs. Installing `opencv-python` from PyPI as well
puts two OpenCV builds in one process, which causes confusing failures.

## Install

```bash
git clone https://github.com/amir-salmani/ir-face-auth
cd ir-face-auth
./scripts/fetch-models.sh        # ~38MB from OpenCV Zoo
```

Check your hardware is usable before anything else:

```bash
PYTHONPATH=src python3 -m irfa.cli doctor
```

Expected:

```
OK    camera: HP 5MP Camera: HP IR Camera at /dev/video2
OK    models: YuNet + SFace loaded
      frame 1: face score=0.88 response=112.1 falloff=1.53 LIVE
OK    detected a face in 4 captures
```

If this fails, see [hardware.md](hardware.md) — and please
[file a report](https://github.com/amir-salmani/ir-face-auth/issues/new?template=hardware-report.yml), because
failures on hardware I do not own are the most useful data this project can
receive.

## Enrollment

```bash
PYTHONPATH=src python3 -m irfa.cli enroll --samples 12
PYTHONPATH=src python3 -m irfa.cli verify
```

Move your head slightly during enrollment so the samples cover a range of
angles. Samples failing liveness are discarded automatically.

Embeddings are written to `~/.local/share/irfa/<user>.npz`, mode `0600`.

> **These are a credential.** Anyone who can write that file can enrol their
> own face as you. `.gitignore` excludes `*.npz` so they cannot be committed by
> accident.

## System installation

Only needed for PAM integration. See [pam-integration.md](pam-integration.md)
for what this enables and how to undo it.

```bash
sudo packaging/install.sh                 # helper, service user, isolated test service
sudo packaging/enroll-system.sh $USER     # promote enrollment to the root-owned store
sudo pamtester irfa-test $USER authenticate
```

`install.sh` deliberately **does not enable face auth anywhere.** It installs
the pieces and creates `/etc/pam.d/irfa-test`, a service nothing on the system
consumes, so you can verify everything works before any real service depends on
it.

What it creates:

| Path | Owner | Purpose |
|---|---|---|
| `/usr/local/lib/irfa/` | root | Runtime code and models |
| `/usr/local/bin/irfa-pam-verify` | root | The PAM helper |
| `/var/lib/irfa/` | root, `0700` | Enrollment store |
| user `irfa` | — | Unprivileged, `video` group, no shell |
| `/etc/pam.d/irfa-test` | root | Isolated test service |

Code is copied out of your checkout on purpose: root must never execute code
from a path the authenticating user can write, or face auth becomes a
privilege-escalation path instead of a protection.

## Uninstall

Disable any enabled services first — see
[pam-integration.md](pam-integration.md#undoing-everything) — then:

```bash
sudo rm -rf /usr/local/lib/irfa /usr/local/bin/irfa-pam-verify
sudo rm -rf /var/lib/irfa                 # deletes enrolled embeddings
sudo rm -f /etc/pam.d/irfa-test
sudo userdel irfa
rm -rf ~/.local/share/irfa                # your development enrollment
```
