# Qualifying the served Killinchu landing

`static/landing.html` is the root page. The production response also passes
through the capability navigation in `killinchu_defend_plane.py`, the brand
navigation in `killinchu_nav_wireup.py`, and two widget injection classes in
`serve.py`. Rendering the raw HTML alone does not test that composition.

The landing declares `<!-- killinchu:capability-navigation -->` after its skip
link. The capability middleware fills that slot and retains its existing
insertion behavior on other pages. The native `details` disclosure keeps every
existing page destination and unavailable label, works without JavaScript, and
gives the links room to reflow. The product bar is the landing's sole sticky
navigation layer.

## Local browser qualification

```sh
python -m pip install 'starlette==1.3.1' 'httpx==0.28.1' 'playwright==1.60.0'
python -m playwright install chromium
python tools/verify_landing_browser.py --output /tmp/killinchu-landing-observations
```

`CHROME_PATH` can select an installed Chromium. The `Served landing
presentation` job in the existing CI workflow runs the same check against its
exact candidate checkout and retains unsigned observations.

The fixture mounts one local HTML route. It uses the actual capability and
brand middleware classes, and selects the two actual widget class declarations
and literal tags from the `serve.py` syntax tree. It does not import `serve.py`,
register operational routes, start backend services, load credentials, or make
a signing request. Browser requests outside local static assets receive labeled
UNAVAILABLE fixtures; WebSocket attempts are closed and recorded.

The checks cover the composed page at 320, 390, 768, 1280 and 1920 CSS pixels:
keyboard entry, native disclosure and link visibility, 44-pixel controls, text
contrast samples, reflow, navigation overlap after scrolling, reduced motion,
forced colors, and the no-JavaScript fallback. Existing capability limitations
remain visible. This is presentation qualification, not operational readiness,
detector performance, a cryptographic attestation, or an accessibility
certification of every console route.

## Observed regression baseline

At accepted source
`32760a15fcecfe50211654713d7e4e6a86d947fa`, the fixture's 61,081-byte output
matched the independently captured public root response exactly: SHA-256
`9235feca7de31242d9f01d2d010ab62a329e10ca2f3c10fb9363d400534aa5bd`.
The observed immutable Hub/runtime revision was
`fc82b533bd5e98db47a7bea8cc937a7c792a4af3`.

That baseline had three distinct navigation layers trying to stick at the top,
a skip link repaired only after JavaScript loaded, and status text extending
beyond 320 pixels without JavaScript. Native keyboard focus could also leave a
partially visible link clipped in the horizontal capability rail. The source
repair removes those dependencies while preserving all existing destinations,
unavailable states, underlying operations, and the established HF publisher.
