"""Recommendations of a Norwegian national guideline, read through Helsedirektoratet's open API.

German first (issue #23): a German guideline answers a clinical question, and another country's
recommendation stands next to it only when the question has a reason (evidence.question_rows).
This module reads the Norwegian guideline on preventing cardiovascular disease
(Nasjonal faglig retningslinje for forebygging av hjerte- og karsykdom) from HAPI, the open API of
the Norwegian Directorate of Health, and writes the same artefact as guidelines.py: one record per
recommendation (anbefaling), with its GRADE strength (sterk, svak), its direction as its own field,
the link to its page, the lab values its wording names (LOINC), the codes HAPI gives it (SNOMED CT,
ICD-10, ICPC-2), the clinical questions it answers and a SHA-256 of its wording.

Licence: the content is under NLOD 2.0 with the HAPI terms of use: name Helsedirektoratet as the
source, mark the content, do not change its meaning, and do not look like a service of the
directorate. NLOD would allow storing the wording. The record still carries facts only, like a German
box, until a person has checked how HAPI marks the statement, its strength and its direction; the
artefact names Helsedirektoratet and links each recommendation to its page.

Access: HAPI needs a free subscription key (utvikler.helsedirektoratet.no, product "Utviklere"). The
key is read from HAPI_SUBSCRIPTION_KEY or ~/.config/klarbefund/hapi.key (mode 600), never printed and
never written anywhere. No personal data goes to the API: requests name content, never a person.

The field names HAPI uses are read defensively: a strength, direction or date this reader cannot
find holds the record back (needsReview) instead of being guessed. `--dump` keeps the raw responses
locally for checking the reader against the live API.

Usage:
  python -m health_graph.norway extract [--out <file>] [--dump <dir>]
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import os
import re
import stat
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from health_graph import guidelines

API = "https://api.helsedirektoratet.no"
WEB = "https://www.helsedirektoratet.no"
KEY_ENV = "HAPI_SUBSCRIPTION_KEY"
KEY_FILE = Path.home() / ".config" / "klarbefund" / "hapi.key"
PAUSE = 0.25  # seconds between calls: the API is shared and free

GUIDELINE_ID = "hdir-hjerte-kar"  # evidence.GUIDELINES, register "HDIR hjerte-kar"
SLUG = "forebygging-av-hjerte-og-karsykdom"
TITLE = "Nasjonal faglig retningslinje for forebygging av hjerte- og karsykdom"

NOTICE = (
    "Facts about recommendations of Helsedirektoratet's national guideline on preventing cardiovascular "
    "disease (NLOD 2.0, source: Helsedirektoratet), no guideline text. The wording is on the page linked."
)

# The page (slug under the guideline) of each recommendation that answers one of the statin questions
# (evidence.QUESTIONS). Read from the guideline's pages on 2026-11-28; a recommendation not listed answers
# no question yet. Muscle symptoms have no recommendation of their own in this guideline.
QUESTION_OF_SLUG: dict[str, list[str]] = {
    "bruk-av-statiner-og-andre-lipidsenkende-legemidler-ved-primaerforebygging-av-hjerte-og-karsykdom":
        ["q-statin-primary"],
    "risikovurdering-og-grense-for-legemiddelbehandling-ved-forebygging-av-hjerte-og-karsykdom":
        ["q-statin-primary"],
    "oppfolgning-og-mal-for-kontroll-ved-forebygging-av-hjerte-og-karsykdom": ["q-ldl-target"],
    "bruk-av-statiner-og-andre-lipidsenkende-medikamenter-ved-sekundaerforebygging-av-aterosklerotisk-hjerte-"
    "og-karsykdom": ["q-ldl-target"],
    "utredning-av-lipidverdiene-ved-primaer-og-sekundaerforebygging-av-hjerte-og-karsykdom": ["q-lpa-measurement"],
    "statinbehandling-hos-eldre-75-ar": ["q-statin-over-75"],
}

# Lab values a Norwegian wording names, with the LOINC codes guidelines.MARKERS uses for the same value.
_CODES = {term: codes for term, _, codes in guidelines.MARKERS}
MARKERS: list[tuple[str, str, list[str]]] = [
    ("LDL-kolesterol", r"\bLDL", _CODES["LDL-Cholesterin"]),
    ("Lp(a)", r"\bLp\s?\(a\)|[Ll]ipoprotein\s?\(a\)", ["10835-7"]),
    ("HbA1c", r"\bHbA1c\b", _CODES["HbA1c"]),
    ("eGFR", r"\beGFR\b", _CODES["eGFR"]),
    ("Blodtrykk", r"[Bb]lodtrykk", _CODES["Blutdruck"]),
]

# The recommendation's direction, read from its first sentence when HAPI gives no field for it.
NEGATIVE = re.compile(r"\b(?:anbefales\s+ikke|ikke\s+anbefales|bør\s+ikke|skal\s+ikke|frarådes|"
                      r"ikke\s+(?:gis|brukes|startes|tilbys|igangsettes))\b", re.I)
POSITIVE = re.compile(r"\b(?:anbefales|anbefaler|bør|skal|kan\s+vurderes|kan\s+tilbys|vurderes)\b", re.I)
STRENGTH_IN_TEXT = re.compile(r"\b(sterk|svak)\s+anbefaling\b", re.I)
DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})|(\d{2})\.(\d{2})\.(\d{4})")


# ── access ──────────────────────────────────────────────────────────────────

def api_key() -> str:
    """The subscription key, from the environment or the key file; never printed."""
    key = os.environ.get(KEY_ENV, "").strip()
    if key:
        return key
    if not KEY_FILE.exists():
        raise SystemExit(
            f"No HAPI subscription key. Sign up at https://utvikler.helsedirektoratet.no, subscribe to the "
            f"product 'Utviklere', and save the Ocp-Apim-Subscription-Key in {KEY_FILE} (chmod 600), "
            f"or set {KEY_ENV}.")
    if KEY_FILE.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise SystemExit(f"{KEY_FILE} is readable by others: run chmod 600 \"{KEY_FILE}\"")
    key = KEY_FILE.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"[A-Za-z0-9]{16,64}", key):
        raise SystemExit(f"{KEY_FILE} does not hold a subscription key (letters and digits only).")
    return key


class Client:
    """GET requests to HAPI with the subscription key; optional dump of every response."""

    def __init__(self, key: str, dump: Path | None = None, opener=urllib.request.urlopen):
        self._key, self._dump, self._open, self._last = key, dump, opener, 0.0

    def get(self, path_or_url: str, params: dict | None = None):
        url = path_or_url if path_or_url.startswith("https://") else API + path_or_url
        if not url.startswith(API + "/"):
            raise ValueError(f"not a HAPI address: {url}")
        if params:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
        wait = PAUSE - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        req = urllib.request.Request(url, headers={"Ocp-Apim-Subscription-Key": self._key,
                                                   "Accept": "application/json",
                                                   "User-Agent": "klarbefund-guidelines/1.0"})
        try:
            with self._open(req, timeout=30) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                raise SystemExit("HAPI refused the subscription key (HTTP %d): check the key and that the "
                                 "subscription to 'Utviklere' is active." % e.code) from None
            raise
        finally:
            self._last = time.monotonic()
        data = json.loads(body)
        if self._dump:
            self._dump.mkdir(parents=True, exist_ok=True)
            name = hashlib.sha256(url.encode()).hexdigest()[:16] + ".json"
            (self._dump / name).write_text(json.dumps({"url": url, "data": data}, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
        return data


# ── reading HAPI's content model ────────────────────────────────────────────
# A product (retningslinje) has chapters (kapittel), which have chapters or normative units
# (anbefaling); a unit links its children (referanse, pico). Links carry rel (forelder, barn, root, …),
# type and href. https://www.helsedirektoratet.no/om-oss/apne-data-api/hvordan-finne-frem-i-innholdet

def _items(data) -> list[dict]:
    if isinstance(data, list):
        return [d for d in data if isinstance(d, dict)]
    if isinstance(data, dict):
        for key in ("data", "items", "innhold", "value", "results"):
            if isinstance(data.get(key), list):
                return [d for d in data[key] if isinstance(d, dict)]
        return [data]
    return []


def _links(item: dict) -> list[dict]:
    links = item.get("links") or item.get("lenker") or []
    return [lk for lk in links if isinstance(lk, dict)]


def _type(item: dict) -> str:
    for key in ("infoType", "infotype", "type", "contentType"):
        v = item.get(key)
        if isinstance(v, str) and v:
            return v.lower()
    return ""


def _strings(obj, path: str = ""):
    """(key path, string value) for every string inside obj."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v, path)
    elif isinstance(obj, str):
        yield path, obj


def plain(text: str) -> str:
    """HTML to plain text, whitespace collapsed."""
    text = re.sub(r"<(?:br|/p|/li|/h\d)[^>]*>", " ", text or "", flags=re.I)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", text))).strip()


def web_url(item: dict) -> str | None:
    for key in ("url", "nettside", "webUrl"):
        v = item.get(key)
        if isinstance(v, str) and v.startswith(WEB + "/"):
            return v
    for lk in _links(item):
        href = lk.get("href") or ""
        if isinstance(href, str) and href.startswith(WEB + "/"):
            return href
    return None


def slug(url: str | None) -> str | None:
    return url.rstrip("/").rsplit("/", 1)[-1] if url else None


def iso_date(value: str | None) -> str | None:
    m = DATE.search(value or "")
    if not m:
        return None
    y, mo, d = (m.group(1), m.group(2), m.group(3)) if m.group(1) else (m.group(6), m.group(5), m.group(4))
    try:
        return dt.date(int(y), int(mo), int(d)).isoformat()
    except ValueError:
        return None


def last_change(item: dict) -> str | None:
    """The last professional change (siste faglige endring), else the latest date HAPI gives."""
    dates = [(path.lower(), iso_date(v)) for path, v in _strings(item)]
    for want in ("fagli", "sistoppdatert", "sist"):
        hits = [d for path, d in dates if d and want in path.replace("_", "")]
        if hits:
            return max(hits)
    return None


def strength(item: dict) -> str | None:
    """'sterk' or 'svak': from a field named for the strength, else from the text."""
    for path, v in _strings(item):
        last = path.lower().rsplit(".", 1)[-1]
        if "styrke" in last or "strength" in last:
            m = re.search(r"\b(sterk|svak|strong|weak)", v, re.I)
            if m:
                return {"strong": "sterk", "weak": "svak"}.get(m.group(1).lower(), m.group(1).lower())
    texts = [v for _, v in _strings(item)]
    found = {m.group(1).lower() for t in texts for m in STRENGTH_IN_TEXT.finditer(plain(t))}
    return found.pop() if len(found) == 1 else None


def direction(item: dict, statement: str) -> tuple[str | None, list[str]]:
    """'do' or 'do not', and the reasons to hold the record back when it cannot be read safely."""
    for path, v in _strings(item):
        # a field named for the direction itself ("retningslinje" is the guideline, not a direction)
        if path.lower().rsplit(".", 1)[-1] in ("retning", "anbefalingsretning", "direction"):
            low = v.lower()
            if re.search(r"\bmot\b|\bagainst\b", low):
                return "do not", []
            if re.search(r"\bfor\b", low):
                return "do", []
    first = re.split(r"(?<=[.!?])\s", statement, maxsplit=1)[0] if statement else ""
    if not first:
        return None, ["no wording to read the direction from"]
    if NEGATIVE.search(first):
        return "do not", []
    if re.search(r"\bikke\b", first, re.I):
        return None, ["a negation the reader cannot place: a person reads the direction"]
    if POSITIVE.search(first):
        return "do", []
    return None, ["no recommending verb in the first sentence"]


def statement_of(item: dict) -> str:
    for key in ("tekst", "text", "anbefaling", "innhold"):
        v = item.get(key)
        if isinstance(v, str) and v.strip():
            return plain(v)
    return ""


def codes_of(item: dict) -> list[dict]:
    raw = item.get("koder") or item.get("codes") or []
    names = {s.lower().replace(" ", "-"): s for s in guidelines.CODE_SYSTEMS}
    out: list[tuple[str, str]] = []
    if isinstance(raw, dict):
        for system, codes in raw.items():
            for c in codes if isinstance(codes, list) else [codes]:
                out.append((str(system), str(c.get("kode", c.get("code", "")) if isinstance(c, dict) else c)))
    elif isinstance(raw, list):
        for c in raw:
            if isinstance(c, dict):
                out.append((str(c.get("kodeverk") or c.get("system") or ""), str(c.get("kode") or c.get("code") or "")))
    seen, result = set(), []
    for system, code in out:
        s = names.get(system.lower().replace(" ", "-"))
        if s and guidelines.CODE_RE.match(code) and (s, code) not in seen:
            seen.add((s, code))
            result.append({"system": s, "code": code})
    return result[:40]


def link_loinc(text: str) -> list[dict]:
    return [{"code": code, "term": term} for term, pattern, codes in MARKERS if re.search(pattern, text)
            for code in codes]


# ── walking the guideline ───────────────────────────────────────────────────

def find_guideline(client: Client) -> dict:
    """The guideline's top node: the retningslinje whose page or title is the one on preventing CVD."""
    for item in _items(client.get("/innhold/innhold", {"infoTyper": "retningslinje"})):
        url, title = web_url(item) or "", plain(str(item.get("tittel") or item.get("title") or ""))
        if url.rstrip("/").endswith("/" + SLUG) or title.lower().endswith("forebygging av hjerte- og karsykdom"):
            return item
    raise SystemExit("HAPI lists no guideline on preventing cardiovascular disease: the reader needs a look.")


def walk(client: Client, top: dict, limit: int = 400) -> list[dict]:
    """Every normative unit under the top node, each with the chapter it sits in."""
    found, queue, seen = [], [(top, None)], set()
    while queue and len(seen) < limit:
        item, chapter = queue.pop(0)
        for lk in _links(item):
            if (lk.get("rel") or "").lower() != "barn":
                continue
            href = lk.get("href") or ""
            if not href or href in seen:
                continue
            kind = (lk.get("type") or "").lower()
            if kind in ("referanse", "pico", "fil"):
                continue
            seen.add(href)
            for child in _items(client.get(href)):
                ctype = _type(child) or kind
                if ctype == "anbefaling":
                    found.append({"item": child, "chapter": chapter})
                else:
                    queue.append((child, plain(str(child.get("tittel") or "")) or chapter))
    return found


def record(unit: dict) -> dict:
    item = unit["item"]
    hid = str(item.get("id") or "")
    reasons: list[str] = []
    if not re.fullmatch(r"[A-Za-z0-9-]{1,60}", hid):
        raise ValueError(f"HAPI id '{hid[:80]}' is not an id")
    text = statement_of(item)
    if not text:
        reasons.append("no wording in the API response")
    grade = strength(item)
    if grade is None:
        reasons.append("strength (sterk/svak) not found")
    way, why = direction(item, text)
    reasons += why
    url = web_url(item)
    title = plain(str(item.get("tittel") or ""))
    return {
        "id": f"{GUIDELINE_ID}:{hid}",
        "guidelineId": GUIDELINE_ID,
        "number": hid[:40],
        "type": "recommendation",
        "basis": "GRADE",
        "status": last_change(item),
        "grade": grade,
        "strength": guidelines.NORWAY_GRADES.get(grade or ""),
        "direction": way,
        "gradeLetter": None,
        "page": None,
        "printedPage": None,
        "section": None,
        "pdfUrl": url,
        "wordingSha256": hashlib.sha256(guidelines.normalise(text or title).encode("utf-8")).hexdigest(),
        "loinc": link_loinc(f"{title} {text}"),
        "scores": [],  # NORRISK 2, not SCORE2: no link to the SCORE2 node
        "consensus": None,
        "dissent": False,
        "checks": {"gate": not why and grade is not None},
        "reviewReasons": reasons,
        "needsReview": bool(reasons),
        "questions": QUESTION_OF_SLUG.get(slug(url) or "", []),
        "codes": codes_of(item),
    }


def build(client: Client) -> dict:
    top = find_guideline(client)
    version = last_change(top)
    records = [record(u) for u in walk(client, top)]
    guideline = {
        "id": GUIDELINE_ID, "key": SLUG, "title": TITLE, "publisher": "Helsedirektoratet (Norway)",
        "version": version, "extracted": True, "country": "NO", "licence": "NLOD 2.0, source: Helsedirektoratet",
        "url": web_url(top) or f"{WEB}/retningslinjer/{SLUG}",
        "quality": {
            "recommendations": len(records),
            "withGrade": sum(1 for r in records if r["grade"]),
            "needsReview": sum(1 for r in records if r["needsReview"]),
            "answersQuestions": sum(1 for r in records if r["questions"]),
            "version": "found" if version else "not found: no recommendation will match the knowledge layer",
        },
    }
    artefact = {
        "schemaVersion": guidelines.SCHEMA_VERSION,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generator": "health_graph.norway",
        "notice": NOTICE,
        "guidelines": [guideline],
        "recommendations": records,
    }
    guidelines.assert_no_text(artefact)
    guidelines.validate(artefact)
    return artefact


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m health_graph.norway")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="read the guideline from HAPI into a local artefact")
    e.add_argument("--out", type=Path,
                   help=f"file to write (default: a new file in Klarbefund's inbox, {guidelines.INBOX})")
    e.add_argument("--dump", type=Path, help="keep HAPI's raw responses in this folder (for checking the reader)")
    a = p.parse_args(argv)
    artefact = build(Client(api_key(), dump=a.dump))
    out = a.out or guidelines.INBOX / f"{int(dt.datetime.now().timestamp() * 1000)}-hdir{guidelines.SUFFIX}"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name("." + out.name + ".tmp")
    tmp.write_text(json.dumps(artefact, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out)
    q = artefact["guidelines"][0]["quality"]
    print(f"{GUIDELINE_ID}: {q['recommendations']} recommendations, {q['withGrade']} with a strength, "
          f"review {q['needsReview']}, answering a question {q['answersQuestions']}, version {q['version']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
