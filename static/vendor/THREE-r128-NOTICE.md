# three-r128.min.js

three.js r128 classic UMD build (`window.THREE`), MIT — see `../vendor3d/THREE_LICENSE.txt`.
Byte-identical copy of `static-vendor/three.min.js` from
`szl-holdings/a11oy@f613fb7b22ad935c6fa9def2bcc38c0d0039122c`.

Why a second three.js: `web/console.html` was written against r128 (it loaded
`cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js`). Serving the same
revision from the same origin removes the runtime CDN dependency (Doctrine v11
G7) without changing the page's rendering behaviour (G8). `three.min.js` in this
directory is r160 and stays the build for pages written against r160
(`live_wires.html`, `szl_live_wires.py`).
