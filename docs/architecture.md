# Architecture

## The finding everything rests on

Windows Hello IR cameras pulse their 850nm emitter at **half the sensor frame
rate**. Measured on the reference hardware, 90 consecutive frames:

```
  0: [42.9, 0.5, 43.0, 0.6, 42.8, 0.7, 43.0, 0.8, 43.1, 0.9, ...]
 15: [ 1.6, 21.4, 1.6, 21.3, 1.5, 20.9, 1.5, 20.9, 1.5, 20.5, ...]

frames >15 mean: 45/90 (50%)
```

A perfect alternation: emitter-on, ambient-only, emitter-on, ambient-only.

This explains the most common bug report about these cameras on Linux. Grab a
single frame and you land on an ambient frame half the time and see pure black
— which looks exactly like a dead emitter, and sends people toward tools that
poke undocumented UVC extension-unit registers, at the documented risk of
corrupting camera firmware. On this hardware none of that is necessary.

It also hands us a liveness primitive:

```
active_ir = lit_frame - ambient_frame
```

That difference isolates light **this laptop's own emitter** put onto the
subject and got back.

## Pipeline

```
  camera.py    find IR device by sysfs name (never a hardcoded /dev/videoN)
       |       discard settle frames, then read consecutive pairs
       |       classify brighter frame as lit, dimmer as ambient
       v
  active_ir    lit - ambient, clipped to [0, 255]
       |
       +---> face.py       YuNet detects, SFace embeds (from lit frame)
       |
       +---> liveness.py   response + falloff (from active IR)
                 |
                 v
             quorum decision: k of n frames must clear the threshold
```

### Device discovery

Node numbering is not stable across boots or USB re-enumeration, so
`/dev/video2` is never safe to assume. `find_ir_device()` walks
`/sys/class/video4linux/*/name` for a capture node (`index == 0`) advertising
`IR` as a whole word — matching `HP IR Camera` but not names that merely
contain those letters.

### Why two frames make a pair

Because the emitter strictly alternates, *any* two consecutive frames form a
lit/ambient pair. We only decide which is which, by comparing means. Pairs
where both frames land in the same phase are rejected — otherwise the
difference image would be meaningless noise.

## Liveness

Two independent properties of the active IR image:

**`response`** — mean active-IR return from the face core. Emissive displays
emit almost nothing at 850nm and contribute equally to both strobe phases, so
they cancel toward zero. Measured on live faces: **103–125**. Threshold: 12.

**`falloff`** — core brightness ÷ surrounding-ring brightness. Active IR obeys
an inverse-square law, so a real 3D face returns markedly more from the nose
and forehead than from the jaw and edges. A flat print returns near-uniform.
Measured on live faces: **1.30–1.79**. Threshold: 1.25.

> **Status: reasoned, not measured.** No attack session has been recorded
> against either metric. The live-face numbers are real; the attack numbers do
> not exist. `falloff` in particular has a thin margin and paper reflects IR
> well, so printed photographs are expected to be the hard case. See
> [threat-model.md](threat-model.md).

## Recognition

**YuNet** for detection, **SFace** for embedding — both bundled with OpenCV
≥ 4.5 and executed by its own DNN module.

This choice is load-bearing. The obvious alternative, dlib, requires a C++
toolchain at install time and its bindings lag interpreter releases; that is
why the established project in this space cannot be installed on a current
distro. Here the entire runtime dependency is OpenCV and numpy. Nothing
compiles, so nothing rots when Python moves.

Embeddings are 128-d, L2-normalised, so comparison is a dot product.

Both models were trained on visible-light faces, and IR is out of their
training domain. Measured cost of that shift on the reference hardware:

| | |
|---|---|
| Enrollment self-similarity (66 pairs) | 0.742 – 0.986, median 0.912 |
| Fresh session vs enrollment | 0.425 – 0.876, median 0.738 |

A median of 0.738 is comparable to visible-light performance, so the domain
shift costs less than expected — though the low tail is why a quorum matters.

## Privilege split

The single biggest difference from prior art. The PAM helper forks before
touching the camera:

| | child | parent |
|---|---|---|
| Runs as | `irfa`, unprivileged, `video` group | root |
| Handles | V4L2 buffers, image decode, ONNX parsing — all untrusted input | numpy arithmetic on a bounded, validated array |
| Can read `/var/lib/irfa`? | **No** (verified: permission denied) | Yes |
| Can grant authentication? | **No** | Yes |

The child supplies a candidate embedding over a pipe; root holds the reference
data and makes the decision. A memory-safety bug in a decoder or model parser
therefore lands in an unprivileged process rather than in root.

Contrast: running the whole pipeline as root inside the auth path — the
conventional approach — makes any such bug a root compromise triggerable by
anyone who can point a camera at the machine.

The parent bounds the payload it reads (1MB) and validates embedding shape
before use, because root must not be driven to exhaust memory or index out of
bounds by a misbehaving child.

**Residual gap:** a compromised child could replay an embedding captured
earlier from the legitimate user. Closing that needs a trusted path to the
sensor, which consumer UVC hardware does not offer.

## Failure behaviour

Everything in the auth path is bounded and fails closed:

| Condition | Result |
|---|---|
| No camera / camera busy | exit 2 → falls through to password |
| Remote session (`PAM_RHOST` set) | exit 2 immediately, no capture attempted |
| No enrollment for user | exit 2 |
| No face, or liveness fails | exit 1 |
| Below quorum | exit 1 |
| Any unhandled exception | caught at top level → exit 2, logged to syslog |
| Anything hanging | `SIGALRM` at 8s |

The alarm exists because a stuck camera would otherwise freeze every `sudo` on
the machine. Tracebacks are caught so they can never surface at a login screen.

## Performance

~3.1s per authentication, dominated by loading the 37MB SFace model on every
invocation plus 14 camera settle frames. Two improvements are open: exit
capture as soon as the quorum is reached, and a socket-activated daemon holding
the models warm.
