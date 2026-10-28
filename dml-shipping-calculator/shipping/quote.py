"""Evaluate one shipment: product, quantity, UPS service, box rows (with staff
corrections) and the UPS Total Cost. Returns field-level errors so the screen
can show each message beside the field it belongs to.

Box rows are grouped: one row = `count` identical boxes, each holding
`pieces` pieces (and, optionally, each weighing `measured_weight_lb`).

Weights per box - UPS World Ease Standard only (non-air):
  dimensional weight  = ceil(L x W x H / 139)                (whole-inch dims)
  measured weight     = what staff weighed, rounded UP to a whole pound
  quoting weight      = max(dimensional, rounded measured)    (dimensional if not weighed)
For UPS Worldwide Expedited/Saver no calculated weight is given: staff use the
billable weight on the UPS quote.
"""
from __future__ import annotations

import re
from decimal import ROUND_CEILING, Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from .config import Config, fmt_num
from .packing import PackingError, get_product, summarize, validate_quantity
from .pricing import price

SERVICE_STANDARD = "world_ease_standard"
SERVICE_EXPEDITED = "worldwide_expedited_saver"
SERVICES = {
    SERVICE_STANDARD: {"label": "UPS World Ease Standard", "weights_apply": True},
    SERVICE_EXPEDITED: {"label": "UPS Worldwide Expedited/Saver", "weights_apply": False},
}
EXPEDITED_WEIGHT_NOTE = "Use the billable weight from the UPS quote."

_NUMBER = re.compile(r"^-?\d+(\.\d*)?$|^-?\.\d+$")


def _parse_int(raw: Any) -> Optional[int]:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float) and raw.is_integer():
        return int(raw)
    if isinstance(raw, str):
        t = raw.strip().replace(",", "")
        if t.lstrip("-").isdigit():
            return int(t)
    return None


def _parse_weight(raw: Any) -> Tuple[Optional[Decimal], Optional[str]]:
    """Returns (Decimal|None, error|None). Blank = not weighed."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, None
    if isinstance(raw, bool):
        return None, "Enter pounds, e.g. 42.5."
    text = str(raw).strip()
    if not _NUMBER.match(text):
        return None, "Enter pounds, e.g. 42.5."
    try:
        d = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, "Enter pounds, e.g. 42.5."
    if not d.is_finite():
        return None, "Enter pounds, e.g. 42.5."
    if d.as_tuple().exponent < -2:
        return None, "Use at most 2 decimals."
    return d, None


def round_up_lb(d: Decimal) -> int:
    return int(d.to_integral_value(rounding=ROUND_CEILING))


def _plural(n: int, word: str) -> str:
    return "%s %s%s" % (format(n, ","), word, "" if n == 1 else "s")


def evaluate(cfg: Config, payload: Dict[str, Any]) -> Dict[str, Any]:
    """payload = {product_id, quantity, service,
                  rows:[{box_id, count, pieces, measured_weight_lb}],
                  ups_total_cost}

    status: 'complete' (price shown), 'incomplete' (something not entered yet)
    or 'invalid' (something entered is wrong). Only 'complete' carries a price.
    """
    errors = {}  # type: Dict[str, str]  field -> short message
    out = {"rows": [], "totals": None, "price": None}  # type: Dict[str, Any]

    # ---- 1. shipment ----
    product = None
    try:
        product = get_product(cfg, payload.get("product_id"))
    except PackingError:
        errors["product"] = "Choose a product."
    qty = None
    raw_qty = payload.get("quantity")
    if raw_qty is None or (isinstance(raw_qty, str) and not raw_qty.strip()):
        errors["quantity"] = "Enter the quantity."
    else:
        try:
            qty = validate_quantity(cfg, raw_qty)
        except PackingError as exc:
            errors["quantity"] = str(exc)
    service = payload.get("service")
    if service not in SERVICES:
        errors["service"] = "Choose a UPS service."
        service = None
    weights_apply = bool(service and SERVICES[service]["weights_apply"])
    out.update({
        "product_id": product.id if product else None,
        "product_name": product.name if product else None,
        "quantity": qty,
        "service": service,
        "service_label": SERVICES[service]["label"] if service else None,
        "weights_apply": weights_apply,
        "weight_note": EXPEDITED_WEIGHT_NOTE if service == SERVICE_EXPEDITED else None,
    })

    # ---- 2. boxes ----
    rows_in = payload.get("rows")
    if not isinstance(rows_in, list):
        rows_in = []
    packing_ok = product is not None and qty is not None
    if product is not None and qty is not None:
        if not rows_in:
            errors["packing"] = "Add at least one box."
            packing_ok = False
        if len(rows_in) > cfg.max_rows:
            errors["packing"] = "Too many rows (max %d). Put identical boxes in one row." % cfg.max_rows
            rows_in = rows_in[: cfg.max_rows]
            packing_ok = False
        total_pieces = 0
        total_boxes = 0
        total_quote_w = 0
        all_counted = True
        for r in rows_in:
            r = r if isinstance(r, dict) else {}
            row_err = {}  # type: Dict[str, str]
            row = {"box_id": r.get("box_id")}  # type: Dict[str, Any]
            pb = product.boxes.get(r.get("box_id")) if isinstance(r.get("box_id"), str) else None
            if pb is None:
                row_err["box"] = "Choose a box."
            elif not pb.selectable:
                row_err["box"] = "Not available for %s." % product.name
                pb = None
            if pb is not None:
                row.update({"label": pb.box.label, "dims_text": pb.box.dims_text, "dims_in": list(pb.box.dims_in),
                            "capacity": pb.capacity, "capacity_confirmed": pb.status != "unconfirmed"})
                if pb.status == "unconfirmed":
                    row["note"] = "Capacity not confirmed for %s." % product.name

            count = _parse_int(r.get("count"))
            row["count"] = count
            if count is None:
                row_err["count"] = "Whole number."
            elif count < 1:
                row_err["count"] = "At least 1."
            elif count > cfg.max_boxes_per_row:
                row_err["count"] = "Too many."
            pieces = _parse_int(r.get("pieces"))
            row["pieces_per_box"] = pieces
            if pieces is None:
                row_err["pieces"] = "Whole number."
            elif pieces < 1:
                row_err["pieces"] = "At least 1."
            elif pb is not None and pieces > pb.capacity:
                row_err["pieces"] = "Max %d per box." % pb.capacity
            counted = "count" not in row_err and "pieces" not in row_err
            row["pieces_total"] = count * pieces if counted else None
            if counted:
                total_pieces += count * pieces
                total_boxes += count
            else:
                all_counted = False

            mw, werr = _parse_weight(r.get("measured_weight_lb"))
            row["measured_weight_lb"] = None
            row["measured_rounded_lb"] = None
            if werr:
                row_err["measured"] = werr
            elif mw is not None:
                if mw <= 0:
                    row_err["measured"] = "Must be more than 0."
                elif mw > cfg.max_measured_weight:
                    row_err["measured"] = "Too heavy."
                else:
                    row["measured_weight_lb"] = fmt_num(mw)
                    row["measured_rounded_lb"] = round_up_lb(mw)
                    if mw > cfg.ups_weight_limit:
                        row["note"] = "Over UPS %s lb per-box limit." % fmt_num(cfg.ups_weight_limit)
            if pb is not None and weights_apply:
                dim = pb.box.dim_weight_lb
                meas = row["measured_rounded_lb"]
                row["dim_weight_lb"] = dim
                row["quote_weight_lb"] = dim if meas is None else max(dim, meas)
                if counted:
                    total_quote_w += row["quote_weight_lb"] * count
            else:
                row["dim_weight_lb"] = None
                row["quote_weight_lb"] = None
            row["errors"] = row_err
            if row_err:
                packing_ok = False
            out["rows"].append(row)

        if rows_in and all_counted and total_pieces != qty and "packing" not in errors:
            diff = qty - total_pieces
            errors["packing"] = ("%s not in a box." % _plural(diff, "piece") if diff > 0
                                 else "%s too many." % _plural(-diff, "piece"))
            packing_ok = False
        out["totals"] = {
            "box_count": total_boxes,
            "pieces": total_pieces,
            "quote_weight_lb": total_quote_w if weights_apply else None,
        }
        named = [x for x in out["rows"] if x.get("dims_text") and isinstance(x.get("count"), int) and x["count"] > 0]
        out["summary"] = summarize(named) if named else ""

    # ---- 3. price ----
    pr = price(cfg, qty if qty else 1, payload.get("ups_total_cost"))
    errors.update(pr["field_errors"])

    qty_missing = errors.get("quantity") == "Enter the quantity."
    invalid = (("quantity" in errors and not qty_missing)
               or (product is not None and qty is not None and not packing_ok)
               or pr["status"] == "invalid")
    if not invalid and product is not None and qty is not None and service and pr["status"] == "complete":
        st = pr["steps"]
        out["status"] = "complete"
        out["price"] = {"customer_shipping_price": st["customer_shipping_price"],
                        "shipping_price_per_piece": st["shipping_price_per_piece"],
                        "currency": cfg.currency}
        out["_steps"] = st  # internal; stripped from API responses
    else:
        out["status"] = "invalid" if invalid else "incomplete"
    out["errors"] = errors
    return out


def public(result: Dict[str, Any]) -> Dict[str, Any]:
    """What the employee screen receives: the two results only, no calculation steps."""
    return {k: v for k, v in result.items() if not k.startswith("_")}
