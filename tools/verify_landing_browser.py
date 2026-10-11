#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
# (c) 2026 Lutar, Stephen P. - SZL Holdings - ORCID 0009-0001-0110-4173
"""Render the root landing against local UNAVAILABLE fixtures; no operation runs.

CHROME_PATH selects an installed Chromium. --output records browser evidence.
The shipped landing is composed through its actual four HTML middleware layers
without starting the operational application. Assets are served locally. All
other browser requests are intercepted; this does not establish readiness.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from landing_presentation_fixture import rendered_landing

WIDTHS = (320, 390, 768, 1280, 1920)
MEDIA_TYPES = {'.html':'text/html', '.css':'text/css', '.js':'application/javascript', '.json':'application/json',
               '.svg':'image/svg+xml', '.png':'image/png', '.jpg':'image/jpeg', '.jpeg':'image/jpeg',
               '.woff':'font/woff', '.woff2':'font/woff2'}


class StaticHandler(BaseHTTPRequestHandler):
    landing = b''
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
        self.send_header('Content-Type', MEDIA_TYPES.get(file.suffix.lower(), 'application/octet-stream'))
        self.end_headers()
        self.wfile.write(self.landing if path in ('/', '/landing.html') else file.read_bytes())


def run(output):
    output.mkdir(parents=True, exist_ok=True)
    StaticHandler.landing = rendered_landing()
    server = ThreadingHTTPServer(('127.0.0.1', 0), StaticHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    origin = 'http://127.0.0.1:' + str(server.server_port)
    checks, errors, requests, layouts, sockets = [], [], [], [], []

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
            context.route_web_socket('**/*', lambda ws: (sockets.append(ws.url), ws.close()))
            page = context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(origin + '/', wait_until='load')
            page.locator('#szl-family-rail').wait_for()
            page.keyboard.press('Tab')
            check('skip precedes server and client navigation', page.locator('.landing-skip').evaluate('e=>e===document.activeElement'))
            page.keyboard.press('Enter')
            check('skip focuses main content', page.locator('#main-content').evaluate('e=>e===document.activeElement'))
            check('capability disclosure starts closed', not page.locator('.landing-capabilities').evaluate('e=>e.open'))
            for width in WIDTHS:
                page.set_viewport_size({'width': width, 'height': 1100})
                if not page.locator('.landing-capabilities').evaluate('e=>e.open'):
                    page.locator('.landing-capabilities > summary').focus()
                    page.keyboard.press('Enter')
                check(f'{width}/capability disclosure opens with the keyboard', page.locator('.landing-capabilities').evaluate('e=>e.open'))
                page.evaluate('document.activeElement?.blur();scrollTo(0,0)')
                page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                layout = page.evaluate("""() => ({viewport:innerWidth,document:document.documentElement.scrollWidth,
                  main:document.querySelectorAll('main').length,h1:document.querySelectorAll('h1').length,
                  controls:[...document.querySelectorAll('.cta a,.card__foot a,.foot__links a,.brand,.szl-family-link,.kc-plane-tabs a,.landing-capabilities > summary')].map(e=>{
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
                check(f'{width}/one capability navigation', page.locator('.kc-plane-tabs').count() == 1)
                for link in page.locator('.kc-plane-tabs a').all():
                    link.focus()
                    page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                    check(f'{width}/capability link focus is exposed', link.evaluate('''e=>{
                        const r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
                        return x>=0&&x<=innerWidth&&y>=0&&y<=innerHeight&&e.contains(document.elementFromPoint(x,y));
                    }'''), link.inner_text())
                page.evaluate('document.activeElement?.blur();scrollTo(0,400)')
                page.evaluate('()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))')
                rails = page.locator('.szl-family-rail,.kc-plane-tabs,.topbar').evaluate_all('''es=>es.map(e=>{
                    const r=e.getBoundingClientRect();return {name:e.className,top:r.top,bottom:r.bottom,height:r.height};
                })''')
                visible = [row for row in rails if row['bottom'] > 0 and row['top'] < 1100]
                overlap = [(a['name'], b['name']) for i,a in enumerate(visible) for b in visible[i+1:]
                           if min(a['bottom'], b['bottom']) - max(0, a['top'], b['top']) > 1]
                check(f'{width}/scrolling navigation layers do not overlap', not overlap, rails)
                check(f'{width}/product bar stays available after scrolling', any(row['name'] == 'topbar' and -1 <= row['top'] <= 1 for row in rails), rails)
                if width in (320, 1280):
                    page.screenshot(path=str(output / f'landing-scrolled-{width}.png'), timeout=60000)
                page.evaluate('scrollTo(0,0)')
                page.locator('.landing-capabilities > summary').focus()
                page.keyboard.press('Enter')
                check(f'{width}/capability disclosure closes with the keyboard', not page.locator('.landing-capabilities').evaluate('e=>e.open'))
                page.evaluate('document.activeElement?.blur();scrollTo(0,0)')
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
            static_context.route_web_socket('**/*', lambda ws: (sockets.append(ws.url), ws.close()))
            static_page = static_context.new_page()
            for width in WIDTHS:
                static_page.set_viewport_size({'width': width, 'height': 1100})
                static_page.goto(origin + '/', wait_until='load')
                static_page.keyboard.press('Tab')
                check(f'{width}/server skip works without JavaScript', static_page.locator('.landing-skip').evaluate('e=>e===document.activeElement'))
                static_page.keyboard.press('Enter')
                check(f'{width}/server skip focuses main without JavaScript', static_page.locator('#main-content').evaluate('e=>e===document.activeElement'))
                check(f'{width}/no-JavaScript document fits viewport', static_page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
                static_page.locator('.landing-capabilities > summary').focus()
                static_page.keyboard.press('Enter')
                check(f'{width}/native disclosure opens without JavaScript', static_page.locator('.landing-capabilities').evaluate('e=>e.open'))
                check(f'{width}/native disclosure fits without JavaScript', static_page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
                for link in static_page.locator('.kc-plane-tabs a').all():
                    link.focus()
                    check(f'{width}/capability link is exposed without JavaScript', link.evaluate('''e=>{
                        const r=e.getBoundingClientRect(),x=r.left+r.width/2,y=r.top+r.height/2;
                        return x>=0&&x<=innerWidth&&y>=0&&y<=innerHeight&&e.contains(document.elementFromPoint(x,y));
                    }'''), link.inner_text())
            check('no-JavaScript view keeps caveats', 'SIMULATED' in static_page.locator('.hero__note').inner_text())
            browser.close()
    except Exception as error:
        errors.append(str(error))
    finally:
        server.shutdown()
        check('all intercepted requests are reads', bool(requests) and all(row['method'] == 'GET' for row in requests))
        check('no WebSocket operation was requested', not sockets, sockets)
        files = ('static/landing.html', 'static/truth-cop.js', 'static/szl-obsidian-signal.css',
                 'static/szl/SOURCE.json', 'static/szl/logos/szl_logo_mono_white.svg', 'tools/verify_landing_browser.py',
                 'tools/landing_presentation_fixture.py','serve.py','killinchu_defend_plane.py','killinchu_nav_wireup.py',
                 'static/brand-tokens.css','static/brand-bridge.css','static/public-experience-v4.css',
                 'static-vendor/a11oy-operator-widget.js','static-vendor/a11oy-operator-widget.css','static-vendor/killinchu-restraint-chaski.js')
        report = {'source': 'ACTUAL HTML MIDDLEWARE + LOCAL UNAVAILABLE FIXTURES; operational app not started; no production calls or readiness claim',
                  'base_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                  'file_sha256': {file: hashlib.sha256((ROOT / file).read_bytes()).hexdigest() for file in files},
                  'composed_landing_sha256':hashlib.sha256(StaticHandler.landing).hexdigest(),
                  'checks': checks, 'errors': errors, 'layouts': layouts, 'requests': requests, 'websockets_denied':sockets}
        (output / 'landing-browser-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    failures = [row for row in checks if not row['passed']]
    print(json.dumps({'checks': len(checks), 'failures': failures, 'errors': errors}))
    return bool(failures or errors)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
