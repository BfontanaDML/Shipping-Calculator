"""Browser check of the employee screen (optional; needs Playwright + Chromium).

    pip install playwright && python -m playwright install chromium
    python tests/ui_check.py              # screenshots go to ./ui_check_screenshots/ (git-ignored)

Starts the app on a free local port, drives a real browser at desktop and phone
widths, and checks what an employee sees.
"""
import logging
import os
import re
import socket
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from werkzeug.serving import make_server  # noqa: E402
from playwright.sync_api import sync_playwright  # noqa: E402

from app import create_app  # noqa: E402

SHOTS = os.environ.get("UI_SHOTS_DIR") or os.path.join(ROOT, "ui_check_screenshots")
RESULTS = []
EXPECTED_USER_ID = "UPSMPDM"
EXPECTED_PASSWORD = "Creation11"
FORBIDDEN = ("UPS service cost", "fuel surcharge", "Quote details", "Customer summary", "Internal detail", "Alternative", "service name", "Non-air", "Non Air",
             "DML cost", "40%", "0.60", "DML discount", "markup", "$75", "freight", "Weight guidance is for UPS non-air", "÷ 139", "EK64", "TK3")
ZERO_PRICE = re.compile(r"\$0\.00(?!\d)")
DECIMAL_DIM = re.compile(r"\d+(?:\.\d+)?\s*×\s*\d+(?:\.\d+)?\s*×\s*\d+(?:\.\d+)?")


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + ((" - " + str(detail)) if detail and not cond else ""))


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def run_flow(browser, base, width, height, tag):
    page = browser.new_page(viewport={"width": width, "height": height})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    # 400s are expected when the test types an invalid quantity on purpose
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" and "400" not in m.text else None)
    page.goto(base)

    def wait():
        page.wait_for_timeout(800)

    def total():
        return page.locator("#r-total").inner_text()

    def no_forbidden(label):
        t = page.locator("body").inner_text()
        bad = [f for f in FORBIDDEN if f.lower() in t.lower()] + (["$0.00"] if ZERO_PRICE.search(t) else [])
        check("%s: no removed/forbidden text (%s)" % (tag, label), not bad, bad)
        check("%s: no decimal box dimensions (%s)" % (tag, label),
              not any("." in m.group(0) for m in DECIMAL_DIM.finditer(t)))

    names = page.locator("#product label").all_inner_texts()
    check("%s: products Caps, Toques, EK9, EK12, EK60" % tag, names == ["Caps", "Toques", "EK9", "EK12", "EK60"], names)
    svcs = page.locator("#service label").all_inner_texts()
    check("%s: services UPS World Ease Standard / UPS Worldwide Expedited/Saver" % tag,
          svcs == ["UPS World Ease Standard", "UPS Worldwide Expedited/Saver"], svcs)
    order = page.evaluate("""[...document.querySelectorAll('#product, #quantity, #service')].map(e => e.id)""")
    check("%s: order is product, quantity, service" % tag, order == ["product", "quantity", "service"], order)
    check("%s: no service-name text field" % tag, page.locator("#service-label").count() == 0)
    check("%s: opens directly, no sign-in" % tag, page.locator("#product").is_visible())
    check("%s: empty screen shows no price" % tag, total() == "—")
    check("%s: no error messages before input" % tag, page.locator(".err:not(:empty)").count() == 0)
    no_forbidden("empty")
    page.screenshot(path=os.path.join(SHOTS, "%s-1-empty.png" % tag), full_page=True)

    # ---- $100 -> $125 example: World Ease Standard, Caps 150 ----
    page.click("label[for=product-caps]")
    page.fill("#quantity", "150")
    page.click("label[for=service-world_ease_standard]")
    wait()
    rows = page.locator("#boxes tbody tr")
    check("%s: Caps 150 -> 2 suggested rows (fewest boxes)" % tag, rows.count() == 2, rows.count())
    r0 = rows.nth(0)
    check("%s: row shows box count, dims, pieces, dim + quote weight" % tag,
          r0.locator("[data-f=count]").input_value() == "1"
          and r0.locator("select option:checked").inner_text() == "24 × 19 × 20"
          and r0.locator("[data-f=pieces]").input_value() == "144"
          and r0.locator("td.dim").inner_text() == "66 lb" and r0.locator("td.qw").inner_text().startswith("66 lb"))
    check("%s: rates not entered -> no price" % tag, total() == "—")
    check("%s: exactly one UPS price field" % tag, page.locator(".price-row input").count() == 1
          and page.locator("label[for=ups-total]").inner_text() == "Discounted UPS Total Cost (CAD)")
    page.locator("#ups-total").focus()
    page.locator("#ups-total").blur()
    wait()
    check("%s: empty UPS Total Cost -> concise inline error, no price" % tag,
          page.locator('[data-err="ups_total_cost"]').inner_text() == "Enter the discounted UPS total cost." and total() == "—")
    page.fill("#ups-total", "0")
    wait()
    check("%s: $0 total rejected beside the field" % tag,
          page.locator('[data-err="ups_total_cost"]').inner_text() == "Must be more than $0." and total() == "—")

    # ---- How to Get Shipping Prices ----
    howto = page.locator("#howto")
    check("%s: instructions closed by default" % tag, howto.get_attribute("open") is None
          and not page.locator("#howto ol").is_visible())
    page.click("#howto summary")
    page.wait_for_timeout(200)
    steps = page.locator("#howto ol > li")
    check("%s: instructions open with 8 steps" % tag, page.locator("#howto ol").is_visible() and steps.count() == 8, steps.count())
    check("%s: step 6 is the UPS account number step" % tag,
          steps.nth(5).inner_text() == "Under How will you pay the shipping charges?, choose DML’s UPS account number from "
                                       "the Select a UPS Account Number dropdown, then click Update."
          and steps.nth(4).inner_text().startswith("Enter every package from Step 2")
          and steps.nth(6).inner_text().startswith("Select the UPS service chosen in Step 1")
          and steps.nth(7).inner_text().startswith("Copy the discounted Total Cost"))
    link = page.locator("#howto a")
    check("%s: UPS link opens in new tab" % tag, link.inner_text() == "Open the UPS website"
          and link.get_attribute("href").startswith("https://www.ups.com/lasso/login?returnto=")
          and link.get_attribute("target") == "_blank")
    check("%s: DML UPS login shown in step 1" % tag,
          page.locator("#ups-user").inner_text() == EXPECTED_USER_ID
          and page.locator("#ups-pass").inner_text() == EXPECTED_PASSWORD)  # no detail: never print the password
    check("%s: steps: Cap America origin, $1 customs, every package, copy discounted Total Cost" % tag,
          all(x in page.locator("#howto").inner_text() for x in ("Cap America", "$1", "Enter every package from Step 2",
                                                                "Copy the discounted Total Cost for the complete shipment into Step 3")))
    page.screenshot(path=os.path.join(SHOTS, "%s-2b-howto-open.png" % tag), full_page=True)
    page.click("#howto summary")
    page.wait_for_timeout(200)
    check("%s: instructions close again" % tag, not page.locator("#howto ol").is_visible())

    page.fill("#ups-total", "100")
    wait()
    check("%s: UPS Total Cost $100 -> Customer Shipping Price $125.00 CAD" % tag, total() == "$125.00 CAD", total())
    check("%s: Shipping Price Per Piece $0.83 (125 / 150)" % tag, page.locator("#r-piece").inner_text() == "$0.83")
    check("%s: only the two pricing results are shown" % tag, page.locator(".results .result").count() == 2
          and page.locator(".results").inner_text().count("$") == 2)
    check("%s: no calculation shown (no $100 / $25 / x1.25 on screen)" % tag,
          all(x not in page.locator("main").inner_text().replace(page.locator("#howto").inner_text(), "")
              for x in ("$100.00", "$25.00", "1.25", "×1.25")))
    check("%s: totals line" % tag, page.locator("#totals").inner_text() == "2 boxes · 150 of 150 pcs · 72 lb quote weight",
          page.locator("#totals").inner_text())
    no_forbidden("priced")
    page.screenshot(path=os.path.join(SHOTS, "%s-2-standard-priced.png" % tag), full_page=True)

    # ---- overrides: pieces, box size, measured weight, rows ----
    rows.nth(1).locator("[data-f=pieces]").fill("5")
    wait()
    check("%s: unassigned piece shown beside totals, no price" % tag,
          page.locator('[data-err="packing"]').inner_text() == "1 piece not in a box." and total() == "—")
    rows.nth(1).locator("[data-f=pieces]").fill("7")
    wait()
    check("%s: over-capacity error beside the field" % tag,
          rows.nth(1).locator('[data-row-err="pieces"]').inner_text() == "Max 6 per box.")
    rows.nth(1).locator("select").select_option("catalog_13x11x7")
    rows.nth(1).locator("[data-f=pieces]").fill("6")
    wait()
    check("%s: changed box size accepted (13 × 11 × 7 = 8 lb)" % tag,
          rows.nth(1).locator("td.dim").inner_text() == "8 lb" and total() == "$125.00 CAD")
    rows.nth(0).locator("[data-f=measured]").fill("58.5")
    wait()
    check("%s: low measured weight keeps 66 lb quote weight" % tag, rows.nth(0).locator("td.qw").inner_text().startswith("66 lb"))
    rows.nth(0).locator("[data-f=measured]").fill("70.2")
    wait()
    check("%s: heavy measured weight -> 71 lb quote weight" % tag,
          rows.nth(0).locator("td.qw").inner_text().startswith("71 lb") and "79 lb quote weight" in page.locator("#totals").inner_text(),
          page.locator("#totals").inner_text())
    rows.nth(0).locator("[data-f=measured]").fill("abc")
    wait()
    check("%s: bad measured weight -> inline error, no price" % tag,
          rows.nth(0).locator('[data-row-err="measured"]').inner_text() != "" and total() == "—")
    rows.nth(0).locator("[data-f=measured]").fill("")
    rows.nth(0).locator("[data-f=count]").fill("2")
    wait()
    check("%s: box count edit -> 144 pieces too many" % tag, page.locator('[data-err="packing"]').inner_text() == "144 pieces too many.",
          page.locator('[data-err="packing"]').inner_text())
    page.click("#add-row")
    wait()
    check("%s: add row" % tag, page.locator("#boxes tbody tr").count() == 3)
    page.locator("#boxes tbody tr").nth(2).locator("[data-act=remove]").click()
    page.click("#reset-rows")
    wait()
    check("%s: reset to suggestion" % tag, page.locator("#boxes tbody tr").count() == 2 and total() == "$125.00 CAD")

    # ---- UPS Worldwide Expedited/Saver ----
    page.click("label[for=service-worldwide_expedited_saver]")
    wait()
    check("%s: service change clears UPS Total Cost" % tag, page.locator("#ups-total").input_value() == "" and total() == "—")
    check("%s: Expedited hides calculated weights" % tag, not page.locator("#boxes td.dim").first.is_visible()
          and not page.locator("#boxes td.qw").first.is_visible() and "quote weight" not in page.locator("#totals").inner_text())
    check("%s: Expedited keeps packing + measured weight input" % tag,
          page.locator("#boxes tbody tr").count() == 2 and page.locator("#boxes [data-f=measured]").first.is_visible())
    check("%s: Expedited short inline note" % tag,
          page.locator("#weight-hint").inner_text() == "Expedited/Saver: use the billable weight from the UPS quote.")
    page.fill("#ups-total", "100")
    wait()
    check("%s: Expedited $100 -> $125.00" % tag, total() == "$125.00 CAD")
    no_forbidden("expedited")
    page.screenshot(path=os.path.join(SHOTS, "%s-3-expedited.png" % tag), full_page=True)
    page.click("label[for=service-world_ease_standard]")
    wait()

    # ---- all five products ----
    for pid, qty, first in (("toques", "500", "24 × 19 × 20"), ("ek9", "40", "24 × 10 × 14"), ("ek12", "18", "23 × 9 × 7"),
                            ("ek60", "30000", "24 × 19 × 20"), ("caps", "7", "13 × 11 × 7")):
        page.click("label[for=product-%s]" % pid)
        page.fill("#quantity", qty)
        wait()
        page.fill("#ups-total", "100")
        wait()
        r = page.locator("#boxes tbody tr").nth(0)
        got = r.locator("select option:checked").inner_text()
        check("%s: %s %s -> %s, $125.00" % (tag, pid, qty, first), got == first and total() == "$125.00 CAD", (got, total()))
        if pid == "ek60":
            check("%s: EK60 30,000 grouped as 555 + 1 boxes" % tag,
                  page.locator("#boxes tbody tr").count() == 2 and r.locator("[data-f=count]").input_value() == "555"
                  and page.locator("#totals").inner_text().startswith("556 boxes · 30,000 of 30,000 pcs"),
                  page.locator("#totals").inner_text())
            check("%s: EK60 per piece $0.0042" % tag, page.locator("#r-piece").inner_text() == "$0.0042")
            opts = " ".join(r.locator("select option").all_inner_texts())
            check("%s: EK60 blocked boxes not offered" % tag, "13 × 11 × 7" not in opts and "11 × 9 × 8" not in opts, opts)
            no_forbidden("EK60 30,000")
            page.screenshot(path=os.path.join(SHOTS, "%s-4-ek60-30000.png" % tag), full_page=True)

    # ---- invalid quantity ----
    page.fill("#quantity", "abc")
    wait()
    check("%s: invalid quantity -> inline error, no price" % tag,
          "whole number" in page.locator('[data-err="quantity"]').inner_text() and total() == "—")
    page.fill("#quantity", "0")
    wait()
    check("%s: zero quantity rejected" % tag, "at least 1" in page.locator('[data-err="quantity"]').inner_text())

    sw = page.evaluate("document.documentElement.scrollWidth")
    check("%s: no horizontal page scroll" % tag, sw <= width, sw)
    check("%s: no browser console errors" % tag, not errors, errors)
    page.close()


def main():
    os.makedirs(SHOTS, exist_ok=True)
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    port = free_port()
    # No UPS environment variables: the login is part of the instructions (v1.4.0).
    os.environ.pop("UPS_LOGIN_USER_ID", None)
    os.environ.pop("UPS_LOGIN_PASSWORD", None)
    server = make_server("127.0.0.1", port, create_app())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:%d/" % port
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROMIUM_PATH") or None)
        run_flow(browser, base, 1280, 900, "desktop")
        run_flow(browser, base, 390, 844, "phone")
        browser.close()
    server.shutdown()
    failed = [r for r in RESULTS if not r[1]]
    print("\n%d checks, %d failed" % (len(RESULTS), len(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
