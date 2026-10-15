<!-- SPDX-License-Identifier: Apache-2.0
(c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173 -->

# Shared bounded engine interface

[Killinchu #538](https://github.com/szl-holdings/killinchu/pull/538) and
[A11oy #2855](https://github.com/szl-holdings/a11oy/pull/2855) synchronize the
existing shared `a11oy_code_engine.py`. The active shared-source manifest binds
its bytes and retains the unchanged meter module. Existing shared drift guards
remain authoritative.

Killinchu callers do not supply an execution budget, so their defaults are
unchanged. The optional strict path requires companion modules present in
A11oy. Killinchu does not copy those modules or enable that path: attempting it
without its companions fails before inference. This is interface compatibility,
not model qualification, a new service, or verified execution evidence.

The existing main publisher restarts the Space. Its observed receipt ledger is
EPHEMERAL / PROCESS_MEMORY. Retaining and verifying an exported chain preserves
captured receipts, but does not preserve subsequent acknowledged writes across
a restart. The current runtime has no write-freeze/final-checkpoint transition.
Resolve that operational constraint before merging; this patch changes neither
ledger storage nor the automatic publisher.
