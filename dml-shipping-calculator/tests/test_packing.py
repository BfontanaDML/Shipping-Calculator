import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shipping.config import load_config  # noqa: E402
from shipping.packing import PackingError, suggest  # noqa: E402

CFG = load_config()

# Approved release table: dims -> (UPS non-air dimensional weight, {product: capacity})
APPROVED = {
    "box_23x9x7": ([23, 9, 7], 11, {"caps": 24, "toques": 72, "ek9": 36, "ek12": 18, "ek60": 9}),
    "box_24x10x14": ([24, 10, 14], 25, {"caps": 48, "toques": 144, "ek9": 72, "ek12": 36, "ek60": 18}),
    "box_24x10x20": ([24, 10, 20], 35, {"caps": 72, "toques": 216, "ek9": 108, "ek12": 54, "ek60": 27}),
    "master_24x19x20": ([24, 19, 20], 66, {"caps": 144, "toques": 432, "ek9": 216, "ek12": 108, "ek60": 54}),
}
PRODUCTS = ["caps", "toques", "ek9", "ek12", "ek60"]


def flat(arr):
    """Expand grouped rows to one (box_id, pieces) per physical box."""
    out = []
    for r in arr["boxes"]:
        out.extend([(r["box_id"], r["pieces_per_box"])] * r["count"])
    return out


def check_arrangement(tc, product, qty, arr):
    """Invariants every suggested arrangement must satisfy."""
    p = CFG.products[product]
    tc.assertEqual(sum(r["count"] * r["pieces_per_box"] for r in arr["boxes"]), qty, "pieces must add up")
    tc.assertEqual(arr["box_count"], sum(r["count"] for r in arr["boxes"]))
    tc.assertLessEqual(arr["row_count"], CFG.max_rows)
    total = 0
    for r in arr["boxes"]:
        pb = p.boxes[r["box_id"]]
        tc.assertTrue(pb.auto, "only auto-enabled boxes may be suggested (%s)" % r["box_id"])
        tc.assertGreaterEqual(r["count"], 1)
        tc.assertGreaterEqual(r["pieces_per_box"], 1)
        tc.assertLessEqual(r["pieces_per_box"], r["capacity"], "box over capacity")
        tc.assertEqual(r["capacity"], pb.capacity)
        tc.assertEqual(r["pieces_total"], r["count"] * r["pieces_per_box"])
        # every row carries its own dims and per-box dimensional weight
        tc.assertEqual(r["dims_in"], pb.box.dims_in)
        tc.assertTrue(all(isinstance(d, int) for d in r["dims_in"]))
        tc.assertNotIn(".", r["dims_text"])
        tc.assertEqual(r["dim_weight_lb"], pb.box.dim_weight_lb)
        tc.assertEqual(r["dim_weight_total_lb"], r["count"] * pb.box.dim_weight_lb)
        total += r["dim_weight_total_lb"]
    tc.assertEqual(arr["total_dim_weight_lb"], total)
    boxes = flat(arr)
    for box_id, pieces in boxes[:-1]:  # only the last box may be partly full
        tc.assertEqual(pieces, p.boxes[box_id].capacity)


class DimensionalWeightTest(unittest.TestCase):
    def test_required_values(self):
        # UPS Canada non-air: whole-inch L x W x H / 139, rounded UP to a whole pound
        self.assertEqual(CFG.boxes["catalog_13x11x7"].dim_weight_lb, 8)
        self.assertEqual(CFG.boxes["box_23x9x7"].dim_weight_lb, 11)
        self.assertEqual(CFG.boxes["box_24x10x14"].dim_weight_lb, 25)
        self.assertEqual(CFG.boxes["sample_11x9x8"].dim_weight_lb, 6)
        self.assertEqual(CFG.boxes["box_24x10x20"].dim_weight_lb, 35)
        self.assertEqual(CFG.boxes["master_24x19x20"].dim_weight_lb, 66)

    def test_formula(self):
        for box in CFG.boxes.values():
            l, w, h = box.dims_in
            exact = l * w * h / 139.0
            self.assertGreaterEqual(box.dim_weight_lb, exact)
            self.assertLess(box.dim_weight_lb - exact, 1)

    def test_workbook_values_are_historical_only(self):
        self.assertEqual(str(CFG.boxes["catalog_13x11x7"].workbook_est_weight_lb), "7")
        self.assertEqual(str(CFG.boxes["box_23x9x7"].workbook_est_weight_lb), "10")
        self.assertEqual(str(CFG.boxes["box_24x10x14"].workbook_est_weight_lb), "24")
        s = suggest(CFG, "caps", 20)
        self.assertEqual(s["boxes"][0]["dim_weight_lb"], 11)  # not 10


class ApprovedDataTest(unittest.TestCase):
    def test_approved_table(self):
        for box_id, (dims, wt, caps) in APPROVED.items():
            box = CFG.boxes[box_id]
            self.assertEqual(box.dims_in, dims)
            self.assertEqual(box.dim_weight_lb, wt)
            for prod, cap in caps.items():
                pb = CFG.products[prod].boxes[box_id]
                self.assertEqual(pb.capacity, cap, (prod, box_id))
                self.assertEqual(pb.status, "approved")

    def test_small_boxes(self):
        self.assertTrue(CFG.products["caps"].boxes["sample_11x9x8"].auto)
        self.assertTrue(CFG.products["caps"].boxes["catalog_13x11x7"].auto)
        for p in ("toques", "ek9", "ek12"):
            for b in ("sample_11x9x8", "catalog_13x11x7"):
                pb = CFG.products[p].boxes[b]
                self.assertEqual(pb.status, "unconfirmed")
                self.assertFalse(pb.auto)
                self.assertTrue(pb.selectable)
        for b in ("sample_11x9x8", "catalog_13x11x7"):
            pb = CFG.products["ek60"].boxes[b]
            self.assertEqual(pb.status, "conflict")
            self.assertIsNone(pb.capacity)
            self.assertFalse(pb.selectable)

    def test_display_names(self):
        names = [CFG.products[p].name for p in CFG.product_order]
        self.assertEqual(names, ["Caps", "Toques", "EK9", "EK12", "EK60"])
        self.assertNotIn("ek64", CFG.products)
        self.assertEqual(CFG.products["ek60"].workbook_sheet, "EK64")  # data origin, audit only
        self.assertEqual(CFG.boxes["box_23x9x7"].dims_text, "23 × 9 × 7")


class PackingTest(unittest.TestCase):
    def test_invariants_all_products_many_quantities(self):
        for prod in PRODUCTS:
            master = CFG.products[prod].boxes["master_24x19x20"].capacity
            for q in list(range(1, 3 * master + 2)) + [10 * master + 7, 5000]:
                s = suggest(CFG, prod, q)
                check_arrangement(self, prod, q, s)
                self.assertNotIn("alternative", s)  # one suggestion only

    def test_fewest_boxes(self):
        for prod in PRODUCTS:
            master = CFG.products[prod].boxes["master_24x19x20"].capacity
            for q in (1, master - 1, master, master + 1, 2 * master, 2 * master + 1, 7 * master + 3):
                s = suggest(CFG, prod, q)
                self.assertEqual(s["box_count"], -(-q // master), (prod, q))

    def test_below_at_above_each_capacity(self):
        for prod in PRODUCTS:
            for pb in CFG.products[prod].auto_boxes():
                c = pb.capacity
                for q in (c - 1, c, c + 1):
                    if q >= 1:
                        check_arrangement(self, prod, q, suggest(CFG, prod, q))
                s = suggest(CFG, prod, c)
                self.assertEqual(s["box_count"], 1)
                self.assertLessEqual(s["total_dim_weight_lb"], pb.box.dim_weight_lb)

    def test_specific_caps(self):
        cases = {
            1: [("sample_11x9x8", 1)],
            6: [("sample_11x9x8", 6)],
            7: [("catalog_13x11x7", 7)],
            12: [("catalog_13x11x7", 12)],
            13: [("box_23x9x7", 13)],
            24: [("box_23x9x7", 24)],
            25: [("box_24x10x14", 25)],
            72: [("box_24x10x20", 72)],
            144: [("master_24x19x20", 144)],
            150: [("master_24x19x20", 144), ("sample_11x9x8", 6)],
            160: [("master_24x19x20", 144), ("box_23x9x7", 16)],
            600: [("master_24x19x20", 144)] * 4 + [("box_23x9x7", 24)],
        }
        for q, expect in cases.items():
            self.assertEqual(flat(suggest(CFG, "caps", q)), expect, q)

    def test_grouped_rows(self):
        s = suggest(CFG, "caps", 600)
        self.assertEqual([(r["box_id"], r["count"], r["pieces_per_box"]) for r in s["boxes"]],
                         [("master_24x19x20", 4, 144), ("box_23x9x7", 1, 24)])
        self.assertEqual(s["summary"], "4 × (24 × 19 × 20 in) + 1 × (23 × 9 × 7 in)")

    def test_toques_never_auto_small_boxes(self):
        for q in range(1, 80):
            for b in suggest(CFG, "toques", q)["boxes"]:
                self.assertNotIn(b["box_id"], ("sample_11x9x8", "catalog_13x11x7"))

    def test_ek60_small_quantities_use_verified_box(self):
        for q in range(1, 10):
            self.assertEqual(flat(suggest(CFG, "ek60", q)), [("box_23x9x7", q)])
        self.assertEqual(flat(suggest(CFG, "ek60", 10)), [("box_24x10x14", 10)])
        self.assertEqual(flat(suggest(CFG, "ek60", 63)), [("master_24x19x20", 54), ("box_23x9x7", 9)])

    def test_ek60_30000(self):
        t = time.time()
        s = suggest(CFG, "ek60", 30000)
        self.assertLess(time.time() - t, 5)
        p = s
        check_arrangement(self, "ek60", 30000, p)
        self.assertEqual(p["box_count"], 556)  # ceil(30000 / 54)
        self.assertEqual([(r["box_id"], r["count"], r["pieces_per_box"]) for r in p["boxes"]],
                         [("master_24x19x20", 555, 54), ("master_24x19x20", 1, 30)])
        self.assertEqual(p["total_dim_weight_lb"], 556 * 66)
        self.assertEqual(p["row_count"], 2)
    def test_max_quantity_every_product(self):
        for prod in PRODUCTS:
            s = suggest(CFG, prod, CFG.max_quantity)
            check_arrangement(self, prod, CFG.max_quantity, s)

    def test_deterministic(self):
        for prod in PRODUCTS:
            for q in (5, 50, 500, 1234):
                self.assertEqual(suggest(CFG, prod, q), suggest(CFG, prod, q))

    def test_invalid_quantities(self):
        for bad in (0, -1, 1.5, "abc", "", None, True, "1e3", "12.0", CFG.max_quantity + 1, [], {}):
            with self.assertRaises(PackingError, msg=repr(bad)):
                suggest(CFG, "caps", bad)
        self.assertEqual(suggest(CFG, "caps", "1,000")["quantity"], 1000)

    def test_invalid_product(self):
        for bad in (None, "", "TK3", "tk3", "ek52", "ek64", "EK64", 5):
            with self.assertRaises(PackingError):
                suggest(CFG, bad, 10)


if __name__ == "__main__":
    unittest.main()
