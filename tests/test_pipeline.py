"""Unit tests for the page-builder pipeline. Run: PYTHONPATH=. python -m pytest tests/ -q"""
import os, tempfile, pytest
from app.spec_parser import parse_spec, SpecParseError
from app.naming import build_title, base_slug, slugify, resolve_slug, derive_paths
from app.renderer import render_page
from app.downloader import _host_allowed, _leading_num, download_all, DownloadError

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "Hiab_262_Jib_Pkg_VIN428061.xls")

def test_parse_real_sheet():
    spec = parse_spec(SAMPLE)
    assert spec["logo_key"] == "hiab"
    assert spec["product_group"] == "HIAB Boom Truck Package"
    assert ("Model", "Hiab HiPro 262E-4+Jib 70x3") in spec["product"]
    # blanks skipped
    labels = [l for l,_ in spec["truck"]]
    assert "Manufacturer" not in labels and "Wheelbase (WB)" not in labels
    assert spec["contact"] == {"name": "Nick Georgoussis", "phone": "647.290.2764"}

def test_parse_missing_model(tmp_path):
    import pandas as pd
    p = tmp_path/"bad.xlsx"
    pd.DataFrame([[None,"Product Group HIAB Boom Truck Package",None],
                  [None,"Year","2023"]]).to_excel(p, header=False, index=False)
    with pytest.raises(SpecParseError):
        parse_spec(str(p))

def test_title_and_slug():
    spec = parse_spec(SAMPLE)
    t = build_title(spec)
    assert t == "Hiab HiPro 262E Crane + Truck Package for Sale | Atlas Polar"
    assert "Work-Ready" not in t  # dropped from SEO title
    assert t.endswith("| Atlas Polar")
    assert base_slug(spec).endswith("package-for-sale")
    assert "work-ready" not in base_slug(spec)
    assert "+" not in base_slug(spec)

def test_heading_keeps_workready_no_brand():
    from app.naming import build_heading
    spec = parse_spec(SAMPLE)
    h = build_heading(spec)
    assert h == "Hiab HiPro 262E Crane + Truck - Work-Ready Package for Sale"
    assert "Atlas Polar" not in h  # brand only in SEO title
    # used unit drops Work-Ready in the H1 too
    used = dict(spec)
    used["truck"] = [(l, ("2019" if v == "new" else v)) for l, v in spec["truck"]]
    assert build_heading(used) == "Hiab HiPro 262E Crane + Truck - Package for Sale"

def test_short_model():
    from app.naming import short_model
    spec = parse_spec(SAMPLE)
    assert short_model(spec) == "Hiab HiPro 262E"

def test_new_status_and_title():
    from app.naming import is_new
    spec = parse_spec(SAMPLE)
    assert is_new(spec) is True
    used = dict(spec)
    used["truck"] = [(l, ("2019" if v == "new" else v)) for l, v in spec["truck"]]
    assert is_new(used) is False
    assert build_title(used) == "Hiab HiPro 262E Crane + Truck Package for Sale | Atlas Polar"
    assert base_slug(used) == base_slug(spec)

def test_description_under_150_all_branches():
    from app.renderer import build_description
    spec = parse_spec(SAMPLE)
    d = build_description(spec)
    assert len(d) <= 150
    assert d.startswith("The Hiab HiPro 262E is a truck-mounted crane")
    assert "mounted on a truck" in d
    assert "an truck" not in d  # article grammar
    assert d.endswith(".")
    # fallback path also under 150 and includes spec facts
    no_acc = dict(spec)
    no_acc["product"] = [(l, v) for l, v in spec["product"] if l.lower() != "accessories"]
    d2 = build_description(no_acc)
    assert len(d2) <= 150
    assert "hydraulic extensions" in d2

def test_slugify_edge_cases():
    assert slugify("A/B & C's \"thing\"") == "a-b-and-cs-thing"
    assert slugify("262E-4+Jib 70x3") == "262e-4-jib-70x3"

def test_collision_suffix():
    spec = parse_spec(SAMPLE)
    taken = {base_slug(spec), base_slug(spec)+"-2"}
    assert resolve_slug(spec, lambda s: s in taken) == base_slug(spec)+"-3"

def test_host_allowlist():
    assert _host_allowed("trello.com")
    assert _host_allowed("abc123.trellousercontent.com")
    assert not _host_allowed("evil.com")
    assert not _host_allowed("trello.com.evil.com")

def test_video_ordering_key():
    assert _leading_num("2.mp4") == 2 and _leading_num("10.mov") == 10
    assert _leading_num("clip.mp4") == 10**9  # unnumbered last

def test_download_rejects_bad_host(tmp_path):
    with pytest.raises(DownloadError):
        download_all([{"url":"https://evil.com/x.xls","name":"x.xls"}], str(tmp_path))

def test_render_structure():
    spec = parse_spec(SAMPLE)
    page = render_page(spec, title="T", menu_url="/demo-used-equipment/t.html",
                       media_path="demo-used-equipment/hiab-boom-trucks/t/",
                       sirv_video_url="https://blueprint.sirv.com/x.mp4",
                       image_names=["1.jpg","2.jpg"])
    assert 'include "../responsive/Framework.php";' in page
    assert "$framework->build_sirv_video(" in page
    assert page.count("<?php") == page.count("?>")  # balanced php tags
    assert "$framework->build_gallery(array(" in page
    assert "$framework->build_footer();" in page
    # gallery must be inside php tags
    gi = page.index("build_gallery")
    assert "<?php" in page[max(0,gi-40):gi]
