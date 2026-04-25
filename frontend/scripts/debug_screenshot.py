"""Debug: see what actually renders on the page."""
from playwright.sync_api import sync_playwright
import os

OUT = os.path.join(os.environ.get("TEMP", "/tmp"), "talugpt-shots")
os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()

    # Console + page errors
    page.on("console", lambda m: print("CONSOLE", m.type, m.text))
    page.on("pageerror", lambda e: print("PAGEERROR", e))

    page.goto("http://localhost:3000/", wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)

    page.screenshot(path=os.path.join(OUT, "debug.png"), full_page=False)
    print("screenshot ->", os.path.join(OUT, "debug.png"))
    print("title:", page.title())
    print("body innerText (first 500):", page.evaluate("() => document.body.innerText.slice(0, 500)"))
    print("body innerHTML length:", page.evaluate("() => document.body.innerHTML.length"))
    print("header exists?", page.evaluate("() => !!document.querySelector('header.app-header')"))
    print("brand-mark exists?", page.evaluate("() => !!document.querySelector('.brand-mark')"))
    print("Loading visible?", page.evaluate("() => document.body.innerText.includes('Laen')"))
    browser.close()
