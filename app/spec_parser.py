"""
spec_parser.py
Parse an Atlas Polar product spec spreadsheet (.xls/.xlsx) into structured data.

Vertical label/value layout in columns B and C (0-indexed 1 and 2):

    (blank)
    Product Group <name> ...        <- product block header / logo key
    Model            | <value>
    ...spec rows...
    (blank)
    Truck Info -                    <- truck block header
    Make             | <value>
    ...spec rows...
    (blank)
    <...>Package Price $ | <value>  <- price line
    (blank)
    Contact Name and Tel. # | <name>
    (blank)                 | <phone>   <- phone in col C on the NEXT row

Locked decisions:
- Render every label/value pair found; skip pairs whose value is blank.
- Missing/unparseable spreadsheet -> SpecParseError (endpoint returns error).
- Values stringified (Year can be int 2023 or str 'new').
"""

from __future__ import annotations
import re
import pandas as pd

LABEL_COL = 1
VALUE_COL = 2

PRODUCT_GROUP_MARKER = "product group"
TRUCK_MARKER = "truck info"
PRICE_MARKER = "package price"
CONTACT_MARKER = "contact name"

_PHONE_RE = re.compile(r"[\d][\d\-.\(\)\s]{6,}")


class SpecParseError(Exception):
    """Raised when the spreadsheet cannot be parsed into a usable product spec."""


def _clean(value) -> str:
    """Stringify a cell, trim whitespace. NaN/None -> ''; 2023.0 -> '2023'."""
    if value is None:
        return ""
    if isinstance(value, float):
        if pd.isna(value):
            return ""
        if value.is_integer():
            return str(int(value))
    return str(value).strip()


def parse_spec(path: str) -> dict:
    """Parse the spreadsheet into a structured spec dict. Raises SpecParseError."""
    try:
        df = pd.read_excel(path, sheet_name=0, header=None)
    except Exception as e:  # noqa: BLE001
        raise SpecParseError(f"Could not read spreadsheet: {e}") from e

    if df.shape[1] <= VALUE_COL:
        raise SpecParseError(
            f"Expected value column at index {VALUE_COL}; sheet has {df.shape[1]} columns."
        )

    labels = [_clean(df.iloc[i, LABEL_COL]) for i in range(df.shape[0])]
    values = [_clean(df.iloc[i, VALUE_COL]) for i in range(df.shape[0])]

    product_group = ""
    logo_key = ""
    product_pairs: list[tuple[str, str]] = []
    truck_pairs: list[tuple[str, str]] = []
    price = ""
    contact_name = ""
    contact_phone = ""
    section = None  # None | "product" | "truck"

    for i, label in enumerate(labels):
        low = label.lower()
        value = values[i]

        if low.startswith(PRODUCT_GROUP_MARKER):
            product_group = _extract_product_group(label)
            logo_key = _logo_key_from_group(product_group)
            section = "product"
            continue
        if low.startswith(TRUCK_MARKER):
            section = "truck"
            continue
        if PRICE_MARKER in low:
            price = value
            section = None
            continue
        if low.startswith(CONTACT_MARKER):
            contact_name = value
            contact_phone = _find_phone_after(values, i)
            section = None
            continue

        if section and label and value:
            (product_pairs if section == "product" else truck_pairs).append((label, value))

    _validate(product_group, product_pairs, truck_pairs)

    return {
        "product_group": product_group,
        "logo_key": logo_key,
        "product": product_pairs,
        "truck": truck_pairs,
        "price": price,
        "contact": {"name": contact_name, "phone": contact_phone},
    }


def _extract_product_group(label: str) -> str:
    """'Product Group HIAB Boom Truck Package (default text)' -> 'HIAB Boom Truck Package'."""
    text = re.sub(r"^\s*product group\s*", "", label, flags=re.IGNORECASE)
    text = re.sub(r"\s*\(.*?\)\s*$", "", text)
    return text.strip()


def _logo_key_from_group(group: str) -> str:
    """Map product-group string to a logo key. Unknown -> '' (endpoint fallback)."""
    g = group.lower()
    for needle in ("hiab", "moffett", "palfinger", "multilift"):
        if needle in g:
            return needle
    return ""


def _find_phone_after(values, contact_idx: int) -> str:
    """Look in the value column of the next few rows for a phone-like string."""
    for offset in range(1, 4):
        j = contact_idx + offset
        if j >= len(values):
            break
        v = values[j]
        if v and _PHONE_RE.fullmatch(v):
            return v
    return ""


def _validate(product_group, product_pairs, truck_pairs) -> None:
    if not product_group:
        raise SpecParseError("No 'Product Group' header found in spreadsheet.")
    if not product_pairs and not truck_pairs:
        raise SpecParseError("No spec rows found in product or truck sections.")
    labels = {l.lower() for l, _ in product_pairs}
    if "model" not in labels:
        raise SpecParseError("Product section has no 'Model' row (needed for title/slug).")
