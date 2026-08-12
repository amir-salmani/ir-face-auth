"""Command line interface for the prototype.

Nothing here touches PAM. Enrol and verify from a terminal until the match and
liveness numbers are trustworthy on your own hardware; wiring this into the
authentication stack comes later and separately.
"""

from __future__ import annotations

import argparse
import getpass
import sys

import numpy as np

from . import camera, liveness
from .face import FaceEngine, cosine_similarity
from .store import Enrollment, Store

# SFace's published operating point is 0.363 cosine similarity on visible-light
# faces. IR imagery is out of the model's training domain, so this default is
# tightened; run `irfa calibrate` and set it from measured data.
DEFAULT_THRESHOLD = 0.45


def _capture(engine: FaceEngine, pairs: int):
    """Yield (lit, active, face) for each captured pair containing a face."""
    with camera.IRCamera() as cam:
        for lit, dark in cam.capture_pairs(pairs):
            faces = engine.detect(lit)
            if not faces:
                continue
            yield lit, camera.active_ir(lit, dark), faces[0]


def cmd_doctor(args) -> int:
    try:
        dev = camera.find_ir_device()
    except camera.CameraError as exc:
        print(f"FAIL  camera: {exc}")
        return 1
    print(f"OK    camera: {dev.name} at {dev.path}")

    try:
        engine = FaceEngine()
    except Exception as exc:
        print(f"FAIL  models: {exc}")
        return 1
    print("OK    models: YuNet + SFace loaded")

    seen = 0
    for lit, active, face in _capture(engine, 4):
        seen += 1
        live = liveness.assess(active, face.bbox)
        print(
            f"      frame {seen}: face score={face.score:.2f} "
            f"response={live.response:.1f} falloff={live.falloff:.2f} "
            f"{'LIVE' if live.passed else 'REJECT'}"
        )
    if seen == 0:
        print("FAIL  no face detected -- sit in front of the camera and retry")
        return 1
    print(f"OK    detected a face in {seen} captures")
    return 0


def cmd_calibrate(args) -> int:
    engine = FaceEngine()
    responses, falloffs = [], []
    for _, active, face in _capture(engine, args.samples):
        result = liveness.assess(active, face.bbox)
        responses.append(result.response)
        falloffs.append(result.falloff)
    if not responses:
        print("No faces captured.")
        return 1
    print(f"samples: {len(responses)}")
    print(f"response  min={min(responses):.1f}  median={np.median(responses):.1f}  max={max(responses):.1f}")
    print(f"falloff   min={min(falloffs):.2f}  median={np.median(falloffs):.2f}  max={max(falloffs):.2f}")
    print()
    print("Set MIN_RESPONSE / MIN_FALLOFF in liveness.py comfortably below the")
    print("minimum seen here, then repeat holding up a phone and a printed photo")
    print("to confirm those land below your thresholds.")
    return 0


def cmd_enroll(args) -> int:
    user = args.user or getpass.getuser()
    engine = FaceEngine()
    store = Store()

    vectors, rejected = [], 0
    print(f"Enrolling '{user}'. Look at the camera and move your head slightly...")
    for lit, active, face in _capture(engine, args.samples):
        result = liveness.assess(active, face.bbox)
        if not result.passed:
            rejected += 1
            continue
        vectors.append(engine.embed(lit, face))

    if len(vectors) < args.min_samples:
        print(
            f"Only {len(vectors)} usable samples ({rejected} failed liveness); "
            f"need {args.min_samples}. Try better positioning and retry."
        )
        return 1

    existing = store.load(user)
    stacked = np.vstack(vectors).astype(np.float32)
    if existing is not None and args.append:
        stacked = np.vstack([existing.embeddings, stacked])

    path = store.save(Enrollment(user, stacked, {"model": "sface_2021dec", "domain": "ir"}))
    print(f"Stored {stacked.shape[0]} embeddings for '{user}' at {path}")
    return 0


def cmd_collect(args) -> int:
    """Record a labelled session of liveness metrics and match scores.

    Liveness is measured on every sample regardless of whether it passes, since
    the whole point is to learn where attacks land relative to the threshold.
    """
    from . import metrics

    user = args.user or getpass.getuser()
    engine = FaceEngine()
    enrollment = Store().load(user)
    session = metrics.Session(label=args.label, note=args.note)

    print(f"Recording '{args.label}' -- {args.samples} samples. {args.note or ''}")
    for lit, active, face in _capture(engine, args.samples):
        result = liveness.assess(active, face.bbox)
        session.response.append(round(result.response, 2))
        session.falloff.append(round(result.falloff, 3))
        if enrollment is not None:
            vec = engine.embed(lit, face)
            session.similarity.append(
                round(max(cosine_similarity(vec, ref) for ref in enrollment.embeddings), 4)
            )

    if session.count == 0:
        print("No faces detected. For attack sessions this itself is a result, but")
        print("it means the detector never saw a face -- reposition and retry.")
        return 1

    path = metrics.save(session)
    print(f"Recorded {session.count} samples to {path}")
    print(
        f"  response median {np.median(session.response):.1f}  "
        f"falloff median {np.median(session.falloff):.2f}"
    )
    return 0


def cmd_analyze(args) -> int:
    from . import metrics

    print(metrics.report(metrics.load_all()))
    return 0


def cmd_demo(args) -> int:
    from pathlib import Path
    from . import demo

    return demo.run(
        threshold=args.threshold,
        quorum=args.quorum,
        window=args.window,
        user=args.user or getpass.getuser(),
        save_dir=Path(args.save_dir) if args.save_dir else None,
        headless_frames=args.headless,
    )


def cmd_verify(args) -> int:
    user = args.user or getpass.getuser()
    engine = FaceEngine()
    enrollment = Store().load(user)
    if enrollment is None:
        print(f"No enrollment for '{user}'. Run: irfa enroll")
        return 2

    # Accepting on the first sample that clears the threshold would give an
    # attacker one independent attempt per captured frame, multiplying the
    # false-accept rate by the sample count. Require agreement across frames
    # instead: k of n must clear, and we report the median rather than the max
    # so a single lucky frame cannot carry the decision.
    scores, best_live = [], None
    for lit, active, face in _capture(engine, args.samples):
        result = liveness.assess(active, face.bbox)
        if not result.passed:
            best_live = best_live or result
            continue
        vec = engine.embed(lit, face)
        scores.append(max(cosine_similarity(vec, ref) for ref in enrollment.embeddings))

    if not scores:
        reason = best_live.reason if best_live else "no face detected"
        print(f"DENY    {reason}")
        return 1

    passing = sum(s >= args.threshold for s in scores)
    median = float(np.median(scores))
    if passing >= args.quorum:
        print(
            f"MATCH   {passing}/{len(scores)} frames >= {args.threshold} "
            f"(median {median:.3f})"
        )
        return 0
    print(
        f"DENY    only {passing}/{len(scores)} frames >= {args.threshold} "
        f"(need {args.quorum}; median {median:.3f})"
    )
    return 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="irfa", description="IR face authentication (prototype)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("doctor", help="check camera, models and detection").set_defaults(func=cmd_doctor)

    cal = sub.add_parser("calibrate", help="measure liveness metrics on your hardware")
    cal.add_argument("--samples", type=int, default=12)
    cal.set_defaults(func=cmd_calibrate)

    enr = sub.add_parser("enroll", help="record face embeddings")
    enr.add_argument("--user")
    enr.add_argument("--samples", type=int, default=10)
    enr.add_argument("--min-samples", type=int, default=4)
    enr.add_argument("--append", action="store_true", help="add to existing enrollment")
    enr.set_defaults(func=cmd_enroll)

    col = sub.add_parser("collect", help="record a labelled metric session")
    col.add_argument("--label", required=True,
                     help="live | spoof-phone | spoof-print | impostor-<name>")
    col.add_argument("--samples", type=int, default=25)
    col.add_argument("--note", default="")
    col.add_argument("--user")
    col.set_defaults(func=cmd_collect)

    sub.add_parser("analyze", help="compare sessions and derive thresholds").set_defaults(func=cmd_analyze)

    dem = sub.add_parser("demo", help="live annotated view of the pipeline")
    dem.add_argument("--user")
    dem.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    dem.add_argument("--quorum", type=int, default=3)
    dem.add_argument("--window", type=int, default=6, help="rolling decision window")
    dem.add_argument("--save-dir", default="captures")
    dem.add_argument("--headless", type=int, default=0, metavar="N",
                     help="write N annotated frames instead of opening a window")
    dem.set_defaults(func=cmd_demo)

    ver = sub.add_parser("verify", help="attempt a match")
    ver.add_argument("--user")
    ver.add_argument("--samples", type=int, default=6)
    ver.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    ver.add_argument("--quorum", type=int, default=3, help="frames that must clear the threshold")
    ver.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (camera.CameraError, KeyboardInterrupt) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
