"""
naming.py
Derive the page title, URL slug, filename, menu_url and media_path from the spec.

Locked decisions:
- Title/slug from crane Model + truck Make + truck Model.
- On slug collision, append a numeric suffix (-2, -3, ...). Never overwrite.
- Collision is checked via a caller-supplied `exists(slug)` predicate so the
  same logic works against FTP (production) or the local filesystem (tests).
"""

from __future__ import annotations
import re


def _first(pairs, label_lower: str) -> str:
    for label, value in pairs:
        if label.lower() == label_lower:
            return value
    return ""


def is_new(spec: dict) -> bool:
    """True if 'new' appears (case-insensitive) in any Year or Mileage value."""
    for block in ("product", "truck"):
        for label, value in spec[block]:
            if label.lower() in ("year", "mileage") and "new" in value.lower():
                return True
    return False


# Type word per product-group key, used in the title/description.
TYPE_WORD = {
    "hiab": "Crane",
    "palfinger": "Crane",
    "moffett": "Forklift",
    "multilift": "Hooklift",
}
DEFAULT_TYPE_WORD = "Unit"

BRAND = "Atlas Polar"


def short_model(spec: dict) -> str:
    """
    Reduce the crane model to its core: cut at the first '-' or '+'.
    'Hiab HiPro 262E-4+Jib 70x3' -> 'Hiab HiPro 262E'
    """
    model = _first(spec["product"], "model")
    cut = re.split(r"[-+]", model, maxsplit=1)[0]
    return cut.strip()


def type_word(spec: dict) -> str:
    return TYPE_WORD.get(spec["logo_key"], DEFAULT_TYPE_WORD)


def build_title(spec: dict) -> str:
    """
    SEO <title> / item_name. Drops 'Work-Ready' regardless of new/used.
    'Hiab HiPro 262E Crane + Truck Package for Sale | Atlas Polar'
    """
    lead = _title_lead(spec)
    return f"{lead} Package for Sale | {BRAND}".strip()


def build_heading(spec: dict) -> str:
    """
    Visible H1. Keeps 'Work-Ready' when new; no brand suffix.
    'Hiab HiPro 262E Crane + Truck - Work-Ready Package for Sale'
    """
    lead = _title_lead(spec)
    package = "Work-Ready Package for Sale" if is_new(spec) else "Package for Sale"
    return f"{lead} - {package}".strip()


def _title_lead(spec: dict) -> str:
    """Shared '<short model> <Type>[ + Truck]' prefix."""
    model = short_model(spec)
    twd = type_word(spec)
    has_truck = bool(_first(spec["truck"], "make") or _first(spec["truck"], "model"))
    lead = " ".join(p for p in (model, twd) if p)
    if has_truck:
        lead += " + Truck"
    return lead


def slugify(text: str) -> str:
    """Lowercase, ASCII-ish, hyphen-separated URL slug."""
    text = text.lower()
    text = text.replace("+", " ")           # 262E-4+Jib -> '262e-4 jib' (matches existing site slugs)
    text = text.replace("&", " and ")
    text = re.sub(r"['\"]", "", text)        # drop quotes/feet-inch marks
    text = re.sub(r"[^a-z0-9]+", "-", text)   # non-alnum -> hyphen
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text


def base_slug(spec: dict) -> str:
    # Slug is derived from the stable title form (always 'Package for Sale',
    # never 'Work-Ready') so a unit's new/used status never changes its URL.
    crane_model = _first(spec["product"], "model")
    truck_make = _first(spec["truck"], "make")
    truck_model = _first(spec["truck"], "model")
    truck_part = " ".join(p for p in (truck_make, truck_model) if p).strip()
    pieces = [crane_model]
    if truck_part:
        pieces.append(truck_part)
    pieces.append("Package for Sale")
    return slugify(" ".join(pieces))


def resolve_slug(spec: dict, exists) -> str:
    """
    Return a unique slug. `exists(slug: str) -> bool` reports whether a page
    with that slug is already published. Appends -2, -3, ... until free.
    """
    base = base_slug(spec)
    if not exists(base):
        return base
    n = 2
    while exists(f"{base}-{n}"):
        n += 1
    return f"{base}-{n}"


def derive_paths(slug: str, product_group_dir: str) -> dict:
    """
    Build the framework paths from the slug.

    product_group_dir is the equipment sub-folder used in media_path, e.g.
    'moffett-forklifts' or 'hiab-boom-trucks'. Kept as an explicit argument
    because it's a site-taxonomy choice, not derivable from the slug alone.
    """
    filename = f"{slug}.php"
    menu_url = f"/demo-used-equipment/{slug}.html"
    media_path = f"demo-used-equipment/{product_group_dir}/{slug}/"
    return {
        "filename": filename,
        "menu_url": menu_url,
        "media_path": media_path,
    }
