# Threat model

Biometric authentication invites overclaiming. This document states what the
project defends against, what it does not, and which claims are backed by
measurement rather than reasoning. Where something is untested, it says so.

## Assets

| Asset | Where | Why it matters |
|---|---|---|
| Face embeddings | `/var/lib/irfa/<user>.npz`, root-owned `0600` | Anyone who can **write** these enrols their own face as you. This is a credential, not merely personal data. |
| The verification helper | `/usr/local/bin/irfa-pam-verify`, root-owned | Runs as root inside the auth path. Write access here is root. |
| The runtime code and models | `/usr/local/lib/irfa`, root-owned | Executed by root. Never install these from a user-writable path. |

The installer deliberately copies code out of the developer checkout under
`/home`. If root executed the checkout directly, any compromise of the user
account would become root — face auth would have *created* a privilege
escalation path rather than protecting one.

## Adversaries

### 1. Someone holding a photo on a phone or tablet

**Defended, by physics — but not yet measured.**

Emissive displays put out effectively nothing at 850nm, and whatever they do
emit is constant across both strobe phases, so it cancels in the
ambient-subtracted image. The attack should register near-zero `response`
against a live-face median of ~103.

Status: **reasoned, not tested.** No spoof session has been recorded. Treat
this as a design intent, not a demonstrated property.

### 2. Someone holding a printed photograph

**Weakly defended, and this is the likely weak point.**

Paper reflects IR well, so `response` will not reject a print. Only `falloff` —
the inverse-square gradient a real 3D face produces — stands in the way, and
measured live values run 1.30–1.79 against a threshold of 1.25. That margin is
thin enough that a flat target could plausibly land inside it.

Status: **untested, and expected to be the hardest case.**

### 3. Someone who resembles the enrolled user

**Unknown.**

No impostor data has been collected. Every recognition figure published by this
project is a genuine-match score. Without a second person's distribution, the
0.45 threshold is a judgement call and **no false-accept rate can be quoted.**
Anyone deploying this should understand that the FAR is not merely high or low
— it is unmeasured.

### 4. A local attacker with code execution as the user

**Partially defended.**

They cannot read `/var/lib/irfa` (verified: permission denied as the service
user). They cannot modify the helper or runtime code without root. They can
run the CLI and enrol into their *own* `~/.local/share/irfa`, which the system
store ignores.

They can, however, re-run `enroll-system.sh` if they already have sudo — and
after this project is installed, a face match grants sudo. Nothing here is a
defence against an attacker who is already you.

### 5. A compromised camera child process

**Contained, with one residual gap.**

The child holds all the untrusted input — V4L2 buffers, JPEG/greyscale decode,
ONNX model parsing — and runs as an unprivileged service user that cannot read
the enrollment store and cannot grant authentication. It supplies a candidate
embedding; root holds the reference data and makes the decision. A
memory-safety bug in a decoder therefore lands in an unprivileged process.

The gap: a compromised child could replay an embedding it captured earlier from
the legitimate user. Closing that needs a trusted path to the sensor, which
consumer UVC hardware does not offer. We accept it and state it.

### 6. A shaped, IR-accurate mask

**Not defended. Out of scope.**

A 3D mask with realistic IR reflectance would satisfy both `response` and
`falloff`. Defeating it needs structured light or time-of-flight sensing that
this hardware does not have.

## What this changes about your system

Enabling face auth for `sudo`, `polkit-1` or `gdm-password` adds an
authentication path that **anyone who can point the camera at your face can
attempt**. Someone who gets you to look at your laptop can attempt auth; a
password requires them to extract something from your memory.

For a laptop lock screen that is usually a good trade. For a machine holding
secrets that matter to someone else, it is not.

## Design rules

1. **Fail closed.** Every error path returns non-zero. The helper catches all
   exceptions at top level so a traceback can never reach a login screen.
2. **Fail open to the password, never past it.** Rules are `sufficient`, never
   `required` or `requisite`. Face auth can only ever *add* a way in.
3. **Never hang the auth stack.** A hard `SIGALRM` bounds the helper; a stuck
   camera must not freeze every `sudo` on the machine.
4. **One service at a time.** `enable.sh` refuses to edit `common-auth`.
5. **Root never executes user-writable code.**

## Reporting

See [SECURITY.md](../SECURITY.md).
