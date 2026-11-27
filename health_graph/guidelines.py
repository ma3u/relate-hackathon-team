"""Guideline recommendations: extract, check and link them to lab values.

One record per recommendation box of a German guideline, from the PDF a person
already has on their Mac. The wording is read from the text layer and checked in
memory, and then dropped: the publishers' imprints require written consent to
store guideline text in electronic systems (see evidence.py). A record keeps the
facts about the box: its number, the grade as printed (⇑⇑ ⇑ ⇔ ⇓ ⇓⇓), the direction
as its own field, the chapter number, the page, the lab values it names (as LOINC
codes) and a SHA-256 of the normalised wording, so a later run can tell whether
the box changed. Klarbefund opens the publisher's PDF at that page to show it.
Checks that use no language model run on every box:

- the wording stands on the stated page (after the same whitespace, hyphen and
  bullet normalisation on both sides),
- the modal verb matches the grade (soll ⇑⇑/⇓⇓, sollte ⇑/⇓, kann ⇔),
- a negation in the main clause matches a downward grade, and its absence an
  upward one; the clause ends at a subordinate clause, a purpose clause, a
  colon that opens a list, and the end of the sentence,
- the short version, where there is one, prints the same wording under the
  same number.

A record that fails a strength or direction check is kept, marked
`needsReview`, and never shown as a recommendation. That is the zero gate: a
"soll" read as "soll nicht" is a safety defect, not a quality problem.

`assert_no_text` refuses to write an artefact that carries any field with
guideline text. The artefact goes to Klarbefund's inbox on this Mac (the
app-group container), where the app loads it into the graph. DEGAM guidelines
are refused unless `--allow-degam` is passed: the DEGAM has asked that its
texts not be processed until it has decided.

Usage:
  python -m health_graph.guidelines extract \
      --manifest <dir>/guidelines-manifest.json --data <dir> [--out <file>]
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import difflib
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = "1.0"

APP_GROUP = "38R8Z4P7S8.red.mabu.meinbefund"
INBOX = Path.home() / "Library" / "Group Containers" / APP_GROUP / "Inbox"
SUFFIX = ".guidelines.json"

NOTICE = (
    "Facts about recommendation boxes (number, grade, page, lab values named), "
    "no guideline text. The wording is in the publisher's PDF at the page given."
)

# Fields a record may carry. Anything else is refused, so no wording slips in.
RECORD_FIELDS = {
    "id", "guidelineId", "number", "type", "basis", "status", "grade", "strength",
    "direction", "gradeLetter", "page", "printedPage", "section", "pdfUrl",
    "wordingSha256", "loinc", "scores", "consensus", "dissent", "checks", "needsReview",
    "reviewReasons",
}

# ── grades ──────────────────────────────────────────────────────────────────

# The NVL legend (Tabelle "Einstufung von Leitlinien-Empfehlungen in
# Empfehlungsgrade"): the letter alone is ambiguous, A stands for both the
# strong positive and the strong negative recommendation. The symbol is not.
GRADES: dict[str, dict[str, str]] = {
    "⇑⇑": {"strength": "soll", "direction": "do", "letter": "A"},
    "⇑": {"strength": "sollte", "direction": "do", "letter": "B"},
    "⇔": {"strength": "kann", "direction": "open", "letter": "0"},
    "⇓": {"strength": "sollte nicht", "direction": "do not", "letter": "B"},
    "⇓⇓": {"strength": "soll nicht", "direction": "do not", "letter": "A"},
}
# The DEGAM prints the letter (A, B, 0) or EK (expert consensus); the letter says how strong,
# the wording says which way: "soll" and "soll nicht" are both A.
LETTERS: dict[str, str] = {"A": "soll", "B": "sollte", "0": "kann"}
ALLOWED_GRADES = [*GRADES, *LETTERS, "EK"]
PUA = "\uf000-\uf8ff"  # a symbol font's private-use glyphs, as pdftotext prints them
ARROW_FOR = {"soll": "⇑⇑", "sollte": "⇑", "kann": "⇔", "sollte nicht": "⇓", "soll nicht": "⇓⇓"}
LEGEND_ROW = re.compile(rf"^\s*([{PUA}]{{1,2}})\s{{2,}}(soll nicht|sollte nicht|sollte|soll|kann)\b")


def symbol_legend(pages: list[str]) -> dict[str, str]:
    """The guideline's own legend for a symbol font: glyphs -> arrow, read from the wording column.

    The letter column is no help: A stands for both "soll" and "soll nicht". The wording column
    ("soll", "sollte nicht", "kann erwogen werden") says which way, so that is what is read.
    """
    legend: dict[str, str] = {}
    for page in pages[:60]:
        for line in page.split("\n"):
            m = LEGEND_ROW.match(line)
            if m:
                legend.setdefault(m.group(1), ARROW_FOR[m.group(2)])
    return legend


def grade_at_end(legend: dict[str, str]) -> re.Pattern:
    symbols = sorted({"⇑⇑", "⇓⇓", "⇑", "⇓", "⇔", *legend}, key=len, reverse=True)
    return re.compile(r"\s{3,}(" + "|".join(re.escape(x) for x in symbols) + r")\s*$")

HEADER = re.compile(
    r"^\s+(?P<number>\d{1,2}(?:\.\d+)?-\d{1,3}[a-z]?)\s*\|\s*(?P<basis>[ek])\s*\|\s*"
    r"(?P<status>[^|]+?)\s*$"
)
LABEL = re.compile(r"^\s*(Empfehlung(?:en)?|Statement(?:s)?)\s*$")
HEADING = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,2}){0,3})\s{2,}(?P<title>\S.*?)\s*$")
FOOTER = re.compile(r"©.*Seite\s+(?P<page>\d+)\s*$")
PAGE_ONLY = re.compile(r"^\s{20,}(?P<page>[1-9]\d{0,2})\s*$")  # the DEGAM prints the bare number (a grade "0" is not one)
BULLET_GLYPHS = "•▪"

# ── text normalisation (for checks only; the stored wording is not reworded) ─


def _join_lines(lines: list[str]) -> str:
    """Lines of a box as one text: soft hyphens joined, list items on their own line."""
    out = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        bullet = line[0] in BULLET_GLYPHS
        if bullet:
            line = "• " + line[1:].strip()
        if not out:
            out = line
        elif bullet:
            out += "\n" + line
        elif re.search(r"[a-zäöüß]-$", out) and re.match(r"[a-zäöüß]", line):
            out = out[:-1] + line  # soft hyphen at a line end: "do-" + "kumentiert"
        else:
            out += " " + line
    return out


def normalise(text: str) -> str:
    """The form both sides of the verbatim check are compared in."""
    text = re.sub(rf"(⇑⇑|⇓⇓|⇑|⇓|⇔|[{PUA}])", " ", text)
    for g in BULLET_GLYPHS + "•":
        text = text.replace(g, " ")
    text = re.sub(r"([a-zäöüß])-\s*\n\s*([a-zäöüß])", r"\1\2", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ── reading the PDF ─────────────────────────────────────────────────────────


def pdf_pages(pdf: Path) -> list[str]:
    """The text layer of each page, in layout mode (keeps the grade column apart)."""
    out = subprocess.run(
        ["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), "-"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


# ── finding the boxes ───────────────────────────────────────────────────────


@dataclasses.dataclass
class Box:
    number: str
    kind: str          # "recommendation" | "statement"
    basis: str         # "evidence" | "consensus"
    status: str        # as printed: "neu 2023", "bestätigt 2023", "modifiziert 2023"
    lines: list[str]
    grade: str | None
    page: int          # 1-based page in the PDF
    printed_page: int | None
    section: str | None
    ran_off_page: bool
    preamble: int = 0  # leading lines shared by all parts a), b), c): checked on the page apart from the part


def split_columns(line: str) -> tuple[str, str]:
    """(text column, what stands right of it): the grade column, a dissent note."""
    m = re.match(r"^(\s*)(.*?)(?:\s{5,}(\S.*?))?\s*$", line)
    lead, left, right = m.group(1), m.group(2), m.group(3) or ""
    if len(lead) >= 40:  # nothing in the text column on this line
        return "", (left + ("     " + right if right else "")).strip()
    return left, right


def text_column(page: str) -> str:
    """A page with the right-hand columns removed: what a box's wording is checked against."""
    return "\n".join(split_columns(line)[0] for line in page.split("\n"))


def find_boxes(pages: list[str], legend: dict[str, str] | None = None) -> list[Box]:
    """The NVL dialect: a header "3-4 | e | neu 2023", the grade as an arrow (or a symbol font) far right."""
    legend = symbol_legend(pages) if legend is None else legend
    grade_re = grade_at_end(legend)
    boxes: list[Box] = []
    label = "recommendation"
    section: str | None = None
    for index, page in enumerate(pages, start=1):
        lines = page.split("\n")
        printed = None
        for line in lines:
            m = FOOTER.search(line)
            if m:
                printed = int(m.group("page"))
        i = 0
        while i < len(lines):
            line = lines[i]
            h = HEADING.match(line)
            if h and not HEADER.match(line):
                section = f"{h.group('num')} {h.group('title')}"
            lab = LABEL.match(line)
            if lab:
                label = "statement" if lab.group(1).startswith("Statement") else "recommendation"
            m = HEADER.match(line)
            if not m:
                i += 1
                continue
            body: list[str] = []
            grade = None
            blanks = 0
            j = i + 1
            ran_off = True
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    blanks += 1
                    if blanks >= 2 and body:
                        ran_off = False
                        break
                    j += 1
                    continue
                if (HEADER.match(nxt) or LABEL.match(nxt) or FOOTER.search(nxt)
                        or not nxt.startswith(" ")):
                    ran_off = False
                    break
                blanks = 0
                g = grade_re.search(nxt)
                symbol = legend.get(g.group(1), g.group(1)) if g else None
                if g:
                    nxt = nxt[: g.start()]
                body.append((nxt, symbol))
                j += 1
            split, shared = _parts(body)
            for suffix, part in split:
                symbols = {sym for _, sym in part if sym}
                boxes.append(Box(
                    number=m.group("number") + suffix,
                    kind=label,
                    basis="evidence" if m.group("basis") == "e" else "consensus",
                    status=m.group("status").strip(),
                    lines=[text for text, _ in part],
                    # two different symbols in one box (or part): "?", and a person decides
                    grade=symbols.pop() if len(symbols) == 1 else ("?" if symbols else None),
                    page=index,
                    printed_page=printed,
                    section=section,
                    ran_off_page=ran_off,
                    preamble=shared if suffix else 0,
                ))
            i = j
    return boxes


DEGAM_HEADER = re.compile(
    r"^\s*(?P<number>\d{1,2}(?:\.\d+)?-\d{1,3}[a-z]?)\s+(?P<kind>Empfehlung|Statement)\s+"
    r"(?P<basis>evidenzbasiert|konsensbasiert)\s+(?P<status>(?:neu|bestätigt|modifiziert|geprüft)\s+\d{4})(?:\s.*)?$"
)
DEGAM_END = re.compile(r"^\s*(Ergebnis Konsensverfahren|Qualität der Evidenz|Rationale\s*$|Hintergrund\s*$)")
CONSENSUS = re.compile(r"Ergebnis Konsensverfahren:\s*(?P<c>[^()]{1,40}?)\s*(?:\(|$)")
DEGAM_GRADES = {"A", "B", "0", "EK", "Statement"}


@dataclasses.dataclass
class DegamBox(Box):
    consensus: str | None = None
    dissent: bool = False


def find_degam_boxes(pages: list[str]) -> list[Box]:
    """The DEGAM dialect: "9.1-2 Empfehlung evidenzbasiert neu 2024", the grade letter in a column
    to the right, parts a), b), c), a dissent note in a third column, the consensus below. A box may
    run over a page end: the page number and the running head are skipped, and the box goes on."""
    flat: list[tuple[int, str]] = []
    printed: dict[int, int] = {}
    for index, page in enumerate(pages, start=1):
        for line in page.split("\n"):
            m = PAGE_ONLY.match(line)
            if m:
                printed[index] = int(m.group("page"))
            flat.append((index, line))
    running_head = re.compile(r"^\s*DEGAM[- ]Leitlinie|^\s*(?:S3-)?Leitlinie\b.*\bDEGAM\b")
    boxes: list[Box] = []
    section: str | None = None
    i = 0
    while i < len(flat):
        index, line = flat[i]
        h = HEADING.match(line)
        if h:
            section = f"{h.group('num')} {h.group('title')}"
        m = DEGAM_HEADER.match(line)
        if not m:
            i += 1
            continue
        body: list[tuple[str, str | None]] = []
        consensus, dissent, crossed, ended = None, False, False, False
        j = i + 1
        while j < len(flat) and j - i < 90:
            at, nxt = flat[j]
            if DEGAM_HEADER.match(nxt):
                ended = True
                break
            if PAGE_ONLY.match(nxt) or running_head.match(nxt):
                j += 1
                continue
            if at != index:
                crossed = True
            if DEGAM_END.match(nxt):
                c = CONSENSUS.search(nxt)
                consensus = c.group("c").strip() if c else None
                ended = True
                break
            left, right = split_columns(nxt)
            grade = None
            for token in re.split(r"\s{3,}", right) if right else []:
                if token in DEGAM_GRADES:
                    grade = token
                elif token.startswith("Dissens"):
                    dissent = True
            if left.strip() or grade:
                body.append((" " + left.strip() if left.strip() else "", grade))
            j += 1
        split, shared = _parts(body)
        for suffix, part in split:
            grades = {g for _, g in part if g}
            grade = grades.pop() if len(grades) == 1 else ("?" if grades else None)
            kind = "statement" if m.group("kind") == "Statement" or grade == "Statement" else "recommendation"
            boxes.append(DegamBox(
                number=m.group("number") + suffix, kind=kind,
                basis="evidence" if m.group("basis") == "evidenzbasiert" else "consensus",
                status=m.group("status").strip(), lines=[t for t, _ in part],
                grade=None if grade == "Statement" else grade, page=index, printed_page=printed.get(index),
                section=section, ran_off_page=not ended, preamble=shared if suffix else 0,
                consensus=consensus, dissent=dissent,
            ))
        i = j
    return boxes


PART = re.compile(r"^\s*([a-h])\)\s*(.*)$")


def _parts(body: list[tuple[str, str | None]]) -> tuple[list[tuple[str, list[tuple[str, str | None]]]], int]:
    """A box with parts a), b), c) is one recommendation per part, each with its own grade.

    Returns the parts and the number of preamble lines each part starts with (0 for none)."""
    first = next((k for k, (text, _) in enumerate(body) if PART.match(text)), None)
    if first is None:
        return [("", body)], 0
    # "Personen ohne … a) soll … b) sollte …": the lines before a) belong to every part.
    preamble = [(t, sym) for t, sym in body[:first] if t.strip()]
    if preamble:
        body = [("", sym) for _, sym in body[:first] if sym] + body[first:]
    parts: list[tuple[str, list[tuple[str, str | None]]]] = []
    for text, symbol in body:
        m = PART.match(text)
        if m:
            parts.append((m.group(1), [(" " + m.group(2), symbol)] if m.group(2) or symbol else []))
        elif parts:
            parts[-1][1].append((text, symbol))
        elif symbol:  # a grade printed beside the box header, before part a)
            parts.append(("", [("", symbol)]))
    if parts and parts[0][0] == "":
        lead = parts.pop(0)[1]
        if parts:
            parts[0][1][:0] = lead
    if preamble:
        parts = [(letter, [(t, None) for t, _ in preamble] + lines) for letter, lines in parts]
    return parts, len(preamble)


# ── checks ──────────────────────────────────────────────────────────────────

MODAL = re.compile(r"\b(soll|sollen|sollte|sollten|kann|können)\b")
MODAL_LETTER = {"soll": "A", "sollen": "A", "sollte": "B", "sollten": "B", "kann": "0", "können": "0"}
NEGATION = re.compile(
    r"\b(nicht(?!-)|kein|keine|keinen|keinem|keiner|keines"
    r"|vermieden|vermeiden|verzichtet|verzichten|unterlassen|unterbleiben|abgeraten|abraten)\b"
)
# Where the clause that carries the action ends. A gender colon (Patient:innen)
# is part of a word, so a colon counts only when no word character follows it.
CLAUSE_END = re.compile(
    r",\s*(?:wenn|falls|sofern|soweit|solange|weil|da|bevor|nachdem|bis|ob|wobei|sodass|so dass)\b"
    r"|,?\s*\bum\b[^.;]*?\bzu\b"
    r"|:(?!\w)"
    r"|[.;](?:\s|$)"
)


RELATIVE = re.compile(r",\s*(?:die|der|das|dem|den|denen|deren|dessen|welche[rsnm]?)\s[^,]*?,")


def without_relative_clauses(text: str) -> str:
    """", die … können (Tabelle 18), soll …": a relative clause describes a noun, it is not the action."""
    return RELATIVE.sub(",", text)


def first_modal(text: str) -> re.Match | None:
    return MODAL.search(without_relative_clauses(text))


def main_clause(wording: str) -> str | None:
    """From the first modal verb (outside relative clauses) to where the action's clause ends."""
    wording = without_relative_clauses(wording)
    m = MODAL.search(wording)
    if not m:
        return None
    rest = wording[m.start():]
    end = CLAUSE_END.search(rest)
    clause = rest[: end.start()] if end else rest
    # "… sollte empfohlen werden, die Grenzen … nicht zu überschreiten": the zu-infinitive
    # after the comma is what is recommended, not the recommending; its negation is content.
    for comma in re.finditer(r",", clause):
        if re.search(r"\bzu\s+\w+\s*$", clause[comma.end():]):
            return clause[: comma.start()]
    return clause


def check_record(wording: str, grade: str | None, kind: str) -> list[str]:
    """Findings that hold a record back (empty = it passes)."""
    return interpret(wording, grade, kind)["findings"]


def interpret(wording: str, grade: str | None, kind: str) -> dict:
    """Strength, direction and the findings that hold a record back.

    An arrow carries both strength and direction, so the wording is checked against it. A letter
    (A, B, 0) carries the strength only: the modal verb is checked against it and the direction is
    read from the main clause. EK (expert consensus) carries neither: both come from the wording.
    """
    if kind == "statement":
        return {"strength": None, "direction": None, "letter": None, "findings": []}
    if grade in LETTERS or grade == "EK":
        return _interpret_letter(wording.replace("\n", " "), grade)
    findings = _check_arrow(wording, grade)
    g = GRADES.get(grade or "", {})
    return {"strength": g.get("strength"), "direction": g.get("direction"), "letter": g.get("letter"),
            "findings": findings}


def _interpret_letter(flat: str, grade: str) -> dict:
    findings: list[str] = []
    m = first_modal(flat)
    if not m:
        return {"strength": None, "direction": None, "letter": None,
                "findings": ["no modal verb (soll, sollte, kann) in the wording"]}
    letter = MODAL_LETTER[m.group(1)]
    if grade in LETTERS and letter != grade:
        findings.append(f"modal verb '{m.group(1)}' does not match grade {grade} ({LETTERS[grade]})")
        letter = grade
    if letter == "0":
        return {"strength": "kann", "direction": "open", "letter": letter, "findings": findings}
    negations = NEGATION.findall(main_clause(flat) or "")
    if len(negations) > 1:
        findings.append("more than one negation in the main clause; direction needs a person")
    direction = "do not" if negations else "do"
    strength = LETTERS[letter] + (" nicht" if negations else "")
    return {"strength": strength, "direction": direction, "letter": letter, "findings": findings}


def _check_arrow(wording: str, grade: str | None) -> list[str]:
    findings: list[str] = []
    flat = wording.replace("\n", " ")
    if grade is None:
        return ["no grade symbol found in the box"]
    if grade not in GRADES:
        return ["two different grade symbols in one box"]
    expected = GRADES[grade]
    m = first_modal(flat)
    if not m:
        findings.append("no modal verb (soll, sollte, kann) in the wording")
    elif MODAL_LETTER[m.group(1)] != expected["letter"]:
        findings.append(
            f"modal verb '{m.group(1)}' does not match grade {grade} ({expected['strength']})"
        )
    clause = main_clause(flat)
    if clause is not None and expected["direction"] != "open":
        negations = NEGATION.findall(clause)
        if len(negations) > 1:
            findings.append("more than one negation in the main clause; direction needs a person")
        elif expected["direction"] == "do not" and not negations:
            findings.append(f"grade {grade} says 'do not' but the main clause has no negation")
        elif expected["direction"] == "do" and negations:
            findings.append(f"grade {grade} says 'do' but the main clause is negated")
    return findings


# ── linking to lab values ───────────────────────────────────────────────────

# A recommendation that names a lab value is linked to that value's LOINC codes.
# This is a lexical link: the guideline mentions the value in this box. It says
# nothing about whether the recommendation applies to a person's result.
MARKERS: list[tuple[str, str, list[str]]] = [
    ("eGFR", r"\beGFR\b|glomeruläre[n]? Filtrationsrate", ["62238-1", "33914-3", "48642-3", "48643-1", "98979-8", "69405-9"]),
    ("Kreatinin", r"(?<!Albumin-)(?<!Albumin )\b(?:Serum-?)?[Kk]reatinin\b(?![- ]?(?:Quotient|Ratio))", ["2160-0", "14682-9", "38483-4"]),
    ("Albuminurie", r"Albumin-?Kreatinin|Albuminurie|\bUACR\b|Albumin im Urin", ["9318-7", "14959-1", "13705-9", "14958-3"]),
    ("HbA1c", r"\bHbA1c\b", ["4548-4", "59261-8", "17856-6"]),
    ("Glukose", r"Plasmaglukose|Nüchternglukose|Blutglukose|Blutzucker|\bGlukose\b(?![- ]?senk)", ["2345-7", "14749-6", "1558-6", "2339-0"]),
    ("Kalium", r"\bKalium", ["2823-3", "6298-4"]),
    ("Natrium", r"\bNatrium", ["2951-2", "2947-0"]),
    ("LDL-Cholesterin", r"\bLDL", ["2089-1", "22748-8", "13457-7", "18262-6"]),
    ("Lipide", r"Lipidstatus|Lipidprofil|Gesamtcholesterin|Triglyzerid", ["2093-3", "14647-2", "2085-9", "2571-8", "14927-8"]),
    ("NT-proBNP", r"NT-proBNP|\bBNP\b", ["33762-6", "30934-4"]),
    ("Blutdruck", r"[Bb]lutdruck", ["8480-6", "8462-4", "85354-9", "55284-4"]),
]


# A recommendation that turns on the 10-year cardiovascular risk (statins, aspirin) is linked to
# the risk score Klarbefund computes for it. Again lexical: the box names that risk.
SCORES: list[tuple[str, str, list[str]]] = [
    ("kardiovaskuläres Risiko",
     r"(?:absolute[sn]?|globale[sn]?|individuelle[sn]?)\s+(?:kardiovaskuläre[sn]?\s+)?Risiko"
     r"|kardiovaskuläre[sn]?\s+Risiko|Risiko für kardiovaskuläre Ereignisse", ["score2"]),
]


def link_scores(wording: str) -> list[dict[str, str]]:
    return [{"id": i, "term": term} for term, pattern, ids in SCORES if re.search(pattern, wording) for i in ids]


def link_loinc(wording: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for term, pattern, codes in MARKERS:
        if re.search(pattern, wording):
            links.extend({"code": c, "term": term} for c in codes)
    return links


# ── short version ───────────────────────────────────────────────────────────


def compare_short(records: list[dict], short_boxes: list[Box]) -> dict[str, int]:
    """Same number, same wording? Marks each record and counts the outcome."""
    by_number = {b.number: _join_lines(b.lines) for b in short_boxes}
    counts = {"matched": 0, "differs": 0, "missing": 0}
    for r in records:
        other = by_number.get(r["number"])
        if other is None:
            r["checks"]["shortVersion"] = "missing"
            counts["missing"] += 1
            continue
        ratio = difflib.SequenceMatcher(None, normalise(r["wording"]), normalise(other)).ratio()
        if ratio >= 0.97:
            r["checks"]["shortVersion"] = "same"
            counts["matched"] += 1
        else:
            r["checks"]["shortVersion"] = f"differs ({ratio:.2f})"
            counts["differs"] += 1
            r["reviewReasons"].append(f"short version prints different wording (similarity {ratio:.2f})")
    return counts


# ── one guideline ───────────────────────────────────────────────────────────


def numbering_gaps(numbers: list[str]) -> list[str]:
    """Numbers missing inside each chapter's run (1..max)."""
    chapters: dict[str, set[int]] = {}
    for n in numbers:
        m = re.match(r"^(\d{1,2}(?:\.\d+)?)-(\d{1,3})", n)
        if m:
            chapters.setdefault(m.group(1), set()).add(int(m.group(2)))
    gaps = []
    for ch, seen in sorted(chapters.items(), key=lambda kv: [int(x) for x in re.split(r"\D", kv[0]) if x]):
        gaps += [f"{ch}-{k}" for k in range(1, max(seen) + 1) if k not in seen]
    return gaps


def extract_guideline(meta: dict, long_pdf: Path, short_pdf: Path | None,
                      pdf_url: str | None = None) -> tuple[dict, list[dict]]:
    pages = pdf_pages(long_pdf)
    norm_pages = [normalise(text_column(p)) for p in pages]
    boxes = all_boxes(pages)
    gid = meta["awmfId"]
    records: list[dict] = []
    seen: set[str] = set()
    for b in boxes:
        wording = _join_lines(b.lines)
        if not wording or b.number in seen:
            continue
        seen.add(b.number)
        reasons: list[str] = []
        near = " ".join(norm_pages[b.page - 1: b.page + 1])  # a box may cross a page end
        pieces = ([_join_lines(b.lines[:b.preamble]), _join_lines(b.lines[b.preamble:])] if b.preamble else [wording])
        verbatim = all(normalise(piece) in near for piece in pieces)
        if not verbatim:
            reasons.append("wording not found on the stated page")
        if b.ran_off_page:
            reasons.append("box runs over the page end")
        kind = b.kind
        if kind == "recommendation" and b.grade is None and not MODAL.search(wording):
            kind = "statement"  # a definition printed in a recommendation box: nothing to grade
        meaning = interpret(wording, b.grade, kind)
        findings = meaning["findings"]
        records.append({
            "id": f"{gid}:{b.number}",
            "guidelineId": gid,
            "number": b.number,
            "type": kind,
            "basis": b.basis,
            "status": b.status,
            "wording": wording,  # in memory only; dropped before the artefact is written
            "grade": b.grade,
            "strength": meaning["strength"],
            "direction": meaning["direction"],
            "gradeLetter": meaning["letter"],
            "page": b.page,
            "printedPage": b.printed_page,
            "section": b.section.split(" ", 1)[0] if b.section else None,
            "pdfUrl": f"{pdf_url}#page={b.page}" if pdf_url else None,
            "wordingSha256": hashlib.sha256(normalise(wording).encode("utf-8")).hexdigest(),
            "loinc": link_loinc(wording),
            "scores": link_scores(wording),
            "consensus": getattr(b, "consensus", None),
            "dissent": getattr(b, "dissent", False),
            "checks": {"verbatim": verbatim, "gate": not findings, "shortVersion": None},
            "reviewReasons": reasons + findings,
        })
    short = compare_short(records, all_boxes(pdf_pages(short_pdf))) if short_pdf else None
    for r in records:
        r["needsReview"] = bool(r["reviewReasons"])
        del r["wording"]
    recs = [r for r in records if r["type"] == "recommendation"]
    quality = {
        "boxes": len(records),
        "recommendations": len(recs),
        "statements": len(records) - len(recs),
        "withGrade": sum(1 for r in recs if r["grade"]),
        "gateFailures": sum(1 for r in records if not r["checks"]["gate"]),
        "needsReview": sum(1 for r in records if r["needsReview"]),
        "numberingGaps": numbering_gaps([r["number"] for r in records]),
        "shortVersion": short,
    }
    guideline = {
        "id": gid,
        "key": meta.get("id"),
        "title": meta["title"],
        "publisher": meta.get("publisher"),
        "guidelineClass": meta.get("guidelineClass"),
        "version": meta.get("version"),
        "adoptedDate": meta.get("adoptedDate"),
        "validUntilDate": meta.get("validUntilDate"),
        "status": meta.get("status"),
        "sourcePage": meta.get("sourcePage"),
        "pdfUrl": pdf_url,
        "pdfSha256": hashlib.sha256(long_pdf.read_bytes()).hexdigest(),
        "pdfPages": len(pages),
        "extracted": True,
        "quality": quality,
    }
    return guideline, records


def all_boxes(pages: list[str]) -> list[Box]:
    """Both dialects; a number found by both is taken once, in page order."""
    seen: set[str] = set()
    out = []
    for b in sorted(find_boxes(pages) + find_degam_boxes(pages), key=lambda b: b.page):
        if b.number not in seen:
            seen.add(b.number)
            out.append(b)
    return out


# ── the artefact ────────────────────────────────────────────────────────────

USER_AGENT = "Klarbefund-guidelines/1.0 (+https://github.com/ma3u/relate-hackathon-team)"


def public_pdf_url(meta: dict, fetch=None) -> str | None:
    """Where the publisher offers the long version.

    leitlinien.de: <topic>/langfassung/<file>. degam.de: the long-version link on the guideline's
    page (one request; its robots.txt allows it). None when it cannot be found.
    """
    name = meta.get("files", {}).get("long", {}).get("pdf")
    page = meta.get("sourcePage") or ""
    if name and page.startswith("https://www.leitlinien.de/themen/"):
        return f"{page.rstrip('/')}/langfassung/{name}"
    if page.startswith("https://www.degam.de/"):
        try:
            html = (fetch or _fetch)(page)
        except OSError:
            return None
        aid = meta.get("awmfId") or ""
        links = [h for h in re.findall(r'href="([^"]+\.pdf)"', html) if "langfassung" in h and aid in h]
        if links:
            return links[0] if links[0].startswith("https://") else "https://www.degam.de/" + links[0].lstrip("/")
    return None


def _fetch(url: str) -> str:
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def assert_no_text(artefact: dict) -> None:
    """Refuses an artefact whose records carry anything but the allowed fact fields."""
    for r in artefact["recommendations"]:
        extra = set(r) - RECORD_FIELDS
        if extra:
            raise ValueError(f"{r.get('id')}: fields not allowed in the artefact: {sorted(extra)}")
        for reason in r["reviewReasons"]:
            if len(reason) > 120:
                raise ValueError(f"{r['id']}: a review reason that long may quote the guideline")


def is_degam(meta: dict) -> bool:
    return "DEGAM" in (meta.get("publisher") or "") or (meta.get("awmfId") or "").startswith("053-")


def build(manifest: dict, data: Path, allow_degam: bool = False, only: set[str] | None = None) -> dict:
    guidelines: list[dict] = []
    records: list[dict] = []
    entries = manifest.get("guidelines", manifest)
    entries = list(entries.values()) if isinstance(entries, dict) else list(entries)
    for meta in entries:
        if only and meta.get("awmfId") not in only and meta.get("id") not in only:
            continue
        base = {k: meta.get(k) for k in ("title", "publisher", "version", "validUntilDate", "status")}
        base["id"], base["key"] = meta.get("awmfId"), meta.get("id")
        if is_degam(meta) and not allow_degam:
            guidelines.append({**base, "extracted": False,
                               "reason": "waiting for the DEGAM's consent to store its texts"})
            continue
        files = meta.get("files", {})
        folder = "degam-pdf" if is_degam(meta) else "nvl-pdf"
        long_pdf = data / folder / files.get("long", {}).get("pdf", "")
        short_name = files.get("short", {}).get("pdf")
        short_pdf = data / folder / short_name if short_name else None
        if not long_pdf.is_file():
            guidelines.append({**base, "extracted": False, "reason": "long version PDF not on disk"})
            continue
        g, recs = extract_guideline(meta, long_pdf, short_pdf if short_pdf and short_pdf.is_file() else None,
                                    public_pdf_url(meta))
        guidelines.append(g)
        records += recs
    return {
        "schemaVersion": SCHEMA_VERSION,
        "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "generator": "health_graph.guidelines",
        "notice": NOTICE,
        "guidelines": guidelines,
        "recommendations": records,
    }


# ── into the graph ──────────────────────────────────────────────────────────
#
# (:Study {kind: 'guideline'})-[:HAS_RECOMMENDATION]->(:GuidelineRecommendation)-[:MENTIONS {term}]->(:LoincCode)
# The Swift library runs the same Cypher (Cypher.swift, generated) and the same checks
# (GuidelineRecommendations.validate in Swift).

STORE_RECOMMENDATIONS = """
UNWIND $recommendations AS r
MATCH (g:Study {kind: 'guideline', register: r.register, version: r.version})
MERGE (e:GuidelineRecommendation {id: r.id})
SET e.guidelineId = r.guidelineId, e.register = r.register, e.number = r.number, e.type = r.type,
    e.basis = r.basis, e.status = r.status, e.grade = r.grade, e.strength = r.strength,
    e.direction = r.direction, e.gradeLetter = r.gradeLetter, e.page = r.page,
    e.printedPage = r.printedPage, e.section = r.section, e.pdfUrl = r.pdfUrl,
    e.wordingSha256 = r.wordingSha256, e.needsReview = r.needsReview,
    e.reviewReasons = r.reviewReasons, e.shortVersion = r.shortVersion,
    e.consensus = r.consensus, e.dissent = r.dissent,
    e.guidelineTitle = g.title, e.guidelineVersion = g.version, e.checkedAt = $checkedAt
MERGE (g)-[:HAS_RECOMMENDATION]->(e)
RETURN count(e) AS recommendations
"""

UNLINK_RECOMMENDATION_MENTIONS = """
UNWIND $ids AS id
MATCH (e:GuidelineRecommendation {id: id})-[x:MENTIONS]->()
DELETE x
RETURN count(*) AS unlinked
"""

STORE_RECOMMENDATION_MENTIONS = """
UNWIND $mentions AS m
MATCH (e:GuidelineRecommendation {id: m.id})
MATCH (c:LoincCode {code: m.code})
MERGE (e)-[x:MENTIONS]->(c)
SET x.term = m.term
RETURN count(x) AS mentions
"""

STORE_RECOMMENDATION_SCORES = """
UNWIND $mentions AS m
MATCH (e:GuidelineRecommendation {id: m.id})
MATCH (s:RiskScore {id: m.score})
MERGE (e)-[x:MENTIONS]->(s)
SET x.term = m.term
RETURN count(x) AS scores
"""

PRUNE_RECOMMENDATIONS = """
UNWIND $guidelines AS gl
MATCH (e:GuidelineRecommendation {guidelineId: gl.id})
WHERE NOT e.id IN gl.ids
DETACH DELETE e
RETURN count(*) AS pruned
"""

GUIDELINE_VERSIONS = """
MATCH (g:Study {kind: 'guideline'})
WHERE g.register IS NOT NULL
RETURN g.register AS register, g.version AS version
"""

ID_RE = re.compile(r"^(?:nvl-\d{3}|\d{3}-\d{3}(?:OL)?):\d{1,2}(?:\.\d+)?-\d{1,3}[a-z]{0,2}$")
LOINC_RE = re.compile(r"^\d{1,7}-\d$")
MAX_TEXT = 120


def register_of(guideline_id: str) -> str:
    """The register number as the knowledge layer writes it (evidence.GUIDELINES)."""
    if guideline_id.startswith("nvl-"):
        return "NVL " + guideline_id[4:]
    return "AWMF " + guideline_id


def validate(artefact: dict) -> tuple[list[dict], list[dict]]:
    """Checks an artefact and returns (recommendation rows, mention rows). ValueError names the problem.

    A mention row names a LOINC code (`code`) or a risk score (`score`).

    The same rules as `GuidelineRecommendations.validate` in Swift: only the fact fields, short strings,
    known grades, well-formed ids and LOINC codes, so no guideline text reaches the graph.
    """
    if artefact.get("schemaVersion") != SCHEMA_VERSION:
        raise ValueError(f"schemaVersion: expected {SCHEMA_VERSION}")
    versions = {g["id"]: g.get("version") for g in artefact.get("guidelines", [])
                if isinstance(g, dict) and g.get("extracted") and g.get("id")}
    recs = artefact.get("recommendations")
    if not isinstance(recs, list) or len(recs) > 5000:
        raise ValueError("recommendations: a list of at most 5000")
    rows, mentions, score_mentions = [], [], []
    for i, r in enumerate(recs, start=1):
        where = f"recommendation {i}"
        if not isinstance(r, dict):
            raise ValueError(f"{where}: an object")
        extra = set(r) - RECORD_FIELDS
        if extra:
            raise ValueError(f"{where}: fields not allowed: {sorted(extra)}")
        rid = r.get("id")
        if not isinstance(rid, str) or not ID_RE.match(rid):
            raise ValueError(f"{where}: id '{rid}' is not <guideline>:<number>")
        gid = r.get("guidelineId")
        if gid not in versions or not rid.startswith(f"{gid}:"):
            raise ValueError(f"{rid}: guideline '{gid}' is not an extracted guideline of this artefact")
        if r.get("grade") not in (*ALLOWED_GRADES, "?", None):
            raise ValueError(f"{rid}: grade '{r.get('grade')}' unknown")
        for key in ("number", "type", "basis", "status", "strength", "direction", "gradeLetter", "section",
                    "consensus"):
            v = r.get(key)
            if v is not None and (not isinstance(v, str) or len(v) > 40):
                raise ValueError(f"{rid}: {key} must be a short string")
        url = r.get("pdfUrl")
        if url is not None and (not isinstance(url, str) or not url.startswith("https://") or len(url) > 300):
            raise ValueError(f"{rid}: pdfUrl must be an https link")
        sha = r.get("wordingSha256")
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError(f"{rid}: wordingSha256 must be a SHA-256")
        for key in ("page", "printedPage"):
            v = r.get(key)
            if v is not None and (not isinstance(v, int) or isinstance(v, bool) or not 0 < v < 10000):
                raise ValueError(f"{rid}: {key} must be a page number")
        reasons = r.get("reviewReasons") or []
        if not isinstance(reasons, list) or len(reasons) > 10 or any(
                not isinstance(x, str) or len(x) > MAX_TEXT for x in reasons):
            raise ValueError(f"{rid}: reviewReasons: at most 10 short reasons")
        links = r.get("loinc") or []
        if not isinstance(links, list) or len(links) > 60:
            raise ValueError(f"{rid}: loinc: a list")
        for link in links:
            if (not isinstance(link, dict) or not LOINC_RE.match(str(link.get("code", "")))
                    or not isinstance(link.get("term"), str) or len(link["term"]) > 40):
                raise ValueError(f"{rid}: loinc entries are {{code, term}}")
            mentions.append({"id": rid, "code": link["code"], "term": link["term"]})
        scores = r.get("scores") or []
        if not isinstance(scores, list) or len(scores) > 10 or any(
                not isinstance(x, dict) or not re.fullmatch(r"[a-z0-9-]{1,30}", str(x.get("id", "")))
                or not isinstance(x.get("term"), str) or len(x["term"]) > 40 for x in scores):
            raise ValueError(f"{rid}: scores entries are {{id, term}}")
        score_mentions.extend({"id": rid, "score": x["id"], "term": x["term"]} for x in scores)
        if not isinstance(r.get("dissent", False), bool):
            raise ValueError(f"{rid}: dissent must be true or false")
        checks = r.get("checks") or {}
        short = checks.get("shortVersion") if isinstance(checks, dict) else None
        rows.append({
            "id": rid, "guidelineId": gid, "register": register_of(gid), "version": versions[gid],
            "number": r.get("number"), "type": r.get("type"), "basis": r.get("basis"),
            "status": r.get("status"), "grade": r.get("grade"), "strength": r.get("strength"),
            "direction": r.get("direction"), "gradeLetter": r.get("gradeLetter"), "page": r.get("page"),
            "printedPage": r.get("printedPage"), "section": r.get("section"), "pdfUrl": url,
            "wordingSha256": sha, "needsReview": bool(r.get("needsReview") or reasons),
            "reviewReasons": reasons, "shortVersion": short if isinstance(short, str) and len(short) <= 40 else None,
            "consensus": r.get("consensus"), "dissent": bool(r.get("dissent", False)),
        })
    return rows, mentions + score_mentions


def store(conn, artefact: dict, checked_at: str | None = None) -> dict:
    """Writes the recommendations of an artefact into the graph; returns the counts.

    A recommendation whose guideline (register and version) is not in the knowledge layer is not
    stored and is counted as `unmatched`: a newer PDF than the knowledge layer knows waits for it.
    """
    rows, mentions = validate(artefact)
    known = {(r["register"], r["version"]) for r in conn.execute(GUIDELINE_VERSIONS)}
    matched = [r for r in rows if (r["register"], r["version"]) in known]
    ids = {r["id"] for r in matched}
    by_guideline: dict[str, list[str]] = {}
    for r in matched:
        by_guideline.setdefault(r["guidelineId"], []).append(r["id"])
    checked_at = checked_at or artefact.get("generatedAt") or dt.datetime.now(dt.timezone.utc).isoformat()
    conn.autocommit = False
    try:
        counts = {"unmatched": len(rows) - len(matched)}
        counts.update(dict(conn.execute(PRUNE_RECOMMENDATIONS, {
            "guidelines": [{"id": g, "ids": i} for g, i in by_guideline.items()]}).single() or {"pruned": 0}))
        counts.update(dict(conn.execute(STORE_RECOMMENDATIONS, {
            "recommendations": matched, "checkedAt": checked_at}).single()))
        conn.execute(UNLINK_RECOMMENDATION_MENTIONS, {"ids": sorted(ids)})
        counts.update(dict(conn.execute(STORE_RECOMMENDATION_MENTIONS, {
            "mentions": [m for m in mentions if m["id"] in ids and "code" in m]}).single()))
        counts.update(dict(conn.execute(STORE_RECOMMENDATION_SCORES, {
            "mentions": [m for m in mentions if m["id"] in ids and "score" in m]}).single()))
        conn.commit()
        return counts
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.autocommit = True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m health_graph.guidelines")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="extract recommendations into a local artefact")
    e.add_argument("--manifest", type=Path, required=True, help="guidelines-manifest.json")
    e.add_argument("--data", type=Path, help="folder with nvl-pdf/ (default: the manifest's folder)")
    e.add_argument("--out", type=Path,
                   help=f"file to write (default: a new file in Klarbefund's inbox, {INBOX})")
    e.add_argument("--only", action="append", help="register id or key, repeatable")
    e.add_argument("--allow-degam", action="store_true",
                   help="only with the DEGAM's written consent")
    ld = sub.add_parser("load", help="store an artefact in a health graph (.rl), for development")
    ld.add_argument("artefact", type=Path)
    ld.add_argument("--db", type=Path, required=True)
    a = p.parse_args(argv)
    if a.cmd == "load":
        from health_graph.store import connect
        conn = connect(a.db)
        print(store(conn, json.loads(a.artefact.read_text(encoding="utf-8"))))
        return 0
    manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    artefact = build(manifest, a.data or a.manifest.parent, a.allow_degam, set(a.only or []) or None)
    assert_no_text(artefact)
    out = a.out or INBOX / f"{int(dt.datetime.now().timestamp() * 1000)}-nvl{SUFFIX}"
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name("." + out.name + ".tmp")
    tmp.write_text(json.dumps(artefact, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out)  # the app never sees half a file
    for g in artefact["guidelines"]:
        if not g.get("extracted"):
            print(f"{g['id']:10} skipped: {g['reason']}")
            continue
        q = g["quality"]
        sv = q["shortVersion"] or {}
        print(f"{g['id']:10} {q['recommendations']:3} recommendations, {q['statements']:2} statements, "
              f"gate failures {q['gateFailures']}, review {q['needsReview']}, gaps {len(q['numberingGaps'])}, "
              f"short version same/differs/missing {sv.get('matched', '-')}/{sv.get('differs', '-')}/{sv.get('missing', '-')}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
