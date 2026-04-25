"""Capture screenshots of the redesigned TaluGPT map for visual verification."""
from playwright.sync_api import sync_playwright
import os, sys

OUT_DIR = os.path.join(os.environ.get("TEMP", "/tmp"), "talugpt-shots")
os.makedirs(OUT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # Desktop view
    desktop = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    page = desktop.new_page()
    page.goto("http://localhost:3000/", wait_until="networkidle", timeout=60000)
    # Wait for map markers to be drawn
    # Wait for the React app shell + leaflet container; tiles may be blocked in sandbox.
    page.wait_for_selector("header.app-header .brand-mark", timeout=20000)
    page.wait_for_selector("#map.leaflet-container", timeout=20000)
    page.wait_for_timeout(3500)
    page.screenshot(path=os.path.join(OUT_DIR, "01-desktop.png"), full_page=False)
    print("desktop ->", os.path.join(OUT_DIR, "01-desktop.png"))

    # Open a popup by clicking near the center of the canvas (where farms cluster in Estonia)
    try:
        canvas = page.locator(".leaflet-pane canvas").first
        box = canvas.bounding_box()
        if box:
            # Click on a few candidate spots to hit a marker
            for dx, dy in [(0.55, 0.55), (0.45, 0.45), (0.6, 0.5), (0.5, 0.6)]:
                page.mouse.click(box["x"] + box["width"] * dx, box["y"] + box["height"] * dy)
                try:
                    page.wait_for_selector(".leaflet-popup-content", timeout=1500)
                    break
                except Exception:
                    continue
            page.wait_for_timeout(400)
            page.screenshot(path=os.path.join(OUT_DIR, "02-popup.png"), full_page=False)
            print("popup ->", os.path.join(OUT_DIR, "02-popup.png"))
    except Exception as e:
        print("popup capture skipped:", e, file=sys.stderr)

    # Apply a filter to show the active state
    try:
        # Click a kind filter button
        page.locator(".filter-grid button:has-text('Talu')").first.click()
        page.wait_for_timeout(800)
        page.screenshot(path=os.path.join(OUT_DIR, "03-filter-active.png"), full_page=False)
        print("filter ->", os.path.join(OUT_DIR, "03-filter-active.png"))
    except Exception as e:
        print("filter capture skipped:", e, file=sys.stderr)

    # Mobile / sidebar collapsed view
    mobile = browser.new_context(viewport={"width": 414, "height": 800}, device_scale_factor=2)
    page2 = mobile.new_page()
    page2.goto("http://localhost:3000/", wait_until="networkidle", timeout=60000)
    page2.wait_for_selector("header.app-header .brand-mark", timeout=20000)
    page2.wait_for_timeout(2500)
    page2.screenshot(path=os.path.join(OUT_DIR, "04-mobile.png"), full_page=False)
    print("mobile ->", os.path.join(OUT_DIR, "04-mobile.png"))

    browser.close()

print("DONE. Files in:", OUT_DIR)
