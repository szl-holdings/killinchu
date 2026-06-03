import sys
from playwright.sync_api import sync_playwright

OUT = "/home/user/workspace/team/killinchu-closeout"
URL = "http://127.0.0.1:7863/console"

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox", "--use-gl=swiftshader", "--enable-webgl"])
    # Desktop
    ctx = b.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    pg = ctx.new_page()
    msgs = []
    pg.on("console", lambda m: msgs.append(m.text))
    pg.goto(URL, wait_until="domcontentloaded", timeout=30000)
    pg.wait_for_timeout(7000)
    pg.screenshot(path=f"{OUT}/console_desktop.png")
    print("desktop done; console msgs:", msgs[:8])
    ctx.close()
    # Mobile
    ctx2 = b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=3, is_mobile=True)
    pg2 = ctx2.new_page()
    pg2.goto(URL, wait_until="domcontentloaded", timeout=30000)
    pg2.wait_for_timeout(7000)
    pg2.screenshot(path=f"{OUT}/console_mobile.png", full_page=True)
    print("mobile done")
    ctx2.close()
    b.close()
