"""Optional HTML UI check using Playwright and an installed Edge browser; local files only."""

import argparse
import json
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def check(report: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    errors, requests = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge", headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.on("request", lambda request: requests.append(request.url))
            page.goto(report.resolve().as_uri())
            visible = page.locator(".candidate:visible")
            expect(visible).to_have_count(13)
            page.locator("#search").fill("swagger")
            expect(visible).to_have_count(1)
            page.locator("#reset").click()
            page.locator("#category").select_option("HIGH")
            expect(visible).to_have_count(1)
            page.locator("#reset").click()
            page.locator("#status").select_option("403")
            expect(visible).to_have_count(1)
            page.locator("#engine").select_option("local-demo")
            expect(visible).to_have_count(1)
            page.locator("#media").select_option("application/json")
            expect(visible).to_have_count(0)
            page.locator("#reset").click()
            page.locator("#media").select_option("application/json")
            expect(visible).to_have_count(3)
            page.locator("#reset").click()
            page.locator("#noise").check()
            expect(visible).to_have_count(35)
            cluster = page.locator("details.cluster").filter(has_text="20 endpoints").first
            cluster.locator(":scope > summary").click()
            cluster.get_by_role("button", name="Browse members").click()
            expect(visible).to_have_count(20)
            page.locator("#reset").click()
            page.get_by_text("100 GET /admin/export", exact=False).first.click()
            expect(page.get_by_text("Evidence support:", exact=False).first).to_be_visible()
            expect(
                page.get_by_role("heading", name="Provenance · 1 observations").first
            ).to_be_visible()
            page.locator("#queue").scroll_into_view_if_needed()
            page.screenshot(path=str(output / "desktop.png"))
            page.set_viewport_size({"width": 390, "height": 844})
            page.locator("#reset").click()
            page.evaluate("window.scrollTo(0, 0)")
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
            page.screenshot(path=str(output / "mobile.png"))
            assert not errors, errors
            assert all(url.startswith("file:") for url in requests), requests
            result = {
                "status": "PASS",
                "javascript_errors": errors,
                "requests": len(requests),
                "external_requests": 0,
                "filters_checked": 7,
                "checks": [
                    "search",
                    "priority",
                    "status",
                    "engine",
                    "content_type",
                    "noise",
                    "cluster",
                    "reset",
                    "endpoint_details",
                    "mobile_width",
                ],
            }
            (output / "result.json").write_text(json.dumps(result, indent=2))
            print(json.dumps(result, indent=2))
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    check(args.report, args.output)
