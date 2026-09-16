# Hardware

## Reference hardware

Everything in this project was measured on one machine. Treat every constant as
calibrated for it until someone reports otherwise.

| | |
|---|---|
| Laptop | HP Pavilion Plus 14-ew1xxx |
| Camera | Chicony `04f2:b7fe`, "HP 5MP Camera" / "HP IR Camera" |
| IR node | `/dev/video2`, 8-bit greyscale, 640×360 |
| OS | Ubuntu 26.04 LTS, kernel 7.0.0-29, Python 3.14.4, OpenCV 4.10.0 |

The RGB and IR sensors are two USB interfaces of a single device (`1.0` and
`1.2`), each exposing a capture node and a metadata node.

## "My IR camera returns black frames"

This is the most common report about Windows Hello cameras on Linux, and it is
usually **not** a broken emitter.

The emitter strobes at half the frame rate. A single-frame grab lands on an
ambient frame half the time:

```python
# Misleading — one frame, 50% chance of black:
cap.read()                      # mean 0.002  -> "the emitter is dead"

# Honest — look at the sequence:
[round(float(cap.read()[1].mean()),1) for _ in range(20)]
# [42.9, 0.5, 43.0, 0.6, 42.8, 0.7, 43.0, 0.8, ...]
```

Before concluding your emitter needs coaxing, log 20–30 consecutive frames. If
they alternate, your emitter is working and no configuration tool is needed.

This matters because the usual next step is a tool that brute-forces
undocumented UVC extension-unit registers, which carries a documented risk of
corrupting camera firmware. It is worth ruling out a measurement artifact
first.

## If frames genuinely never brighten

Then your camera may need its emitter enabled, and
[linux-enable-ir-emitter](https://github.com/EmixamPP/linux-enable-ir-emitter)
is the established tool. Read its warnings first — it can corrupt camera
firmware, and that risk is real even if small.

If you go that route and it works, please
[report it](https://github.com/amir-salmani/ir-face-auth/issues/new?template=hardware-report.yml), so this
documentation can distinguish cameras that self-strobe from cameras that need
configuring.

## Device discovery

Node numbers are not stable across boots or USB re-enumeration.
`find_ir_device()` scans sysfs instead:

```bash
for d in /sys/class/video4linux/video*; do
  echo "$(basename $d): $(cat $d/name)  index=$(cat $d/index)"
done
```

It selects a node whose `index` is 0 (a capture node; index 1 is metadata) and
whose name contains `IR` as a **whole word** — matching "HP IR Camera" without
false-matching unrelated names.

**If your IR camera is not named with "IR"**, discovery will miss it. That is a
known limitation and a good first contribution — please file a hardware report
with your `name` values.

## Camera permissions

On a desktop session, `/dev/video*` is typically root:video with an ACL
granting the seat's active user:

```
$ getfacl -p /dev/video2
user::rw-
user:amir:rw-        <- granted by logind, not group membership
group::rw-
mask::rw-
```

Note the implication: a **background service user does not get this ACL** and
needs real `video` group membership. `install.sh` adds the `irfa` user to
`video` for exactly this reason.

Testing gotcha: `test -r /dev/video2` can report failure where an actual
`open()` succeeds. Trust the `open()`:

```bash
sudo -u irfa python3 -c "import os; os.close(os.open('/dev/video2', os.O_RDWR)); print('ok')"
```

## Calibrating for a different camera

Thresholds are not portable. Emitter power, sensor gain and lens geometry all
shift the numbers.

```bash
irfa collect --label live --samples 40     # move: near, far, angled
irfa analyze
```

Set `MIN_RESPONSE` and `MIN_FALLOFF` in `src/irfa/liveness.py` below your
measured live minimum, then record attack sessions to check they land below
your thresholds. `analyze` will tell you if a metric cannot separate them.

Reference values on the hardware above:

| Metric | Live face | Default threshold |
|---|---|---|
| `response` | 103 – 125 | 12.0 |
| `falloff` | 1.30 – 1.79 | 1.25 |
| similarity | median 0.738 | 0.45 |

`falloff` has the thinnest margin and is the most likely to need adjusting on
different optics.

## Reporting your hardware

Successes and failures are equally useful — arguably failures more so.

```bash
PYTHONPATH=src python3 -m irfa.cli doctor
```

[File a hardware report](https://github.com/amir-salmani/ir-face-auth/issues/new?template=hardware-report.yml) with
the output. Please send numbers, not photographs.
