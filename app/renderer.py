"""
renderer.py
Render a Framework.php product page from parsed spec + asset info.

Mirrors the structure of the reference page
(moffett-m8-...-package-for-sale.php): Framework include, configure() array,
<h1> with product-group logo, build_sirv_video(), build_gallery(), two spec
tables (one row per non-blank label/value pair), and a contact block.

All dynamic text is PHP-escaped for single-quoted string context and
HTML-escaped for markup context to avoid breaking the generated file on values
that contain quotes/inch-marks (e.g.  59'1" ).
"""

from __future__ import annotations
import html
import re

# Logo file per product-group key. Paths follow the reference page convention
# (/media/material-handling-equipment/<group>/<group>-logo.svg).
LOGO_PATHS = {
    "hiab": "/media/material-handling-equipment/hiab/hiab-logo.svg",
    "moffett": "/media/material-handling-equipment/moffett/moffett-logo.svg",
    "palfinger": "/media/material-handling-equipment/palfinger/palfinger-logo.svg",
    "multilift": "/media/material-handling-equipment/multilift/multilift-logo.svg",
}
DEFAULT_LOGO = "/media/material-handling-equipment/atlas-polar-logo.svg"

# Section icons are fixed (locked decision).
ICON_PRODUCT = "../../icon-crane.png"
ICON_TRUCK = "../../icon-truck.png"


def _php_sq(s: str) -> str:
    """Escape for a PHP single-quoted string literal: backslash and single quote."""
    return s.replace("\\", "\\\\").replace("'", "\\'")


EQUIPMENT_TYPE = {
    "hiab": "truck-mounted crane",
    "palfinger": "truck-mounted crane",
    "moffett": "truck-mounted forklift",
    "multilift": "hooklift system",
}
DEFAULT_EQUIPMENT_TYPE = "unit"


MAX_DESCRIPTION = 150


def build_description(spec: dict) -> str:
    """
    Meta description, kept under MAX_DESCRIPTION characters.

    Uses the simplified (short) model. Builds progressively richer variants and
    returns the longest one that still fits: full (with accessories/spec facts +
    truck) -> trimmed (model + type + truck) -> minimal (model + type).
    """
    from .naming import short_model  # local import avoids a cycle at module load

    model = short_model(spec)
    etype = EQUIPMENT_TYPE.get(spec["logo_key"], DEFAULT_EQUIPMENT_TYPE)

    truck_make = _first(spec["truck"], "make")
    truck_model = _first(spec["truck"], "model")
    truck = " ".join(p for p in (truck_make, truck_model) if p).strip()
    truck_clause = ", mounted on a truck" if truck else ""

    # Richest detail clause: accessories, else year/outreach/extensions.
    accessories = _first(spec["product"], "accessories")
    if accessories:
        detail = f" featuring {accessories.rstrip('.')}"
    else:
        facts = []
        year = _first(spec["product"], "year")
        if year:
            facts.append("a new model" if "new" in year.lower() else f"a {year} model")
        outreach = _first(spec["product"], "hydraulic outreach")
        if outreach:
            facts.append(f"{_lead_outreach(outreach)} outreach")
        extensions = _first(spec["product"], "no of hydraulic extensions")
        if extensions:
            facts.append(f"{extensions} hydraulic extensions")
        detail = (" with " + _join_list(facts)) if facts else ""

    base = f"The {model} is a {etype}"

    full = f"{base}{detail}{truck_clause}."
    if len(full) <= MAX_DESCRIPTION:
        return full

    # Too long: try keeping the truck clause and truncating the detail to fit.
    if detail:
        room = MAX_DESCRIPTION - len(base) - len(truck_clause) - 1  # -1 for '.'
        if room > 12:  # only worth it if a meaningful slice remains
            trimmed = _truncate_clause(detail, room)
            candidate = f"{base}{trimmed}{truck_clause}."
            if len(candidate) <= MAX_DESCRIPTION:
                return candidate

    for c in (f"{base}{truck_clause}.", f"{base}."):
        if len(c) <= MAX_DESCRIPTION:
            return c
    return _truncate(f"{base}.", MAX_DESCRIPTION)


def _lead_outreach(outreach: str) -> str:
    """Take just the first figure from a messy outreach string, e.g.
    \"71'10\\\" with Jib/ 38'5\\\" ...\" -> \"71'10\\\"\"."""
    m = re.match(r"[\d'\"\.\s]+", outreach)
    return m.group(0).strip() if m else outreach


def _truncate_clause(clause: str, limit: int) -> str:
    """Trim a leading clause (e.g. ' featuring ...') to <= limit chars on a word
    boundary, dropping trailing punctuation. Keeps the leading space."""
    if len(clause) <= limit:
        return clause
    cut = clause[:limit].rsplit(" ", 1)[0].rstrip(",;:/ ")
    return cut


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",;: ")
    return cut + "."


def _join_list(items):
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _article(phrase: str) -> str:
    return "an" if phrase[:1].lower() in "aeiou" else "a"





def _h(s: str) -> str:
    """HTML-escape for markup context."""
    return html.escape(s, quote=True)


def _rows(pairs) -> str:
    out = []
    for label, value in pairs:
        out.append(
            "        <tr>\n"
            f"            <th>{_h(label)}:</th>\n"
            f"            <td>{_h(value)}</td>\n"
            "        </tr>"
        )
    return "\n".join(out)


def _gallery(image_names, alt) -> str:
    alt_sq = _php_sq(alt)
    lines = ["\t\t<?php", "\t\t$framework->build_gallery(array("]
    for name in image_names:
        lines.append(f"\t\t\tarray('{_php_sq(name)}', '{alt_sq}'),")
    lines.append("\t\t));")
    lines.append("\t\t?>")
    return "\n".join(lines)


def render_page(
    spec: dict,
    *,
    title: str,
    heading: str = None,
    menu_url: str,
    media_path: str,
    sirv_video_url: str,
    image_names,
    product_icon: str = ICON_PRODUCT,
    truck_icon: str = ICON_TRUCK,
) -> str:
    """Return the full .php page as a string.

    `title` populates the SEO <title>/item_name; `heading` is the visible H1.
    If `heading` is omitted it falls back to `title`.
    """
    logo = LOGO_PATHS.get(spec["logo_key"], DEFAULT_LOGO)
    group = spec["product_group"]  # e.g. 'HIAB Boom Truck Package'
    heading_text = heading if heading is not None else title

    description = build_description(spec)

    product_table = _rows(spec["product"])
    truck_table = _rows(spec["truck"])

    video_block = ""
    if sirv_video_url:
        video_block = (
            f'        <?php $framework->build_sirv_video("{sirv_video_url}"); ?>\n'
        )

    contact = spec["contact"]
    contact_name = _h(contact.get("name", ""))
    contact_phone_raw = contact.get("phone", "")
    contact_tel = _tel_href(contact_phone_raw)

    page = f"""<?php
include "../responsive/Framework.php";
$framework->getForm();
$framework->configure(
        array(
            'item_name' => "{_php_dq(title)}",
            'short_name' => "{_php_dq(title)}",
            'description' => "{_php_dq(description)}",
            'menu_url' => "{menu_url}",
            'media_path' => '{_php_sq(media_path)}',
            'title' => '{_php_sq(title)}'
        )
);
$framework->build_header();
?>
<div class="ppc">
<h1 itemprop="headline" class="product-heading">
    <?php $framework->build_image('{logo}', '{_php_sq(group)}', 'height="25" class="small-logo"'); ?> {_h(heading_text)}</h1>
<div class="top-content">
    <div id="product-img">
{video_block}{_gallery(image_names, title)}
    </div>
    <div class="feature-bullets">

		<form class="product-quote-form" id="quote-form" method="post" action="/material-handling-equipment/m-info-request.php">
		<h4>Get a quote by calling <a href="tel:{contact_tel}">{contact_phone_raw}</a> or complete the form below.</h4>
		<?php $framework->quoteform(false); ?>
		<input type="submit" value="Get a Quote" />
		</form>
    </div>
</div>

<div class="demo-used-info">
<div class="demo-used-block">
    <h3><?php $framework->build_image('{product_icon}', '{_php_sq(group)}'); ?> {_h(group)} Details</h3>
    <table>
{product_table}
    </table>
</div>
<div class="demo-used-block right">
	<h3><?php $framework->build_image('{truck_icon}', 'Truck'); ?> Truck Details</h3>
    <table>
{truck_table}
    </table>
</div>
<div class="demo-used-block">
    <h3>Contact Details</h3>
    <table>
		<tr>
            <th>{contact_name}</th><td><a href="tel:{contact_tel}">{contact_phone_raw}</a></td>
        </tr>
    </table>
</div>
</div>
</div>
<?php $framework->build_footer(); ?>
"""
    return page


def _first(pairs, label_lower: str) -> str:
    for label, value in pairs:
        if label.lower() == label_lower:
            return value
    return ""


def _php_dq(s: str) -> str:
    """Escape for a PHP double-quoted string literal."""
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$")


def _tel_href(phone: str) -> str:
    """Digits only, for the tel: href."""
    return "".join(ch for ch in phone if ch.isdigit())
