"""Packing engine: suggest physical boxes for a product and quantity.

Rules (deterministic; see README "How the numbers work"):

* Only boxes whose capacity status is 'approved' or 'auto_audited' for the
  product are used for automatic suggestions.
* One suggestion only: the FEWEST physical boxes. Among arrangements with that
  many boxes, the one with the lowest total UPS dimensional weight
  (L x W x H / 139, rounded up) is chosen.
* Boxes are filled largest first; only the last box can be partly full.
  Identical boxes are grouped into one row ("555 boxes x 54 pcs").
* Ties are broken by a fixed box order, so the same input always gives the
  same answer.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Tuple

from .config import Config, Product, ProductBox


_INF = (10 ** 18, 10 ** 18)


class PackingError(ValueError):
    pass


def _solve(boxes: List[ProductBox], qty: int) -> List[ProductBox]:
    """Dynamic programme over piece counts. Returns the chosen boxes."""
    caps = [pb.capacity for pb in boxes]
    wts = [pb.box.dim_weight_lb for pb in boxes]
    best = [(0, 0)] + [_INF] * qty  # best[n] = key for covering n pieces
    choice = [-1] * (qty + 1)
    nb = len(boxes)
    for n in range(1, qty + 1):
        b_key = _INF
        b_idx = -1
        for i in range(nb):
            prev = n - caps[i]
            if prev < 0:
                prev = 0
            pk = best[prev]
            key = (pk[0] + 1, pk[1] + wts[i])  # (fewest boxes, then lowest dim. weight)
            if key < b_key:  # strict: first box in fixed order wins ties
                b_key = key
                b_idx = i
        best[n] = b_key
        choice[n] = b_idx
    chosen = []
    n = qty
    while n > 0:
        i = choice[n]
        chosen.append(boxes[i])
        n = max(0, n - caps[i])
    return chosen


def _row(pb: ProductBox, count: int, per_box: int) -> Dict[str, Any]:
    return {
        "box_id": pb.box.id,
        "label": pb.box.label,
        "dims_in": list(pb.box.dims_in),
        "dims_text": pb.box.dims_text,
        "count": count,
        "pieces_per_box": per_box,
        "pieces_total": count * per_box,
        "capacity": pb.capacity,
        "dim_weight_lb": pb.box.dim_weight_lb,
        "dim_weight_total_lb": count * pb.box.dim_weight_lb,
    }


def _arrangement(chosen: List[ProductBox], qty: int) -> Dict[str, Any]:
    chosen = sorted(chosen, key=lambda pb: (-pb.capacity, pb.box.id))
    remaining = qty
    rows = []  # type: List[Dict[str, Any]]
    for pb in chosen:
        pieces = min(pb.capacity, remaining)
        remaining -= pieces
        if pieces <= 0:
            continue  # cannot happen for an optimal solution; guard against data edits
        last = rows[-1] if rows else None
        if last and last["box_id"] == pb.box.id and last["pieces_per_box"] == pieces:
            last["count"] += 1
            last["pieces_total"] += pieces
            last["dim_weight_total_lb"] += pb.box.dim_weight_lb
        else:
            rows.append(_row(pb, 1, pieces))
    if remaining != 0:
        raise PackingError("internal error: %d pieces unassigned" % remaining)
    return {
        "boxes": rows,
        "row_count": len(rows),
        "box_count": sum(r["count"] for r in rows),
        "total_pieces": qty,
        "total_dim_weight_lb": sum(r["dim_weight_total_lb"] for r in rows),
        "summary": summarize(rows),
    }


def summarize(rows: List[Dict[str, Any]]) -> str:
    """'556 x (24 x 19 x 20 in) + 1 x (23 x 9 x 7 in)' - box counts by size, in row order."""
    parts = []  # type: List[Tuple[str, int]]
    for r in rows:
        n = r.get("count") or 0
        if parts and parts[-1][0] == r["dims_text"]:
            parts[-1] = (r["dims_text"], parts[-1][1] + n)
        else:
            parts.append((r["dims_text"], n))
    return " + ".join("%s × (%s in)" % (format(n, ","), d) for d, n in parts)


def validate_quantity(cfg: Config, qty: Any) -> int:
    msg = "Quantity must be a whole number of pieces."
    if isinstance(qty, bool):
        raise PackingError(msg)
    if isinstance(qty, str):
        q = qty.strip().replace(",", "")
        if not q.isdigit():
            raise PackingError(msg)
        qty = int(q)
    if isinstance(qty, float):
        if not qty.is_integer():
            raise PackingError(msg)
        qty = int(qty)
    if not isinstance(qty, int):
        raise PackingError(msg)
    if qty < 1:
        raise PackingError("Quantity must be at least 1.")
    if qty > cfg.max_quantity:
        raise PackingError("Quantity is above the %s-piece limit for this tool." % format(cfg.max_quantity, ","))
    return qty


def get_product(cfg: Config, product_id: Any) -> Product:
    if not isinstance(product_id, str) or product_id not in cfg.products:
        raise PackingError("Choose a product.")
    return cfg.products[product_id]


def suggest(cfg: Config, product_id: Any, qty: Any) -> Dict[str, Any]:
    product = get_product(cfg, product_id)
    q = validate_quantity(cfg, qty)
    # Results depend only on (data file, product, quantity); cache them so that
    # re-evaluating a 100,000-piece quote while a PM types stays fast.
    key = (id(cfg), product.id, q)
    hit = _CACHE.get(key)
    if hit is None:
        hit = _suggest(cfg, product, q)
        if len(_CACHE) >= 512:
            _CACHE.clear()
        _CACHE[key] = hit
    return copy.deepcopy(hit)


_CACHE = {}  # type: Dict[Tuple[int, str, int], Dict[str, Any]]


def _suggest(cfg: Config, product: Product, q: int) -> Dict[str, Any]:
    arr = _arrangement(_solve(product.auto_boxes(), q), q)
    arr.update({"product_id": product.id, "product_name": product.name, "quantity": q})
    return arr
