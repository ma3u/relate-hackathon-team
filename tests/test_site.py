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
        # a picture may have a German version: name.png on the English page, name-de.png on the German one
        imgs = {re.sub(r"-de(\.\w+)$", r"\1", src) for src in re.findall(r'<img[^>]* src="([^"]+)"', t)}
        return re.findall(r'<section id="([^"]+)"', t), sorted(imgs)
    assert shape(EN) == shape(DE)


def test_the_german_page_shows_german_pictures_where_they_exist():
    """A picture with a German version (name-de.png next to name.png) is shown in German on /de/."""
    de = _text(DE)
    for src in re.findall(r'<img[^>]* src="(/[^"]+)\.(png|jpg)"', _text(EN)):
        path, ext = src
        if (DOCS / f"{path.lstrip('/')}-de.{ext}").exists():
            assert f'src="{path}-de.{ext}"' in de, path

def test_nothing_is_loaded_from_another_host():
    for p in PAGES:
        t = _text(p)
        for tag in re.findall(r"<script[^>]*\ssrc=\"[^\"]+\"|<link[^>]*rel=\"stylesheet\"[^>]*>|<img[^>]*\ssrc=\"[^\"]+\"", t):
            src = re.search(r'(?:src|href)="([^"]+)"', tag).group(1)
            assert src.startswith("/") or not re.match(r"[a-z]+:", src), f"{p.name}: {src}"


def test_no_em_dashes():
    for p in PAGES[:4]:
        assert "—" not in _text(p), p.name


def test_language_switch_names_what_it_shows():
    """WCAG 2.2: the accessible name starts with the visible label (2.5.3), each link says its
    language (3.1.2), and the page's own language is marked current."""
    for page, own in ((EN, "en"), (DE, "de")):
        t = _text(page)
        group = re.search(r'<span class="langs"[^>]*>(.*?)</span>(?=\n)', t, re.S).group(1)
        links = re.findall(r"<a ([^>]*)>([A-Z]{2})<span class=\"sr-only\"> (\w+)</span></a>", group)
        assert [code for _, code, _ in links] == ["EN", "DE"], page
        for attrs, code, name in links:
            assert "aria-label" not in attrs
            assert f'lang="{code.lower()}"' in attrs and f'hreflang="{code.lower()}"' in attrs
            assert name.upper().startswith(code)
            assert ("aria-current" in attrs) == (code.lower() == own), (page, code)


def test_phone_menu_indexes_every_section():
    """The phone menu lists every section of the page, in page order, and its button names and
    controls it (WCAG 2.2: 4.1.2); a section added to the page fails here until the menu has it."""
    for page in (EN, DE):
        t = _text(page)
        sections = re.findall(r'<section id="([^"]+)"', t)
        btn = re.search(r'<button class="menu-btn"([^>]*)>(.*?)</button>', t, re.S)
        assert 'aria-controls="toc"' in btn.group(1) and 'aria-expanded="false"' in btn.group(1), page
        assert re.search(r'<span class="sr-only">\w+</span>$', btn.group(2)), page
        toc = re.search(r'<nav id="toc" class="toc" aria-label="[^"]+" hidden>(.*?)</nav>', t, re.S).group(1)
        assert re.findall(r'<li><a href="#([^"]+)">', toc) == sections, page

def test_every_page_picks_its_theme_before_painting_and_offers_the_switch():
    """Day and night: each page sets data-theme in <head> before the stylesheet loads (no flash),
    from a stored choice or the sun where the visitor is, and offers a named toggle (WCAG 2.2: 4.1.2).
    All pages carry the same sun calculation."""
    for page in PAGES[:4]:
        t = _text(page)
        head = t[:t.index("</head>")]
        script = head.index('localStorage.getItem("kb-theme")')
        assert 'kbSunUp(new Date()' in head[script:] and 'timeZone' in head[script:] and 'data-theme' in head[script:], page.name
        assert script < head.index('rel="stylesheet"'), page.name
        assert '<meta name="color-scheme" content="dark light">' in head, page.name
        buttons = re.findall(r'<button class="theme-btn[^"]*" type="button" aria-pressed="true" hidden>(.*?)</button>', t, re.S)
        assert buttons, page.name
        for b in buttons:
            assert re.search(r'<span class="(sr-only|lbl)">[^<]+</span>', b), page.name
        assert '<script src="/site/site.js">' in t, page.name
    suns = {re.search(r'function kbSunUp.*?return [^}]*}', _text(p)).group(0) for p in PAGES[:4]}
    assert len(suns) == 1
    for page in (EN, DE):
        toc = re.search(r'<nav id="toc".*?</nav>', _text(page), re.S).group(0)
        assert 'class="theme-btn"' in toc, page.name

def test_sitemap_lists_pages_that_exist():
    locs = re.findall(r"<loc>https://klarbefund\.mabu\.red/([^<]*)</loc>", _text(DOCS / "sitemap.xml"))
    assert locs
    for loc in locs:
        path = DOCS / loc
        assert (path / "index.html").exists() if loc == "" or loc.endswith("/") else path.exists(), loc
