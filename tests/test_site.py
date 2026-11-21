"""The website (docs/, served at klarbefund.mabu.red) says what the code does.

The English and German pages name counts that come from the code: the
reference ranges the knowledge layer seeds, the anamnesis protocols, and
the prompts and guides of the Mac app's MCP server. A change to any of them
fails here until both pages follow. The pages also load nothing from another
host (the privacy policy says so), and the two languages show the same
sections and pictures.
"""

import re
from pathlib import Path

from health_graph import knowledge, protocols

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
EN = DOCS / "index.html"
DE = DOCS / "de" / "index.html"
PAGES = [EN, DE, DOCS / "imprint.html", DOCS / "privacy.html", DOCS / "3d" / "index.html"]
CATALOG = ROOT / "apps" / "mac" / "Shared" / "MCPCatalog.swift"

WORDS_EN = {10: "Ten", 11: "Eleven", 12: "Twelve"}
WORDS_DE = {10: "Zehn", 11: "Elf", 12: "Zwölf"}


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _catalog_counts() -> tuple[int, int]:
    src = _text(CATALOG)
    prompts = src[src.index("static let prompts"):src.index("// ── guides")]
    guides = src[src.index("static var guides"):]
    return len(re.findall(r"^\s*Prompt\(", prompts, re.M)), len(re.findall(r"^\s*Guide\(", guides, re.M))


def test_ranges_match_the_knowledge_layer():
    n = len(knowledge._range_rows())
    assert f"{n} reference ranges" in _text(EN)
    assert f"{n} Referenzbereiche" in _text(DE)


def test_questionnaires_match_the_protocols():
    n = len(protocols.PROTOCOLS)
    assert f"{WORDS_EN[n]} validated questionnaires" in _text(EN)
    assert f"{WORDS_DE[n]} validierte Fragebögen" in _text(DE)


def test_prompts_and_guides_match_the_mac_catalog():
    prompts, guides = _catalog_counts()
    assert f"{prompts} ready prompts and {guides} guides" in _text(EN)
    assert f"{prompts} fertige Prompts und {guides} Guides" in _text(DE)


def test_both_languages_show_the_same_sections_and_pictures():
    def shape(p):
        t = _text(p)
        return re.findall(r'<section id="([^"]+)"', t), sorted(set(re.findall(r'<img[^>]* src="([^"]+)"', t)))
    assert shape(EN) == shape(DE)


def test_nothing_is_loaded_from_another_host():
    for p in PAGES:
        t = _text(p)
        for tag in re.findall(r"<script[^>]*\ssrc=\"[^\"]+\"|<link[^>]*rel=\"stylesheet\"[^>]*>|<img[^>]*\ssrc=\"[^\"]+\"", t):
            src = re.search(r'(?:src|href)="([^"]+)"', tag).group(1)
            assert src.startswith("/") or not re.match(r"[a-z]+:", src), f"{p.name}: {src}"


def test_no_em_dashes():
    for p in PAGES[:4]:
        assert "—" not in _text(p), p.name


def test_sitemap_lists_pages_that_exist():
    locs = re.findall(r"<loc>https://klarbefund\.mabu\.red/([^<]*)</loc>", _text(DOCS / "sitemap.xml"))
    assert locs
    for loc in locs:
        path = DOCS / loc
        assert (path / "index.html").exists() if loc == "" or loc.endswith("/") else path.exists(), loc
