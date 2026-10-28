import copy
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app import create_app  # noqa: E402
from shipping.config import Config, ConfigError, DEFAULT_CONFIG_PATH  # noqa: E402

DECIMAL_DIM = re.compile(r"\d+(?:\.\d+)?\s*(?:\u00d7|x)\s*\d+(?:\.\d+)?\s*(?:\u00d7|x)\s*\d+(?:\.\d+)?")


def has_decimal_dims(text):
    """True if any 'L x W x H' triple in the text contains a decimal number."""
    return any("." in m.group(0) for m in DECIMAL_DIM.finditer(text))



class AppTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = create_app().test_client()

    def post(self, path, body):
        return self.client.post(path, data=json.dumps(body), content_type="application/json")

    def get_text(self, path):
        r = self.client.get(path)
        self.assertEqual(r.status_code, 200, path)
        t = r.get_data(as_text=True)
        r.close()
        return t

    def test_pages(self):
        for path in ("/", "/healthz", "/api/config", "/static/app.js", "/static/styles.css"):
            self.get_text(path)
        r = self.client.get("/")
        self.assertIn("Content-Security-Policy", r.headers)
        r.close()
        for gone in ("/data", "/api/evaluate", "/api/record", "/static/data.js"):
            self.assertEqual(self.client.get(gone).status_code, 404, gone)

    def test_health(self):
        d = self.client.get("/healthz").get_json()
        self.assertTrue(d["ok"])
        self.assertEqual(d["app_version"], "1.5.0")

    def test_screen_text(self):
        # Failures print only the phrase checked, never the page (the page contains the UPS login).
        html = self.get_text("/")
        for text in ("Shipment", "Boxes", "Price", "Customer Shipping Price", "Shipping Price Per Piece",
                     "Discounted UPS Total Cost (CAD)", "Quantity", "How to Get Shipping Prices"):
            self.assertTrue(text in html, text)
        self.assertEqual(html.count('id="ups-total"'), 1)  # exactly one UPS price field
        lowered = html.lower()
        for removed in ("ups service cost", "fuel surcharge", "svc-cost", 'id="fuel"',
                        "quote details", "customer summary", "internal detail", "alternative", "service name",
                        "40%", "0.60", "dml discount", "applies a discount", "markup", "dml cost", "freight",
                        "weight guidance is for ups non-air", "÷ 139", "non-air", "box data", "$75"):
            self.assertTrue(removed not in lowered, removed)
        js = self.get_text("/static/app.js").lower()
        for removed in ("alternative", "customer_summary", "internal", "freight", "40%", "0.6", "markup"):
            self.assertTrue(removed not in js, removed)

    def test_config_api(self):
        cfg = self.client.get("/api/config").get_json()
        self.assertEqual([p["name"] for p in cfg["products"]], ["Caps", "Toques", "EK9", "EK12", "EK60"])
        self.assertEqual([s["label"] for s in cfg["services"]], ["UPS World Ease Standard", "UPS Worldwide Expedited/Saver"])
        w = {b["dims_text"]: b["dim_weight_lb"] for b in cfg["boxes"]}
        self.assertEqual((w["13 \u00d7 11 \u00d7 7"], w["23 \u00d7 9 \u00d7 7"], w["24 \u00d7 10 \u00d7 14"]), (8, 11, 25))
        everything = json.dumps(cfg, ensure_ascii=False) + self.get_text("/") + self.get_text("/static/app.js")
        for bad in ("TK3", "EK64", "22.8", "Non Air", "Non-air"):
            self.assertNotIn(bad, everything)
        self.assertFalse(has_decimal_dims(everything))

    def test_suggest_api(self):
        d = self.post("/api/suggest", {"product_id": "toques", "quantity": 73}).get_json()
        b = d["boxes"][0]
        self.assertEqual((b["dims_text"], b["count"], b["pieces_per_box"], b["capacity"]), ("24 × 10 × 14", 1, 73, 144))
        self.assertNotIn("alternative", d)
        r = self.post("/api/suggest", {"product_id": "toques", "quantity": "abc"})
        self.assertEqual(r.status_code, 400)

    def test_quote_api_75(self):
        s = self.post("/api/suggest", {"product_id": "ek60", "quantity": 30000}).get_json()
        rows = [{"box_id": b["box_id"], "count": b["count"], "pieces": b["pieces_per_box"]} for b in s["boxes"]]
        body = {"product_id": "ek60", "quantity": "30000", "service": "world_ease_standard", "rows": rows,
                "ups_total_cost": "100"}
        q = self.post("/api/quote", body).get_json()
        self.assertEqual(q["status"], "complete")
        self.assertEqual(q["price"], {"customer_shipping_price": "125.00", "shipping_price_per_piece": "0.0042", "currency": "CAD"})
        self.assertNotIn("_steps", q)
        body["ups_total_cost"] = ""
        q = self.post("/api/quote", body).get_json()
        self.assertEqual((q["status"], q["price"]), ("incomplete", None))

    def test_bad_requests(self):
        r = self.client.post("/api/quote", data="not json", content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.get_json()["price"])
        r = self.client.post("/api/quote", data="x" * (300 * 1024), content_type="application/json")
        self.assertEqual(r.status_code, 413)
        self.assertEqual(self.client.get("/api/quote").status_code, 405)
        self.assertEqual(self.client.get("/api/nope").status_code, 404)


# The DML UPS login is shown in the instructions at DML's explicit request (v1.4.0).
UPS_USER_ID = "UPSMPDM"
UPS_PASSWORD = "Creation11"


class HowToAndAccessTest(unittest.TestCase):
    def app_with(self, env):
        with mock.patch.dict(os.environ, env, clear=False):
            for k in ("UPS_LOGIN_USER_ID", "UPS_LOGIN_PASSWORD"):
                os.environ.pop(k, None)  # no UPS environment variables are needed
            return create_app().test_client()

    def howto(self, html):
        return html[html.index('id="howto"'):html.index("</details>")]

    def test_instructions_closed_by_default_with_steps(self):
        html = self.app_with({}).get("/").get_data(as_text=True)
        m = re.search(r'<details class="howto" id="howto"([^>]*)>', html)
        self.assertIsNotNone(m)
        self.assertNotIn("open", m.group(1))  # closed by default
        body = self.howto(html)
        steps = re.findall(r"<li>(.*?)</li>", body, re.S)
        self.assertEqual(len(steps), 8)
        expected = ["Open the UPS website", "Shipping → Calculate Shipping Cost",
                    "<strong>Cap America</strong> as the shipping origin",
                    "customs value to <strong>$1</strong>", "Enter every package from Step 2",
                    "Under <strong>How will you pay the shipping charges?</strong>, choose DML’s UPS account number "
                    "from the <strong>Select a UPS Account Number</strong> dropdown, then click <strong>Update</strong>.",
                    "Select the UPS service chosen in Step 1",
                    "Copy the discounted <strong>Total Cost</strong> for the complete shipment into Step 3"]
        for i, text in enumerate(expected):  # each step in its numbered position
            self.assertTrue(text in steps[i], "step %d" % (i + 1))
        self.assertIn("destination postal code", steps[3])
        self.assertIn("sign in with the DML UPS login", steps[0])
        self.assertIn('href="https://www.ups.com/lasso/login?returnto=https%3a//www.ups.com/webqvm%3floc%3den_CA'
                      '&amp;reasonCode=-1&amp;appid=CVA#/thirdparty"', body)
        self.assertIn('rel="noopener noreferrer"', body)

    def test_login_shown_without_environment_variables(self):
        r = self.app_with({}).get("/")
        body = self.howto(r.get_data(as_text=True))
        # assertTrue with a fixed message so a failure never prints the password
        self.assertTrue('<code id="ups-user">%s</code>' % UPS_USER_ID in body, "user ID not shown")
        self.assertTrue('<code id="ups-pass">%s</code>' % UPS_PASSWORD in body, "password not shown")
        self.assertNotIn("has not been set up", body)
        self.assertEqual(r.headers.get("Cache-Control"), "no-store")

    def test_login_only_inside_instructions(self):
        c = self.app_with({})
        html = c.get("/").get_data(as_text=True)
        self.assertTrue(html.count(UPS_PASSWORD) == 1, "password appears outside the instructions")
        for path in ("/api/config", "/healthz", "/static/app.js"):
            r = c.get(path)
            self.assertTrue(UPS_PASSWORD not in r.get_data(as_text=True), "password leaked in " + path)
            r.close()

    def test_opens_directly_without_sign_in(self):
        for env in ({}, {"DML_ACCESS_PASSWORD": "anything", "DML_ACCESS_USER": "dml"}):  # old settings are ignored
            c = self.app_with(env)
            for path in ("/", "/api/config", "/static/app.js", "/healthz"):
                r = c.get(path)
                self.assertEqual(r.status_code, 200, path)
                self.assertNotIn("WWW-Authenticate", r.headers)
                r.close()
            self.assertTrue('<code id="ups-pass">%s</code>' % UPS_PASSWORD in c.get("/").get_data(as_text=True),
                            "login missing from instructions")

    def test_no_sign_in_code_left(self):
        with open(os.path.join(ROOT, "app.py"), encoding="utf-8") as fh:
            src = fh.read()
        for gone in ("DML_ACCESS_PASSWORD", "DML_ACCESS_USER", "WWW-Authenticate", "authorization", "401"):
            self.assertNotIn(gone, src)


class ConfigValidationTest(unittest.TestCase):
    def setUp(self):
        with open(DEFAULT_CONFIG_PATH, encoding="utf-8") as fh:
            self.raw = json.load(fh)

    def bad(self, mutate):
        raw = copy.deepcopy(self.raw)
        mutate(raw)
        with self.assertRaises(ConfigError):
            Config(raw)

    def test_valid(self):
        Config(copy.deepcopy(self.raw))

    def test_rejects_decimal_dimension(self):
        self.bad(lambda r: r["boxes"][2].__setitem__("dims_in", [22.8, 9, 7]))

    def test_rejects_bad_divisor_and_historical_weight(self):
        self.bad(lambda r: r["dimensional_weight"].__setitem__("divisor_in3_per_lb", 0))
        self.bad(lambda r: r["dimensional_weight"].__setitem__("divisor_in3_per_lb", 139.5))
        self.bad(lambda r: r["boxes"][0].__setitem__("workbook_est_weight_lb", "abc"))

    def test_rejects_bad_limits(self):
        self.bad(lambda r: r["limits"].__setitem__("max_box_rows_per_line", 3))
        self.bad(lambda r: r["limits"].__setitem__("max_quantity", 0))

    def test_rejects_bad_capacity(self):
        self.bad(lambda r: r["products"][0]["capacities"]["box_23x9x7"].__setitem__("capacity", 0))
        self.bad(lambda r: r["products"][0]["capacities"]["box_23x9x7"].__setitem__("capacity", 2.5))
        self.bad(lambda r: r["products"][4]["capacities"]["catalog_13x11x7"].__setitem__("capacity", 12))
        self.bad(lambda r: r["products"][0]["capacities"]["box_23x9x7"].__setitem__("status", "maybe"))

    def test_rejects_bad_pricing(self):
        self.bad(lambda r: r["pricing"].__setitem__("markup_on_cost_rate", "x"))

    def test_dimension_edit_recalculates_dim_weight(self):
        raw = copy.deepcopy(self.raw)
        raw["boxes"][2]["dims_in"] = [24, 9, 7]  # 1,512 in3 / 139 = 10.9 -> 11
        raw["boxes"][3]["dims_in"] = [24, 10, 15]  # 3,600 / 139 = 25.9 -> 26
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(raw, fh)
        try:
            c = create_app(fh.name).test_client()
            d = c.get("/api/config").get_json()
            w = {b["id"]: b["dim_weight_lb"] for b in d["boxes"]}
            self.assertEqual(w["box_24x10x14"], 26)
        finally:
            os.unlink(fh.name)


class SecurityHygieneTest(unittest.TestCase):
    """The workbook contains carrier login details. Make sure nothing like that,
    and no copy of the workbook, is shipped with the app."""

    def iter_files(self):
        skip = {".git", "__pycache__", ".venv", "venv", "node_modules"}
        for d, dirs, files in os.walk(ROOT):
            dirs[:] = [x for x in dirs if x not in skip]
            for f in files:
                yield os.path.join(d, f)

    def test_no_workbook_copies(self):
        for p in self.iter_files():
            self.assertFalse(p.lower().endswith((".xlsx", ".xlsm", ".xls")), p)

    def test_no_credential_fields(self):
        pat = re.compile(r"(password|passwd|pwd|username|user\s*id|login\s*:|api[_-]?key|secret\s*=)", re.I)
        # These files name the login fields or env variables but never hold values.
        allowed = {os.path.join(ROOT, "tests", "test_app_and_config.py"), os.path.join(ROOT, "AUDIT.md"),
                   os.path.join(ROOT, "README.md"), os.path.join(ROOT, "CHANGELOG.md"), os.path.join(ROOT, "app.py"),
                   os.path.join(ROOT, "templates", "index.html"), os.path.join(ROOT, "tests", "ui_check.py")}
        for p in self.iter_files():
            if p in allowed or not p.endswith((".py", ".js", ".html", ".css", ".json", ".md", ".txt", ".yaml", ".toml", ".cfg")):
                continue
            with open(p, encoding="utf-8", errors="ignore") as fh:
                m = pat.search(fh.read())
            self.assertIsNone(m, "%s contains %r" % (p, m and m.group(0)))


    def test_login_only_in_template_and_no_env_requirement(self):
        for d, _dirs, files in os.walk(ROOT):
            if "__pycache__" in d:
                continue
            for f in files:
                p = os.path.join(d, f)
                if p.endswith((".py", ".js", ".json", ".css")) and not p.endswith(os.path.join("tests", "test_app_and_config.py")) \
                        and not p.endswith(os.path.join("tests", "ui_check.py")):
                    with open(p, encoding="utf-8", errors="ignore") as fh:
                        txt = fh.read()
                    self.assertTrue(UPS_PASSWORD not in txt, "login value found in " + p)
                    self.assertNotIn("UPS_LOGIN_", txt, p)


if __name__ == "__main__":
    unittest.main()
