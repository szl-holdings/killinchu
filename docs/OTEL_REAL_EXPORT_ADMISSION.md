# Killinchu — real OTLP/gRPC export admission

**Current status: SOURCE-TESTED; NEW IMAGE NOT RELEASE-ADMITTED; FIVE-ORGAN TRACE HOLD.**

The immutable historical Killinchu image pinned by szl-build-env was signed
from commit `cc49a0cc5fa03405fc7894c64040e013911a63bc`, before its
current VSP telemetry middleware existed. The modern Dockerfile copies
`vsp_otel` but `space-core.txt` installed only `opentelemetry-api`, not the
SDK or OTLP/gRPC exporter. Source presence and HTTP 200 health are not proof
of real exported spans.

## Owned source correction

- Add a hash-locked exporter closure
  `deploy/space/requirements/space-otel.{in,txt}`, compiled against public
  PyPI for Linux Python 3.14, with OTel SDK, gRPC exporter and exact
  transitive versions.
- Both canonical Dockerfiles install the lock **without** a best-effort
  fallback and fail their build unless grpcio, SDK and OTLP exporter import.
- Preserve private-network gating in `vsp_otel.middleware`: no endpoint
  means **in-process-only**, and a public IP or unapproved DNS hostname is
  refused. No public collector or production endpoint is added by this PR.
- A SHA-pinned, bounded, read-only GitHub Actions test installs the exact
  lock into Linux Python 3.14 and sends one synthetic, child-of-injected-W3C
  span to an isolated loopback gRPC collector. No private data leaves CI.

## Evidence

On 2026-11-17, the owner workstation installed the exact hash-locked
closure into an isolated Python 3.12 environment; `pip check` passed.
A real, loopback-only gRPC collector received the expected Killinchu
service span as a child of the injected traceparent (**2/2 local tests
passed**, including unconfigured/public endpoint refusal). The existing
packaging and security regression suite passed **13/13** tests, with
Ruff E9/F clean. This is local runtime capability evidence, **not**
production or five-organ acceptance.

Developer reproduction:

```bash
python -m pip install --disable-pip-version-check --require-hashes \
  -r deploy/space/requirements/space-otel.txt
python -I -B tests/test_vsp_otel_real_export.py
python -m pip check
```

## Release admission

1. Verify current-head protected CI, including real Linux Python 3.14
   loopback export, without bypassing approvals.
2. Publish a new immutable Killinchu image from the exact protected SHA
   with cryptographic signature/provenance and independent readback.
3. Rebind `szl-build-env` to that digest and source SHA, configure only the
   approved private collector in the isolated acceptance manifest, then
   rerun actual five-organ Jaeger acceptance.
4. Require five connected, fresh child spans and all five health checks.
   Any missing service, drifted source, expired receipt or absent signature
   remains **HOLD**.
5. HF/production deployment and Cloudflare revenue remain separate governed
   release and settlement gates. This source PR authorizes neither.

No payment, email, secrets, deployment, consumer routing or collector
credentials are handled here.
