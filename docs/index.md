# Documentation

Complete documentation for `ir-face-auth`.

| Document | What it covers |
|---|---|
| [Installation](installation.md) | Requirements, install, enrollment, uninstall |
| [Usage](usage.md) | Every CLI command, with what its output means |
| [Architecture](architecture.md) | How it works: strobe capture, liveness, recognition, privilege split |
| [PAM integration](pam-integration.md) | Wiring into GDM, lock screen, sudo, polkit — and undoing it |
| [Hardware](hardware.md) | The strobe finding, device discovery, calibrating for a different camera |
| [Threat model](threat-model.md) | Assets, adversaries, what is defended and what is not |

Project-level documents: [README](../README.md) ·
[SECURITY](../SECURITY.md) · [CONTRIBUTING](../CONTRIBUTING.md) ·
[CODE_OF_CONDUCT](../CODE_OF_CONDUCT.md)

## Open licensing

This documentation is **CC BY 4.0** — see [LICENSE-DOCS](../LICENSE-DOCS).
Source code is **MIT** — see [LICENSE](../LICENSE).

Both licences are conformant with the
[Open Definition](https://opendefinition.org/) maintained by the
[Open Knowledge Foundation](https://okfn.org/). In practice that means anyone
may use, redistribute and adapt this material, including commercially, with
attribution as the only condition.

Against the Open Definition's criteria:

| Criterion | Status |
|---|---|
| Open licence | CC BY 4.0 (docs), MIT (code) — both [OD-conformant](https://opendefinition.org/licenses/) |
| Access | Public repository, no registration, no fee |
| Open format | Markdown and PNG throughout — no proprietary formats |
| Machine readable | Plain-text Markdown; licences declared in `pyproject.toml` |
| Redistribution | Permitted, including commercially |
| Derivative works | Permitted, with attribution |
| No discrimination | No restriction on persons, groups or fields of endeavour |

One honest exception: the **ONNX model files are not ours to license.** They
are fetched at install time from [OpenCV Zoo](https://github.com/opencv/opencv_zoo)
and carry their own terms. This is why `scripts/fetch-models.sh` downloads them
rather than the repository vendoring them.

## A note on how to read these documents

Security claims here are marked as **measured** or **unmeasured**, and the
distinction is load-bearing. This project has real measurements behind its
liveness metrics on one camera, and **no measurements at all** behind its
false-accept rate or its resistance to spoofing attempts.

Where something is untested, the documentation says so rather than describing
the mechanism confidently and letting you infer that it works. Please hold any
contribution to the same standard.
