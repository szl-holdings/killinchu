#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Render the root landing against local UNAVAILABLE fixtures; no operation runs.

CHROME_PATH selects an installed Chromium. --output records browser evidence.
The shipped landing and its assets are served locally. All other requests are
intercepted; the result is presentation evidence, not production readiness.
"""
import argparse
import hashlib
import json
import mimetypes
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 390, 768, 1280, 1920)


class StaticHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ('/', '/landing.html'):
            file = ROOT / 'static/landing.html'
        elif path.startswith('/static/'):
            file = ROOT / path.lstrip('/')
        elif path.startswith('/vendor/'):
            file = ROOT / 'static-vendor' / path.removeprefix('/vendor/')
        else:
            file = ROOT / '__missing__'
        if not file.resolve().is_relative_to(ROOT) or not file.is_file():
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', mimetypes.guess_type(file)[0] or 'application/octet-stream')
        self.end_headers()
        self.wfile.write(file.read_bytes())


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), StaticHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = 'http://127.0.0.1:' + str(server.server_port)
    checks, errors, requests, layouts = [], [], [], []

    def check(name, passed, detail=None):
        checks.append({'name': name, 'passed': bool(passed), 'detail': detail})

    def intercept(route):
        request = route.request
        path = urlsplit(request.url).path
        local = request.url.startswith(origin + '/')
        if local and request.method == 'GET' and (path in ('/', '/landing.html') or path.startswith(('/static/', '/vendor/'))):
            route.continue_()
            return
        requests.append({'path': path, 'method': request.method, 'local': local})
        route.fulfill(status=503, content_type='application/json', body=json.dumps(
            {'state': 'UNAVAILABLE', 'mode': 'UNAVAILABLE', 'source': 'LOCAL TEST FIXTURE'}))

    try:
        with sync_playwright() as controller:
            browser = controller.chromium.launch(executable_path=os.environ.get('CHROME_PATH'), headless=True,
                args=['--disable-dev-shm-usage', '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
            context = browser.new_context(viewport={'width': 1280, 'height': 1100}, reduced_motion='reduce',
                                          color_scheme='dark', service_workers='block')
            context.route('**/*', intercept)
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin + '/', wait_until='load')
            page.locator('#szl-family-rail').wait_for()
            page.keyboard.press('Tab')
            check('skip precedes injected family navigation', page.locator('.landing-skip').evaluate('e=>e===document.activeElement'))
            page.keyboard.press('Enter')
            check('skip focuses main content', page.locator('#main-content').evaluate('e=>e===document.activeElement'))
            for width in WIDTHS:
                page.set_viewport_size({'width': width, 'height': 1100})
                page.evaluate('document.activeElement?.blur();scrollTo(0,0)')
                page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                layout = page.evaluate("""() => ({viewport:innerWidth,document:document.documentElement.scrollWidth,
                  main:document.querySelectorAll('main').length,h1:document.querySelectorAll('h1').length,
                  controls:[...document.querySelectorAll('.cta a,.card__foot a,.foot__links a,.brand,.szl-family-link')].map(e=>{
                    const r=e.getBoundingClientRect();return {text:e.textContent.trim(),width:r.width,height:r.height};}),
                  cardOverflow:[...document.querySelectorAll('.card')].filter(e=>e.scrollWidth>e.clientWidth+1).length,
                  marks:[...document.querySelectorAll('.brand__mark,.szl-family-mark')].map(e=>({ready:e.complete&&e.naturalWidth>0,path:e.getAttribute('src')})),
                  motion:getComputedStyle(document.documentElement).scrollBehavior,
                  note:getComputedStyle(document.querySelector('.hero__note')).color})""")
                layouts.append(layout)
                check(f'{width}/document fits viewport', layout['document'] <= width + 1, layout)
                check(f'{width}/one main and one heading', layout['main'] == 1 and layout['h1'] == 1)
                check(f'{width}/controls have44px targets', all(row['width'] >= 43.99 and row['height'] >= 43.99 for row in layout['controls']), layout['controls'])
                check(f'{width}/card contents stay inside their surfaces', layout['cardOverflow'] == 0)
                check(f'{width}/canonical marks load', len(layout['marks']) == 2 and all(row['ready'] for row in layout['marks']), layout['marks'])
                check(f'{width}/reduced motion stops smooth scrolling', layout['motion'] == 'auto')
                if width in (320, 1280):
                    page.screenshot(path=str(output / f'landing-{width}.png'), timeout=60000)
            page.set_viewport_size({'width': 1280, 'height': 1100})
            colors = page.evaluate("""() => {
              const canvas=document.createElement('canvas'),x=canvas.getContext('2d');
              function rgba(value){x.clearRect(0,0,1,1);x.fillStyle=value;x.fillRect(0,0,1,1);return [...x.getImageData(0,0,1,1).data];}
              function luminance(rgb){return rgb.slice(0,3).map(v=>v/255).map(v=>v<=.04045?v/12.92:((v+.055)/1.055)**2.4).reduce((s,v,i)=>s+v*[.2126,.7152,.0722][i],0);}
              function background(node){if(!node)return [0,0,0];const value=rgba(getComputedStyle(node).backgroundColor),a=value[3]/255;
                return a>=1?value:background(node.parentElement).map((v,i)=>value[i]*a+v*(1-a));}
              return ['.hero__note','.tele__head','.card__eyebrow','.foot__line','.szl-family-copy small','.btn--primary'].map(selector=>{
                const e=document.querySelector(selector),fg=rgba(getComputedStyle(e).color),bg=background(e),f=luminance(fg),b=luminance(bg);
                return {selector,fg,bg,ratio:(Math.max(f,b)+.05)/(Math.min(f,b)+.05)};});
            }""")
            for row in colors:
                check(row['selector'] + '/text contrast >=4.5', row['ratio'] >= 4.5, row)
            primary = page.locator('.btn--primary').first
            primary.focus()
            check('primary keyboard focus is visible', primary.evaluate('e=>parseFloat(getComputedStyle(e).outlineWidth)>=2'))
            check('effector and detector limitations remain visible', page.locator('#szl-kanchay-honesty').is_visible() and
                  all(text in page.locator('#szl-kanchay-honesty').inner_text() for text in ('SIMULATED', 'Waman', 'no weights', 'frames SKIP', 'Conjecture 1')))
            check('unavailable fixtures stay unavailable', page.locator('#tSvc').inner_text() == 'UNAVAILABLE' and page.locator('#killinchu-track-truth').inner_text().startswith('UNAVAILABLE'))
            page.locator('.foot').screenshot(path=str(output / 'landing-footer.png'), timeout=60000)
            page.emulate_media(forced_colors='active')
            check('forced colors follows user canvas', page.locator('body').evaluate('e=>getComputedStyle(e).backgroundImage') == 'none')
            context.close()
            static_context = browser.new_context(java_script_enabled=False, viewport={'width': 320, 'height': 1100})
            static_context.route('**/*', intercept)
            static_page = static_context.new_page()
            static_page.goto(origin + '/', wait_until='load')
            static_page.keyboard.press('Tab')
            check('skip works without JavaScript', static_page.locator('.landing-skip').evaluate('e=>e===document.activeElement'))
            check('no-JavaScript view keeps caveats', 'SIMULATED' in static_page.locator('.hero__note').inner_text())
            browser.close()
    except Exception as error:
        errors.append(str(error))
    finally:
        server.shutdown()
        check('all intercepted requests are reads', bool(requests) and all(row['method'] == 'GET' for row in requests))
        files = ('static/landing.html', 'static/truth-cop.js', 'static/szl-obsidian-signal.css',
                 'static/szl/SOURCE.json', 'static/szl/logos/szl_logo_mono_white.svg', 'tools/verify_landing_browser.py')
        report = {'source': 'LOCAL UNAVAILABLE FIXTURES; no production calls or readiness claim',
                  'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  'file_sha256': {file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest() for file in files},
                  'checks': checks, 'errors': errors, 'layouts': layouts, 'requests': requests}
        (output / 'landing-browser-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    failures = [row for row in checks if not row['passed']]
    print(json.dumps({'checks': len(checks), 'failures': failures, 'errors': errors}))
    return bool(failures or errors)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
