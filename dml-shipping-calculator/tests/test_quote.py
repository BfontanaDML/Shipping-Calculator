import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shipping.config import load_config  # noqa: E402
from shipping.packing import suggest  # noqa: E402
from shipping.pricing import price  # noqa: E402
from shipping.quote import SERVICE_EXPEDITED, SERVICE_STANDARD, evaluate, public  # noqa: E402

CFG = load_config()
PRODUCTS = ["caps", "toques", "ek9", "ek12", "ek60"]


def rows_for(product, qty):
    return [{"box_id": r["box_id"], "count": r["count"], "pieces": r["pieces_per_box"]}
            for r in suggest(CFG, product, qty)["boxes"]]


def quote(product="caps", qty=150, service=SERVICE_STANDARD, rows=None, total="100"):
    if rows is None:
        rows = rows_for(product, qty)
    return evaluate(CFG, {"product_id": product, "quantity": qty, "service": service, "rows": rows,
                          "ups_total_cost": total})


class PricingTest(unittest.TestCase):
    def test_acceptance_example(self):
        q = quote("caps", 100)  # discounted UPS Total Cost $100.00
        self.assertEqual(q["status"], "complete")
        self.assertEqual(q["price"]["customer_shipping_price"], "125.00")  # 100 x 1.25, no further discount
        self.assertEqual(q["price"]["shipping_price_per_piece"], "1.25")
        st = q["_steps"]  # internal only
        self.assertEqual((st["ups_total_cost"], st["markup_amount"], st["customer_shipping_price"]), ("100.00", "25.00", "125.00"))
        self.assertNotIn("dml_cost", st)
        self.assertNotIn("dml_discount_amount", st)

    def test_formula_is_markup_only(self):
        from decimal import ROUND_HALF_UP, Decimal
        for total in ("1", "12.34", "99.99", "100", "250.50", "1234.56", "8765.43"):
            st = price(CFG, 7, total)["steps"]
            expect = (Decimal(total) * Decimal("1.25")).quantize(Decimal("0.01"), ROUND_HALF_UP)
            self.assertEqual(st["customer_shipping_price"].replace(",", ""), str(expect), total)
        self.assertFalse(hasattr(CFG, "discount_rate"))  # no discount anywhere in the calculator

    def test_both_services_same_price(self):
        for svc in (SERVICE_STANDARD, SERVICE_EXPEDITED):
            q = quote("ek9", 50, service=svc)
            self.assertEqual(q["status"], "complete")
            self.assertEqual(q["price"]["customer_shipping_price"], "125.00")

    def test_calculation_hidden_from_screen(self):
        pub = public(quote("caps", 100))
        self.assertNotIn("_steps", pub)
        self.assertEqual(set(pub["price"]), {"customer_shipping_price", "shipping_price_per_piece", "currency"})
        blob = repr(pub)
        for word in ("dml_cost", "discount", "markup", "'25.00'"):
            self.assertNotIn(word, blob)

    def test_rounding(self):
        self.assertEqual(quote("caps", 144)["price"]["shipping_price_per_piece"], "0.87")  # 125 / 144 = 0.868
        self.assertEqual(quote("caps", 150)["price"]["shipping_price_per_piece"], "0.83")
        st = price(CFG, 3, "33.33")["steps"]
        self.assertEqual((st["customer_shipping_price"], st["shipping_price_per_piece"]), ("41.66", "13.89"))
        self.assertEqual(price(CFG, 10, "$1,247.00")["steps"]["customer_shipping_price"], "1,558.75")
        self.assertEqual(quote("ek60", 30000)["price"]["shipping_price_per_piece"], "0.0042")  # never $0.00
        self.assertEqual(price(CFG, 100000, "0.01")["steps"]["shipping_price_per_piece"], "<0.0001")

    def test_missing_total_shows_no_price(self):
        for total in ("", "   ", None):
            q = quote(total=total)
            self.assertEqual(q["status"], "incomplete", total)
            self.assertIsNone(q["price"])
            self.assertEqual(q["errors"]["ups_total_cost"], "Enter the discounted UPS total cost.")

    def test_invalid_total_shows_no_price(self):
        for total in ("0", "0.00", "-5", "abc", "NaN", "Infinity", "1e3", "10.123", "99999999", True, "12,3x"):
            q = quote(total=total)
            self.assertEqual(q["status"], "invalid", total)
            self.assertIsNone(q["price"])
            self.assertIn("ups_total_cost", q["errors"])
            self.assertLess(len(q["errors"]["ups_total_cost"]), 45)  # concise, shown beside the field

    def test_old_two_field_payload_is_not_priced(self):
        q = evaluate(CFG, {"product_id": "caps", "quantity": 150, "service": SERVICE_STANDARD, "rows": rows_for("caps", 150),
                           "ups_service_cost": "90", "ups_fuel_surcharge": "10"})
        self.assertEqual(q["status"], "incomplete")
        self.assertIsNone(q["price"])


class ShipmentFieldsTest(unittest.TestCase):
    def test_empty_screen_is_incomplete_not_invalid(self):
        q = evaluate(CFG, {})
        self.assertEqual(q["status"], "incomplete")
        self.assertIsNone(q["price"])
        self.assertEqual(set(q["errors"]), {"product", "quantity", "service", "ups_total_cost"})

    def test_service_required(self):
        q = quote(service=None)
        self.assertEqual(q["status"], "incomplete")
        self.assertIsNone(q["price"])
        self.assertEqual(q["errors"]["service"], "Choose a UPS service.")
        self.assertEqual(quote(service="air")["errors"]["service"], "Choose a UPS service.")

    def test_service_labels(self):
        self.assertEqual(quote(service=SERVICE_STANDARD)["service_label"], "UPS World Ease Standard")
        self.assertEqual(quote(service=SERVICE_EXPEDITED)["service_label"], "UPS Worldwide Expedited/Saver")

    def test_quantity_validation(self):
        for bad in ("abc", "0", "-3", "1.5", "1e3", str(CFG.max_quantity + 1)):
            q = quote(qty=bad, rows=[])
            self.assertEqual(q["status"], "invalid", bad)
            self.assertIn("quantity", q["errors"])
            self.assertIsNone(q["price"])
        self.assertEqual(quote(qty="", rows=[])["status"], "incomplete")
        self.assertEqual(quote(qty="1,000", rows=rows_for("caps", 1000))["status"], "complete")

    def test_product_validation(self):
        for bad in (None, "", "ek64", "EK64", "tk3"):
            q = quote(product=bad, rows=[])
            self.assertIn("product", q["errors"])
            self.assertIsNone(q["price"])


class WeightTest(unittest.TestCase):
    def test_standard_shows_dim_and_quote_weight_per_row(self):
        q = quote("caps", 150, SERVICE_STANDARD)
        self.assertTrue(q["weights_apply"])
        got = [(r["count"], r["dims_text"], r["pieces_per_box"], r["dim_weight_lb"], r["quote_weight_lb"]) for r in q["rows"]]
        self.assertEqual(got, [(1, "24 × 19 × 20", 144, 66, 66), (1, "11 × 9 × 8", 6, 6, 6)])
        self.assertEqual(q["totals"], {"box_count": 2, "pieces": 150, "quote_weight_lb": 72})

    def test_required_dim_weights(self):
        for box_id, pcs, wt in (("catalog_13x11x7", 10, 8), ("box_23x9x7", 20, 11), ("box_24x10x14", 40, 25)):
            q = quote("caps", pcs, rows=[{"box_id": box_id, "count": 1, "pieces": pcs}])
            self.assertEqual(q["rows"][0]["dim_weight_lb"], wt)

    def test_measured_weight_rules(self):
        rows = rows_for("caps", 144)
        rows[0]["measured_weight_lb"] = "12.2"  # low: never reduces below dim. weight
        r = quote("caps", 144, rows=rows)["rows"][0]
        self.assertEqual((r["measured_weight_lb"], r["measured_rounded_lb"], r["dim_weight_lb"], r["quote_weight_lb"]), ("12.2", 13, 66, 66))
        rows[0]["measured_weight_lb"] = "70.2"  # heavy: rounded up and used
        q = quote("caps", 144, rows=rows)
        self.assertEqual(q["rows"][0]["quote_weight_lb"], 71)
        self.assertEqual(q["totals"]["quote_weight_lb"], 71)
        rows = [{"box_id": "box_23x9x7", "count": 3, "pieces": 8, "measured_weight_lb": "11.01"}]
        q = quote("caps", 24, rows=rows)
        self.assertEqual((q["rows"][0]["quote_weight_lb"], q["totals"]["quote_weight_lb"]), (12, 36))

    def test_bad_measured_weight(self):
        rows = rows_for("caps", 144)
        for bad in ("0", "-1", "abc", "1.234", "1000", "5e1"):
            rows[0]["measured_weight_lb"] = bad
            q = quote("caps", 144, rows=rows)
            self.assertEqual(q["status"], "invalid", bad)
            self.assertIn("measured", q["rows"][0]["errors"])
            self.assertIsNone(q["price"])
        rows[0]["measured_weight_lb"] = "160"  # over UPS limit: short note, not a blocker
        q = quote("caps", 144, rows=rows)
        self.assertEqual(q["status"], "complete")
        self.assertIn("150 lb", q["rows"][0]["note"])

    def test_expedited_gives_no_calculated_weight(self):
        rows = rows_for("caps", 150)
        rows[0]["measured_weight_lb"] = "70"
        q = quote("caps", 150, SERVICE_EXPEDITED, rows=rows)
        self.assertEqual(q["status"], "complete")
        self.assertFalse(q["weights_apply"])
        self.assertIsNone(q["totals"]["quote_weight_lb"])
        for r in q["rows"]:
            self.assertIsNone(r["dim_weight_lb"])
            self.assertIsNone(r["quote_weight_lb"])
        self.assertEqual(q["rows"][0]["measured_weight_lb"], "70")  # staff can still record it
        self.assertEqual(q["weight_note"], "Use the billable weight from the UPS quote.")
        self.assertEqual(q["price"]["customer_shipping_price"], "125.00")


class PackingOverrideTest(unittest.TestCase):
    def test_all_products_both_services(self):
        for prod in PRODUCTS:
            for svc in (SERVICE_STANDARD, SERVICE_EXPEDITED):
                for qty in (1, 9, 24, 54, 72, 144, 433, 1000, 100000):
                    q = quote(prod, qty, svc)
                    self.assertEqual(q["status"], "complete", (prod, svc, qty, q["errors"]))
                    self.assertEqual(q["totals"]["pieces"], qty)
                    self.assertEqual(q["price"]["customer_shipping_price"], "125.00")

    def test_grouped_rows_ek60_30000(self):
        q = quote("ek60", 30000)
        self.assertEqual(q["status"], "complete")
        self.assertEqual([(r["count"], r["pieces_per_box"]) for r in q["rows"]], [(555, 54), (1, 30)])
        self.assertEqual(q["totals"]["box_count"], 556)
        self.assertEqual(q["totals"]["quote_weight_lb"], 556 * 66)
        self.assertEqual(q["price"]["shipping_price_per_piece"], "0.0042")
        self.assertNotIn("freight", repr(q).lower())  # no large-shipment warning

    def test_edit_counts_boxes_and_pieces(self):
        rows = [{"box_id": "master_24x19x20", "count": 3, "pieces": 144}, {"box_id": "box_23x9x7", "count": 2, "pieces": 12}]
        q = quote("caps", 456, rows=rows)  # suggestion is 3 x 144 + 1 x 24; staff split the last box
        self.assertEqual(q["status"], "complete")
        self.assertEqual(q["totals"]["box_count"], 5)
        rows = [{"box_id": "box_24x10x20", "count": 1, "pieces": 60}, {"box_id": "box_23x9x7", "count": 1, "pieces": 12}]
        self.assertEqual(quote("caps", 72, rows=rows)["status"], "complete")  # changed box sizes

    def test_pieces_must_add_up(self):
        q = quote("caps", 24, rows=[{"box_id": "box_23x9x7", "count": 1, "pieces": 20}])
        self.assertEqual((q["status"], q["errors"]["packing"]), ("invalid", "4 pieces not in a box."))
        self.assertIsNone(q["price"])
        q = quote("caps", 24, rows=[{"box_id": "box_23x9x7", "count": 2, "pieces": 15}])
        self.assertEqual(q["errors"]["packing"], "6 pieces too many.")

    def test_row_errors_are_field_level(self):
        cases = [
            ({"box_id": "box_23x9x7", "count": 1, "pieces": 25}, "pieces", "Max 24 per box."),
            ({"box_id": "box_23x9x7", "count": 0, "pieces": 5}, "count", "At least 1."),
            ({"box_id": "box_23x9x7", "count": "x", "pieces": 5}, "count", "Whole number."),
            ({"box_id": "box_23x9x7", "count": 1, "pieces": ""}, "pieces", "Whole number."),
            ({"box_id": "nope", "count": 1, "pieces": 5}, "box", "Choose a box."),
        ]
        for row, key, msg in cases:
            q = quote("caps", 5 if key != "pieces" or row["pieces"] != 25 else 25, rows=[row])
            self.assertEqual(q["status"], "invalid", row)
            self.assertEqual(q["rows"][0]["errors"].get(key), msg, row)
            self.assertIsNone(q["price"])

    def test_no_rows_and_row_limit(self):
        q = quote("caps", 5, rows=[])
        self.assertEqual(q["errors"]["packing"], "Add at least one box.")
        rows = [{"box_id": "sample_11x9x8", "count": 1, "pieces": 1}] * (CFG.max_rows + 1)
        self.assertIn("Too many rows", quote("caps", CFG.max_rows + 1, rows=rows)["errors"]["packing"])

    def test_box_rules_preserved(self):
        q = quote("ek60", 5, rows=[{"box_id": "catalog_13x11x7", "count": 1, "pieces": 5}])
        self.assertEqual(q["rows"][0]["errors"]["box"], "Not available for EK60.")
        q = quote("toques", 10, rows=[{"box_id": "catalog_13x11x7", "count": 1, "pieces": 10}])
        self.assertEqual(q["status"], "complete")
        self.assertIn("not confirmed", q["rows"][0]["note"])


if __name__ == "__main__":
    unittest.main()
