"""Manual UPS pricing.

    Customer Shipping Price   = Discounted UPS Total Cost x 1.25   # 25% markup on the entered cost
    Shipping Price Per Piece  = Customer Shipping Price / quantity

The employee enters DML's discounted UPS Total Cost (CAD) for the complete
shipment, exactly as shown in DML's signed-in UPS quote. That amount already
includes DML's UPS discount, so the calculator applies no further discount.
Example: $100.00 -> $125.00.

Currency rounding: Decimal arithmetic, ROUND_HALF_UP to the cent. Per piece is
shown to the cent, or to 4 decimals when cent rounding would show $0.00.
Only the two final figures are shown to employees.
"""
from __future__ import annotations

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from .config import Config

CENT = Decimal("0.01")
_AMOUNT = re.compile(r"^-?\d+(\.\d*)?$|^-?\.\d+$")
FOUR = Decimal("0.0001")


def money(d: Decimal) -> Decimal:
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


def money_str(d: Decimal) -> str:
    return "{:,.2f}".format(money(d))


def _per_piece_text(cents: Decimal, exact: Decimal) -> str:
    if cents > 0:
        return money_str(cents)
    four = exact.quantize(FOUR, rounding=ROUND_HALF_UP)
    if four > 0:
        return "{:,.4f}".format(four)
    return "<0.0001"


def parse_amount(raw: Any, cfg: Config, allow_zero: bool) -> Tuple[Optional[Decimal], Optional[str], bool]:
    """Returns (value, short error for the field, missing)."""
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None, None, True
    if isinstance(raw, bool):
        return None, "Enter an amount, e.g. 90.50.", False
    text = str(raw).strip().replace(",", "").replace("$", "").strip()
    if not _AMOUNT.match(text):
        return None, "Enter an amount, e.g. 90.50.", False
    try:
        d = Decimal(text)
    except (InvalidOperation, ValueError):
        return None, "Enter an amount, e.g. 90.50.", False
    if not d.is_finite():
        return None, "Enter an amount, e.g. 90.50.", False
    if d.as_tuple().exponent < -2:
        return None, "Use at most 2 decimals.", False
    if d < 0:
        return None, "Can't be negative.", False
    if d == 0 and not allow_zero:
        return None, "Must be more than $0.", False
    if d > cfg.max_price:
        return None, "Too large.", False
    return d, None, False


def price(cfg: Config, quantity: Optional[int], total_raw: Any) -> Dict[str, Any]:
    """Customer shipping price from the discounted UPS Total Cost the employee enters
    (DML's signed-in UPS Total Cost for the complete shipment, all boxes included).

    Never returns a $0 or divided-by-zero result: if the amount is missing or
    invalid, status is 'incomplete' or 'invalid' and `steps` is None.
    field_errors key: ups_total_cost.
    """
    field_errors = {}  # type: Dict[str, str]
    total, err, missing = parse_amount(total_raw, cfg, allow_zero=False)
    if err:
        field_errors["ups_total_cost"] = err
    elif missing:
        field_errors["ups_total_cost"] = "Enter the discounted UPS total cost."
    result = {"field_errors": field_errors, "steps": None}  # type: Dict[str, Any]
    if err or not quantity or quantity < 1:
        result["status"] = "invalid"
        return result
    if missing:
        result["status"] = "incomplete"
        return result

    # Internal steps (not shown on the employee screen; kept for tests and audit).
    ups_total = money(total)
    markup_amt = money(ups_total * cfg.markup_rate)
    customer = money(ups_total + markup_amt)
    per_piece_exact = customer / Decimal(quantity)
    per_piece = money(per_piece_exact)
    result["status"] = "complete"
    result["steps"] = {
        "ups_total_cost": money_str(ups_total),
        "markup_amount": money_str(markup_amt),
        "customer_shipping_price": money_str(customer),
        # Below one cent, cents rounding would show a misleading $0.00, so 4 decimals are shown instead.
        "shipping_price_per_piece": _per_piece_text(per_piece, per_piece_exact),
    }
    return result
