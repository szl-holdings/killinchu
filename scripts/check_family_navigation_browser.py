#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline Chromium regression for the product-owned Killinchu family navigation.

Executes the real static/truth-cop.js, with its single legacy data endpoint replaced
by an explicitly unavailable in-memory fixture. No backend, external request,
provider mutation, full-page application acceptance, or native zoom is exercised.
"""
from __future__ import annotations
import argparse, hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

CASES = (
    ('phone-320',320,568,1,'no-preference','none'),
    ('phone-360',360,800,1,'no-preference','none'),
    ('phone-375',375,812,1,'no-preference','none'),
    ('phone-390',390,844,1,'no-preference','none'),
    ('tablet-768',768,1024,1,'no-preference','none'),
    ('desktop-1024',1024,900,1,'no-preference','none'),
    ('desktop-1440',1440,1000,1,'no-preference','none'),
    ('theatre-1920',1920,1080,1,'no-preference','none'),
    ('ultrawide-3440',3440,1440,1,'no-preference','none'),
    ('reduced-motion',375,812,1,'reduce','none'),
    ('forced-colors',375,812,1,'no-preference','active'),
    ('css-zoom-200',1280,900,2,'no-preference','none'),
    ('css-zoom-400',1280,900,4,'no-preference','none'),
)
FIXTURE = '''<!doctype html><html lang="en"><head>
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Offline Killinchu navigation regression</title></head>
<body style="margin:0"><main><h1>Component geometry fixture</h1>
<p>This is an offline test. No operational data or actions are available.</p></main></body></html>'''
FETCH_FIXTURE = '''() => {
window.__fixtureCalls = [];
window.fetch = async (url, options) => {
  window.__fixtureCalls.push({url: String(url), method: (options && options.method) || "GET"});
  return {ok: false, json: async () => ({mode: "UNAVAILABLE", total_tracks: 0,
    source: "OFFLINE_BROWSER_FIXTURE"})};
};
}'''


def digest(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def execute(repo: Path, css_path: Path, chromium: Path, screenshots: Path | None) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright
    js_path = repo / 'static/truth-cop.js'
    css, js = css_path.read_bytes(), js_path.read_bytes()
    results = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=str(chromium), headless=True)
        browser_version = browser.version
        try:
            for name, width, height, zoom, motion, colors in CASES:
                context = browser.new_context(viewport={'width': width, 'height': height},
                    reduced_motion=motion, forced_colors=colors, service_workers='block')
                attempts = []

                def reject_request(route):
                    attempts.append({'url': route.request.url, 'method': route.request.method})
                    route.abort()

                context.route('**/*', reject_request)
                errors = []
                row = {'case': name, 'width': width, 'height': height, 'css_zoom': zoom, 'failures': []}
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                try:
                    page.set_content(FIXTURE)
                    page.add_style_tag(content=css.decode()).evaluate('e=>e.id="szl-obsidian-signal-killinchu"')
                    page.evaluate(FETCH_FIXTURE)
                    page.add_script_tag(content=js.decode())
                    page.wait_for_selector('.szl-family-identity', timeout=5000)
                    if zoom != 1:
                        page.evaluate('z=>document.documentElement.style.zoom=String(z)', zoom)
                    page.wait_for_function('document.documentElement.dataset.killinchuTrackMode === "UNAVAILABLE"')
                    identity = page.locator('.szl-family-identity')
                    rect = identity.bounding_box()
                    row['identity_rect'] = rect
                    row['identity_css_dimensions'] = {'width': round(rect['width']/zoom, 3), 'height': round(rect['height']/zoom, 3)}
                    if min(rect['width']/zoom, rect['height']/zoom) < 44:
                        row['failures'].append('identity below 44 CSS pixels')
                    row['links'] = page.locator('#szl-family-rail a').evaluate_all(
                        'els=>els.map(e=>({text:e.textContent.trim(),href:e.getAttribute("href"),label:e.getAttribute("aria-label")}))')
                    if len(row['links']) != 8:
                        row['failures'].append('navigation link set changed')
                    # Exercise keyboard order and pointer hit-testing, not CSS markers alone.
                    page.keyboard.press('Tab')
                    if not identity.evaluate('e=>e===document.activeElement'):
                        row['failures'].append('keyboard entry not identity')
                    outline = identity.evaluate('e=>({style:getComputedStyle(e).outlineStyle,width:getComputedStyle(e).outlineWidth})')
                    if outline['style'] in ('none', 'hidden') or float(outline['width'].removesuffix('px')) < 1:
                        row['failures'].append('focus indicator absent')
                    row['keyboard_order_verified'] = True
                    for index in range(1, 8):
                        page.keyboard.press('Tab')
                        if not page.locator('#szl-family-rail a').nth(index).evaluate('e=>e===document.activeElement'):
                            row['keyboard_order_verified'] = False
                            row['failures'].append('keyboard order: ' + str(index))
                    row['pointer_targets'] = []
                    for index in range(8):
                        link = page.locator('#szl-family-rail a').nth(index)
                        link.scroll_into_view_if_needed(timeout=5000)
                        info = link.evaluate('''e=>{const r=e.getBoundingClientRect();
                            const x=Math.max(0,r.left)+Math.min(r.width,innerWidth-Math.max(0,r.left))/2;
                            const y=r.top+r.height/2;const h=document.elementFromPoint(x,y);
                            return {width:r.width,height:r.height,hit:h===e||e.contains(h)};}''')
                        row['pointer_targets'].append(info)
                        if min(info['width']/zoom, info['height']/zoom) < 44 or not info['hit']:
                            row['failures'].append('target geometry or obstruction: ' + str(index))
                    row['overflow_css_px'] = page.evaluate('Math.max(0,document.documentElement.scrollWidth-innerWidth)')
                    if row['overflow_css_px'] > 1:
                        row['failures'].append('document horizontal overflow')
                    row['fixture_calls'] = page.evaluate('window.__fixtureCalls')
                    if any(c['url'] != '/api/killinchu/v1/threats/active' or c['method'] != 'GET' for c in row['fixture_calls']):
                        row['failures'].append('unexpected product request')
                    row['operational_mode'] = page.evaluate('document.documentElement.dataset.killinchuTrackMode')
                    row['page_errors'] = errors
                    row['attempted_network'] = attempts
                    if errors:
                        row['failures'].append('uncaught page error')
                    if attempts:
                        row['failures'].append('unexpected network attempt')
                    if screenshots and name in ('phone-320', 'tablet-768', 'css-zoom-400'):
                        screenshots.mkdir(parents=True, exist_ok=True)
                        page.evaluate('scrollTo(0,0)')
                        page.screenshot(path=str(screenshots / (name + '.png')))
                except Exception as exc:
                    row['failures'].append(type(exc).__name__ + ': ' + str(exc)[:400])
                finally:
                    context.close()
                row['pass'] = not row['failures']
                results.append(row)
        finally:
            browser.close()
    return {'schema': 'szl.killinchu-family-browser/v1', 'observed_at': datetime.now(timezone.utc).isoformat(),
        'scope': 'OFFLINE_COMPONENT_ONLY', 'browser': browser_version, 'python': sys.version.split()[0],
        'source_sha256': {'css': digest(css), 'product_controller': digest(js)},
        'network_allowed': False, 'api_fixture': 'UNAVAILABLE', 'native_browser_zoom_tested': False,
        'production_acceptance': False, 'case_count': len(results),
        'pass': all(r['pass'] for r in results), 'results': results}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--css', type=Path)
    p.add_argument('--chromium', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--screenshots', type=Path)
    args = p.parse_args()
    report = execute(args.repo, args.css or args.repo / 'static/szl-obsidian-signal.css', args.chromium, args.screenshots)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': sum(r['pass'] for r in report['results']), 'total': report['case_count'], 'pass': report['pass']}))
    return 0 if report['pass'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
