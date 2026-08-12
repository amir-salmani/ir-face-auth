# Usage

All commands run as `PYTHONPATH=src python3 -m irfa.cli <command>`, or simply
`irfa <command>` if you installed the package.

## `doctor`

Checks camera discovery, model loading and face detection, then reports live
metrics. Run this first, and whenever something stops working.

```
OK    camera: HP 5MP Camera: HP IR Camera at /dev/video2
OK    models: YuNet + SFace loaded
      frame 1: face score=0.88 response=112.1 falloff=1.53 LIVE
```

- `score` — detector confidence the region is a face (0–1)
- `response` — mean active-IR return from the face core; screens produce ~0
- `falloff` — core brightness ÷ edge brightness; flat photos produce ~1.0

## `enroll`

```bash
irfa enroll [--samples 10] [--min-samples 4] [--append] [--user NAME]
```

Records embeddings. Samples failing liveness are discarded. `--append` adds to
an existing enrollment rather than replacing it — useful for adding glasses, a
different hairstyle, or a second lighting condition.

## `verify`

```bash
irfa verify [--threshold 0.45] [--quorum 3] [--samples 6]
```

```
MATCH   6/6 frames >= 0.45 (median 0.578)
DENY    only 1/6 frames >= 0.45 (need 3; median 0.31)
```

**Why a quorum.** Accepting on the first frame over threshold would give an
attacker one independent attempt per captured frame, multiplying the
false-accept rate by the sample count. Requiring agreement across frames and
reporting the median stops a single lucky frame carrying the decision.

Exit codes: `0` match, `1` denied, `2` no enrollment.

## `demo`

```bash
irfa demo [--window 6] [--save-dir captures] [--headless N]
```

Live side-by-side view: lit IR (what the recogniser sees) and active IR (what
the liveness check sees), with bounding box, metrics and a rolling verdict.

Keys: `q` quit, `s` save a snapshot. `--headless N` writes N annotated frames
instead of opening a window, for machines without a display.

This is the fastest way to understand the system. Cover the emitter and watch
the right pane collapse to black.

## `collect` and `analyze`

The calibration pair. Thresholds picked by hand are guesses; these derive them
from measured separation.

```bash
irfa collect --label live         --samples 40
irfa collect --label spoof-phone  --samples 25 --note "OLED, max brightness, 30cm"
irfa collect --label spoof-print  --samples 25
irfa collect --label impostor-sam --samples 25
irfa analyze
```

Sessions are stored as JSON under `calibration/`. **Only scalar metrics are
recorded — never images.**

`analyze` compares the distributions and does one of three things per metric:

| Situation | Output |
|---|---|
| Attack data absent | States that the value bounds false *rejects* only, and refuses to imply a false-accept bound |
| Clean separation | Proposes a threshold in the gap, with the margin |
| Distributions overlap | States the metric **cannot** separate them on its own |

That third case is the one that matters. A calibration tool that always emits a
confident number is worse than useless for security work.

Move around during a `live` session — near, far, angled, glasses on and off —
or you will calibrate for one pose and reject yourself in every other.

## Tuning

Defaults, and where they live:

| Constant | Default | File |
|---|---|---|
| `MIN_RESPONSE` | 12.0 | `src/irfa/liveness.py` |
| `MIN_FALLOFF` | 1.25 | `src/irfa/liveness.py` |
| `DEFAULT_THRESHOLD` | 0.45 | `src/irfa/cli.py` |
| `THRESHOLD` / `QUORUM` / `SAMPLES` | 0.45 / 3 / 6 | `packaging/irfa-pam-verify` |

Raising `DEFAULT_THRESHOLD` rejects more impostors and more of you. Lowering it
does the reverse. Without impostor data you are trading against an unknown, so
prefer stricter.

**Changing the PAM helper's constants requires a reinstall** (`sudo
packaging/install.sh`) — it runs from `/usr/local/lib/irfa`, not your checkout.
