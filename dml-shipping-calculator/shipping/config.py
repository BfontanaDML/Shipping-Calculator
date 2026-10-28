"""Load and validate the shipping data file (data/shipping_config.json).

Validation is strict on purpose: a bad edit to the data file should stop the
app at start-up with a clear message rather than produce wrong quotes.
"""
from __future__ import annotations

import json
import os
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "shipping_config.json"
)

AUTO_STATUSES = ("approved", "auto_audited")
SELECTABLE_STATUSES = ("approved", "auto_audited", "unconfirmed")
ALL_STATUSES = ("approved", "auto_audited", "unconfirmed", "conflict")


class ConfigError(ValueError):
    """Raised when the data file is missing or invalid."""


def _dec(value: Any, where: str, max_places: int = 4) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ConfigError("%s: expected a number" % where)
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ConfigError("%s: %r is not a number" % (where, value))
    if not d.is_finite():
        raise ConfigError("%s: must be finite" % where)
    if d.as_tuple().exponent < -max_places:
        raise ConfigError("%s: at most %d decimal places" % (where, max_places))
    return d


def _pos_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError("%s: must be a positive whole number" % where)
    return value


def ceil_div(a: int, b: int) -> int:
    return -(-a // b)


class Box(object):
    def __init__(self, raw: Dict[str, Any], divisor: int):
        self.id = raw.get("id")
        if not isinstance(self.id, str) or not self.id:
            raise ConfigError("box id missing")
        self.label = str(raw.get("label", ""))
        dims = raw.get("dims_in")
        if not isinstance(dims, list) or len(dims) != 3:
            raise ConfigError("box %s: dims_in must be [L, W, H]" % self.id)
        for d in dims:
            # Approved display rule: whole inches only, never decimals.
            if isinstance(d, bool) or not isinstance(d, int) or d <= 0:
                raise ConfigError("box %s: dimensions must be positive whole inches, got %r" % (self.id, d))
        self.dims_in = [int(d) for d in dims]
        # Historical only: the workbook's own estimate (nearest-pound rounding). Never used for guidance.
        wb = raw.get("workbook_est_weight_lb")
        self.workbook_est_weight_lb = None if wb is None else _dec(wb, "box %s workbook_est_weight_lb" % self.id, 2)
        self.source = str(raw.get("source", ""))
        # UPS non-air dimensional weight: whole-inch L x W x H / divisor, rounded UP to a whole pound.
        self.dim_weight_lb = ceil_div(self.volume_in3, divisor)

    @property
    def dims_text(self) -> str:
        return " × ".join(str(d) for d in self.dims_in)

    @property
    def volume_in3(self) -> int:
        l, w, h = self.dims_in
        return l * w * h


class ProductBox(object):
    def __init__(self, box: Box, raw: Dict[str, Any], product_id: str):
        self.box = box
        self.status = raw.get("status")
        if self.status not in ALL_STATUSES:
            raise ConfigError("%s/%s: unknown status %r" % (product_id, box.id, self.status))
        cap = raw.get("capacity")
        if self.status == "conflict":
            if cap is not None:
                raise ConfigError("%s/%s: a 'conflict' entry must have capacity null" % (product_id, box.id))
            self.capacity = None  # type: Optional[int]
        else:
            self.capacity = _pos_int(cap, "%s/%s capacity" % (product_id, box.id))
        wc = raw.get("workbook_capacity")
        self.workbook_capacity = wc if isinstance(wc, int) else self.capacity
        self.source = str(raw.get("source", ""))
        self.note = str(raw.get("note", ""))

    @property
    def auto(self) -> bool:
        return self.status in AUTO_STATUSES

    @property
    def selectable(self) -> bool:
        return self.status in SELECTABLE_STATUSES


class Product(object):
    def __init__(self, raw: Dict[str, Any], boxes: Dict[str, Box]):
        self.id = raw.get("id")
        self.name = raw.get("name")
        if not isinstance(self.id, str) or not isinstance(self.name, str) or not self.name:
            raise ConfigError("product id/name missing")
        self.workbook_sheet = str(raw.get("workbook_sheet", ""))
        caps = raw.get("capacities")
        if not isinstance(caps, dict) or not caps:
            raise ConfigError("product %s: capacities missing" % self.id)
        self.boxes = {}  # type: Dict[str, ProductBox]
        for box_id, entry in caps.items():
            if box_id not in boxes:
                raise ConfigError("product %s: unknown box %s" % (self.id, box_id))
            self.boxes[box_id] = ProductBox(boxes[box_id], entry, self.id)
        if not self.auto_boxes():
            raise ConfigError("product %s: no box is enabled for automatic suggestions" % self.id)

    def auto_boxes(self) -> List[ProductBox]:
        """Boxes used for automatic suggestions, largest capacity first (deterministic)."""
        items = [pb for pb in self.boxes.values() if pb.auto]
        items.sort(key=lambda pb: (-pb.capacity, pb.box.dim_weight_lb, pb.box.id))
        return items


class Config(object):
    def __init__(self, raw: Dict[str, Any], path: str = ""):
        self.path = path
        self.raw = raw
        self.version = str(raw.get("config_version", "unversioned"))
        pricing = raw.get("pricing") or {}
        self.currency = str(pricing.get("currency", "CAD"))
        self.markup_rate = _dec(pricing.get("markup_on_cost_rate"), "pricing.markup_on_cost_rate")
        if not (Decimal("0") <= self.markup_rate <= Decimal("5")):
            raise ConfigError("pricing.markup_on_cost_rate must be between 0 and 5")
        self.default_service_label = str(pricing.get("default_service_label", "UPS Standard"))
        self.rounding_note = str(pricing.get("rounding", ""))

        dw = raw.get("dimensional_weight") or {}
        self.dim_divisor = _pos_int(dw.get("divisor_in3_per_lb", 139), "dimensional_weight.divisor_in3_per_lb")
        self.dim_scope = str(dw.get("service_scope", "UPS non-air services only"))
        self.dim_source = str(dw.get("source", ""))

        limits = raw.get("limits") or {}
        self.max_quantity = _pos_int(limits.get("max_quantity", 100000), "limits.max_quantity")
        self.max_rows = _pos_int(limits.get("max_box_rows_per_line", 50), "limits.max_box_rows_per_line")
        self.max_boxes_per_row = _pos_int(limits.get("max_boxes_per_row", 100000), "limits.max_boxes_per_row")
        self.max_measured_weight = _dec(limits.get("max_measured_weight_lb", "999"), "limits.max_measured_weight_lb")
        self.ups_weight_limit = _dec(limits.get("ups_package_weight_limit_lb", "150"), "limits.ups_package_weight_limit_lb")
        self.max_price = _dec(limits.get("max_price_cad", "1000000"), "limits.max_price_cad")

        self.boxes = {}  # type: Dict[str, Box]
        for b in raw.get("boxes") or []:
            box = Box(b, self.dim_divisor)
            if box.id in self.boxes:
                raise ConfigError("duplicate box id %s" % box.id)
            self.boxes[box.id] = box
        if not self.boxes:
            raise ConfigError("no boxes defined")

        self.products = {}  # type: Dict[str, Product]
        self.product_order = []  # type: List[str]
        for p in raw.get("products") or []:
            prod = Product(p, self.boxes)
            if prod.id in self.products:
                raise ConfigError("duplicate product id %s" % prod.id)
            self.products[prod.id] = prod
            self.product_order.append(prod.id)
        if not self.products:
            raise ConfigError("no products defined")

        # Every suggested arrangement must be expressible within the row limit: at most
        # (number of auto boxes + 1) distinct rows are ever suggested.
        for p in self.products.values():
            if len(p.auto_boxes()) + 1 > self.max_rows:
                raise ConfigError("limits.max_box_rows_per_line is too small for product %s" % p.id)


def fmt_num(d: Decimal) -> str:
    """Decimal -> plain string without exponent or trailing zeros ('10', '10.5')."""
    return format(d.normalize(), "f")


def load_config(path: Optional[str] = None) -> Config:
    path = path or os.environ.get("SHIPPING_CONFIG_PATH") or DEFAULT_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
    except FileNotFoundError:
        raise ConfigError("data file not found: %s" % path)
    except json.JSONDecodeError as exc:
        raise ConfigError("data file is not valid JSON (%s): %s" % (path, exc))
    return Config(raw, path)
