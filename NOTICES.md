# Third-Party Notices — SZL Holdings Flagships
**Doctrine v11 LOCKED 749/14/163 | SLSA L1 honest | Generated: 2026-06-03**

This file contains notices for third-party libraries used by SZL Holdings flagships.

## Python Dependencies

### FastAPI
- **License:** MIT
- **Source:** https://github.com/tiangolo/fastapi
- **Usage:** API framework for all 5 flagships

### Gradio
- **License:** Apache-2.0
- **Source:** https://github.com/gradio-app/gradio
- **Usage:** UI framework for HuggingFace Spaces

### Uvicorn
- **License:** BSD-3-Clause
- **Source:** https://github.com/encode/uvicorn
- **Usage:** ASGI server

### httpx
- **License:** BSD-3-Clause
- **Source:** https://github.com/encode/httpx
- **Usage:** HTTP client for inter-flagship calls

### huggingface_hub
- **License:** Apache-2.0
- **Source:** https://github.com/huggingface/huggingface_hub
- **Usage:** HuggingFace API access

## Infrastructure Components

### UDS Core (Defense Unicorns)
- **License:** Apache-2.0
- **Source:** https://github.com/defenseunicorns/uds-core
- **Usage:** Kubernetes security baseline (UDS deployment)

### Zarf (Defense Unicorns)
- **License:** Apache-2.0  
- **Source:** https://github.com/zarf-dev/zarf
- **Usage:** Airgap packaging

### Pepr (Defense Unicorns)
- **License:** Apache-2.0
- **Source:** https://github.com/defenseunicorns/pepr
- **Usage:** Kubernetes admission webhook

## Mathematical Libraries

### Lean 4 (Lean FRO / Microsoft Research)
- **License:** Apache-2.0
- **Source:** https://github.com/leanprover/lean4
- **Usage:** Formal verification substrate (lutar-lean)

### Mathlib4
- **License:** Apache-2.0
- **Source:** https://github.com/leanprover-community/mathlib4
- **Usage:** Mathematical library for Lean 4

## Governed Vector Index (WAQAY) — studied open work, made ours (attribution required)

WAQAY (Quechua: *to keep / guard / store*) is SZL Holdings' own governed,
air-gapped, DSSE-signed quantized vector index (`szl_waqay.py`). It was built by
**studying** the following MIT / open work and **re-implementing the approach** in
pure Python — we do **not** vendor or copy the upstream crate. Attribution is
required by the MIT license and is given here in full.

### turbovec (Ryan Codrai)
- **License:** MIT
- **Copyright:** © 2026 Ryan Codrai
- **Source:** https://github.com/RyanCodrai/turbovec
- **What we studied:** the Rust+Python vector-index architecture — a
  data-oblivious quantizer with **no codebook training** and **no train phase**
  (online ingest); the Lloyd-Max codebook fit analytically to the Beta marginal
  induced by a random orthogonal rotation; RaBitQ-style per-vector length
  renormalization; bit-packed 2/4-bit codes.
- **What we built (OURS):** a clean-room **pure-NumPy** re-implementation of the
  *approach* (`szl_waqay.py`). We add the governed difference — every index build
  and every retrieval emits a **DSSE-signed provenance receipt** and passes the
  **Restraint gate**. We do **not** ship the Rust crate, and we do **not** claim
  to match its SIMD throughput: our perf figures are labeled **MODELED/ROADMAP**.
  Compression is **MEASURED**; recall is a **MODELED bound** (never claimed perfect).

### TurboQuant (Google Research)
- **Attribution:** the data-oblivious quantization *approach* originates with
  Google Research's TurboQuant work (normalize → random orthogonal rotation →
  analytic Lloyd-Max codebook on the Beta((d-1)/2,(d-1)/2) marginal → bit-pack →
  per-vector scale). WAQAY implements this approach independently in NumPy.
- **Honesty:** we attribute the approach; we make no claim of affiliation with or
  endorsement by Google Research.

**Honest perf labeling (Doctrine v11, Zero-Bandaid Law):** WAQAY is a pure-Python
governed index *inspired by* TurboQuant. It does **not** claim to beat FAISS or to
match the Rust SIMD original. Compression ratios shown are MEASURED on the actual
bytes stored; recall is a MODELED design bound surfaced honestly (trust ceiling
< 1.0 — never perfect).

## Section 889 Declaration

SZL Holdings does NOT use equipment or services from:
- Huawei Technologies Company
- ZTE Corporation
- Hytera Communications
- Hangzhou Hikvision Digital Technology Company
- Dahua Technology Company

This notice is provided in compliance with Section 889 of the 2019 NDAA.

**Signed-off-by: Yachay <yachay@szlholdings.ai>**  
**Co-Authored-By: Perplexity Computer Agent <agent@perplexity.ai>**

---

## Frontier Tabs (3D · Live) — Vendored Visualization Libraries

The killinchu operator console (`/elite`) vendors the following open-source
visualization libraries locally (served from `/vendor/*`, **no CDN — sovereign /
offline**). killinchu adopts their interaction **patterns** and reimplements all
tab logic as its own original code; the libraries themselves are used unmodified
under their own licenses. No GPL/AGPL code is copied.

### 3d-force-graph / three-forcegraph
- **License:** MIT
- **Copyright:** (c) Vasco Asturiano (vasturiano)
- **Source:** https://github.com/vasturiano/3d-force-graph
- **Usage:** Field Net, Autonomy Oversight, MELT, Dark-Vessel Threat Graph 3D entity-link graphs

### globe.gl
- **License:** MIT
- **Copyright:** (c) Vasco Asturiano (vasturiano)
- **Source:** https://github.com/vasturiano/globe.gl
- **Usage:** Single-Operating-Picture globe (Live Picture / field view)

### force-graph
- **License:** MIT
- **Copyright:** (c) Vasco Asturiano (vasturiano)
- **Source:** https://github.com/vasturiano/force-graph
- **Usage:** 2D force-graph fallback

### Apache ECharts
- **License:** Apache-2.0
- **Copyright:** The Apache Software Foundation
- **Source:** https://github.com/apache/echarts
- **Usage:** MELT golden-metric + Deploy posture charts

### echarts-gl
- **License:** Apache-2.0
- **Copyright:** The Apache Software Foundation
- **Source:** https://github.com/ecomfe/echarts-gl
- **Usage:** GL-accelerated chart rendering

### Cytoscape.js
- **License:** MIT
- **Copyright:** (c) The Cytoscape Consortium
- **Source:** https://github.com/cytoscape/cytoscape.js
- **Usage:** 2D graph rendering (existing tabs)

### D3 (d3-force et al.)
- **License:** ISC / BSD-3-Clause
- **Copyright:** (c) Mike Bostock
- **Source:** https://github.com/d3/d3
- **Usage:** Force-layout primitives used by the graph libraries

### Chart.js
- **License:** MIT
- **Copyright:** (c) Chart.js Contributors
- **Source:** https://github.com/chartjs/Chart.js
- **Usage:** Sparklines / gauges (existing tabs)

### KaTeX
- **License:** MIT
- **Copyright:** (c) Khan Academy and contributors
- **Source:** https://github.com/KaTeX/KaTeX
- **Usage:** Formula rendering

### Interaction-model inspirations (PATTERNS only — no code copied)
- vasturiano force-graph explorable entity-link model (MIT-compatible) — Field Net tab
- GraphRouter / RouteProfile, Tao Feng et al. (arXiv:2605.00180) — Model Atlas routing graph
- New Relic / Datadog MELT + service-map — MELT Observability tab
- Wiz / CrowdStrike security-graph "toxic path" — Dark-Vessel Threat Graph tab
- Defense Unicorns UDS deploy-posture — Deploy Posture tab (uds-core is AGPL: **PATTERN ONLY, NO code copied**)
- Governed-run oversight pattern — Autonomy Oversight tab (the proven non-interference kernel is killinchu's own)

Copyright (c) of each library belongs to its respective authors. Full license
texts ship with each minified bundle's upstream distribution under `static/vendor/`.

**Signed-off-by: stephenlutar2-hash <stephenlutar2@gmail.com>**
