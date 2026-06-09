# Vendored anvaka graph stack — ATTRIBUTION (0-CDN, in-image)

All files below are **vendored locally** (no runtime CDN) and referenced with relative
`<script src="/vendor/...">` tags only. Author: **Andrei Kashcha** (GitHub
[@anvaka](https://github.com/anvaka)). We do **not** relicense or claim authorship of
these libraries — "make it our own" means our data + our tab logic + our adaptation
layer; the rendering/layout primitives stay attributed to Andrei Kashcha.

| Vendored file | Source repo + path | SPDX license | Global exposed | Copyright |
|---|---|---|---|---|
| `ngraph.graph.min.js` | [anvaka/ngraph.graph](https://github.com/anvaka/ngraph.graph) `dist/` | BSD-3-Clause | `createGraph` | © 2013-2026 Andrei Kashcha |
| `ngraph.forcelayout.min.js` | [anvaka/ngraph.forcelayout](https://github.com/anvaka/ngraph.forcelayout) `dist/` | BSD-3-Clause | `ngraphCreateLayout` | © 2013-2026 Andrei Kashcha |
| `ngraph.path.min.js` | [anvaka/ngraph.path](https://github.com/anvaka/ngraph.path) `dist/` | MIT | `ngraphPath` (`.aStar/.aGreedy/.nba`) | © 2017-2026 Andrei Kashcha |
| `ngraph.events.umd.js` | [anvaka/ngraph.events](https://github.com/anvaka/ngraph.events) `index.js` (ESM source, wrapped UMD) | BSD-3-Clause | `ngraphEvents` | © 2013-2026 Andrei Kashcha |
| `panzoom.min.js` | [anvaka/panzoom](https://github.com/anvaka/panzoom) `dist/` | MIT | `panzoom` | © 2016-2026 Andrei Kashcha |
| `vivagraph.min.js` | [anvaka/VivaGraphJS](https://github.com/anvaka/VivaGraphJS) `dist/vivagraph.min.js` | BSD-3-Clause | `Viva` | © 2011-2026 Andrei Kashcha |
| `three.map.control.min.js` | [anvaka/three.map.control](https://github.com/anvaka/three.map.control) v1.6.0 (npm) | MIT | `threeMapControls` / `PanZoomControls` | © 2016-2026 Andrei Kashcha |
| `ngraph.three.min.js` | [anvaka/ngraph.three](https://github.com/anvaka/ngraph.three) v0.0.16 (npm) | MIT | `ngraphThree` | © 2013-2026 Andrei Kashcha |
| `ngraph.cw.min.js` | [anvaka/ngraph.cw](https://github.com/anvaka/ngraph.cw) v2.0.0 (npm) | MIT | `ngraphCW` | © 2013-2026 Andrei Kashcha |
| `w-gl.min.js` | [anvaka/w-gl](https://github.com/anvaka/w-gl) v0.22.0 `build/wgl.js` (UMD) | MIT | `wgl` (`.createScene/.WireCollection/.PointCollection/.mapControls`) | © 2017-2026 Andrei Kashcha |

Each library's full LICENSE text is kept beside its vendored file as `LICENSE.<lib>`.

## Build provenance (the four formerly-deferred libs)
`three.map.control`, `ngraph.three`, and `ngraph.cw` ship upstream only as
CommonJS-with-`require()`-trees; `w-gl` ships as `index.ts` + a prebuilt UMD `build/wgl.js`.
To turn them into single self-contained **browser globals** (0-CDN) they were bundled
**once, offline, at build time** with `esbuild@0.21.5 --bundle --minify --format=iife`:

- `three.map.control.min.js` — bundles `wheel`, `ngraph.events`, `amator`, `./lib/kinetic`
  inline; **`three` is marked `--external`** (provided in-image as `window.THREE`, never
  re-bundled → no duplicate three.js, no CDN).
- `ngraph.cw.min.js` — bundles `ngraph.random` inline; fully self-contained.
- `ngraph.three.min.js` — bundles `ngraph.merge`, `ngraph.forcelayout3d`, `ngraph.physics.*`,
  `three.trackball` inline; **`three` is `--external`** (in-image global).
- `w-gl.min.js` — the upstream prebuilt UMD `build/wgl.js` copied verbatim (global `wgl`).

This is a one-time build-time transform of permissively-licensed (MIT/BSD-3) source; the
runtime carries **zero network dependency** and the libraries remain attributed to the author.

3D tabs already use the in-image **`three.min.js` + 3d-force-graph + globe.gl** engines with the
vendored **`ngraph.forcelayout {dimensions:3}`** deterministic layout; `three.map.control` adds
map-style pan/zoom camera control, `ngraph.three` adds the three.js graph-render glue, `w-gl`
adds a high-performance WebGL line/point renderer for dense track/constellation surfaces, and
`ngraph.cw` adds Chinese-Whispers community clustering for graph node coloring — all 0-CDN.
