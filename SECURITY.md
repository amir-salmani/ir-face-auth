# Security policy

## Status: experimental

This project has not been audited, has no false-accept rate measurement, and
has not been tested against real presentation attacks. It should be treated as
a convenience unlock for a personal laptop, not as a security control.

Do not use it as the only thing standing between an attacker and something that
matters.

## Reporting a vulnerability

Report privately to **hi@amirsalmani.com**, or via GitHub's
[private vulnerability reporting](https://github.com/amir-salmani/ir-face-auth/security/advisories/new).

Please do not open a public issue for anything that would let someone
authenticate as another user. Everything else — crashes, hangs, install bugs —
is fine in public.

Useful details: hardware, distro, the relevant `journalctl -t irfa-pam` lines,
and what you did. If you defeated the liveness check, the metric values from
`irfa collect` are worth more than a description.

I will acknowledge within a week. This is a personal project with no SLA behind
it; if something is being actively exploited, say so and I will prioritise it.

## Known limitations

These are documented, not secret. Reporting them is unnecessary — though
*evidence* about them is very welcome.

| Limitation | Status |
|---|---|
| False-accept rate | **Unmeasured.** No impostor data has been collected. |
| Printed-photo attack | Untested. Expected to be the weakest point, since paper reflects IR and only the `falloff` metric opposes it. |
| Display replay attack | Untested. Expected to fail against the ambient-subtraction check, but this is reasoning, not measurement. |
| 3D mask attack | Not defended. Out of scope for this hardware. |
| Embedding replay by a compromised camera child | Accepted risk. Needs a trusted sensor path that consumer UVC hardware lacks. |
| Hardware coverage | One camera model tested. |

See [docs/threat-model.md](docs/threat-model.md) for the full analysis.

## Design commitments

Changes that violate these will be rejected regardless of what else they
improve:

1. Face auth is always `sufficient`, never `required`. It cannot block a login,
   only add a way in. A password always remains available.
2. All error paths deny.
3. Untrusted input — camera buffers, image decoding, model parsing — is handled
   by an unprivileged process that cannot read the enrollment store and cannot
   grant authentication.
4. Root never executes code from a user-writable path.
5. Nothing in the authentication path may hang without a bound.
