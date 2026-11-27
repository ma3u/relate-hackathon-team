"""Guideline recommendations: boxes found, checks that hold a wrong direction back, no text in the graph.

Every wording below is made up for the test. No guideline text is used or stored here.
"""
import json
from pathlib import Path

import pytest

from health_graph import fhir, guidelines as G, knowledge, store

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = sorted((ROOT / "fixtures" / "fhir").glob("*.json"))

# One page in the layout `pdftotext -layout` prints a guideline in: a label line, a header
# "number | e/k | status", the wording indented by one space, the grade symbol far right.
PAGE = """3.2        Ein erfundenes Kapitel

 Empfehlung

 3-1 | e | neu 2023
 Bei Erwachsenen mit erfundenem Befund soll die eGFR einmal im Jahr be-                         ⇑⇑
 stimmt werden.

Rationale
Fließtext, der nicht zur Empfehlung gehört.

 Empfehlung

 3-2 | k | neu 2023
 Personen mit erfundenem Befund sollte nicht routinemäßig ein Test angeboten werden.          ⇓
 3-3 | k | bestätigt 2023
 a)
 Bei erfundenem Befund soll eine Messung erfolgen.                                              ⇑⇑

 b)
 Ist sie nicht möglich, kann eine zweite Messung erwogen werden.                               ⇔

 Statement

 3-4 | e | neu 2023

 Ein erfundener Befund allein begründet keine Therapie.

                                                                    © Test-Programm 2023  Seite 12
"""


def boxes():
    return {b.number: b for b in G.find_boxes([PAGE])}


def test_boxes_are_found_with_grade_page_and_section():
    b = boxes()
    assert sorted(b) == ["3-1", "3-2", "3-3a", "3-3b", "3-4"]
    assert b["3-1"].grade == "⇑⇑" and b["3-1"].kind == "recommendation" and b["3-1"].basis == "evidence"
    assert b["3-1"].printed_page == 12 and b["3-1"].section.startswith("3.2")
    assert G._join_lines(b["3-1"].lines).endswith("einmal im Jahr bestimmt werden.")  # soft hyphen joined
    assert b["3-2"].grade == "⇓" and b["3-2"].basis == "consensus"
    assert (b["3-3a"].grade, b["3-3b"].grade) == ("⇑⇑", "⇔")  # each part its own grade
    assert b["3-4"].kind == "statement" and b["3-4"].grade is None


def test_the_rationale_is_not_part_of_the_box():
    assert "Fließtext" not in G._join_lines(boxes()["3-1"].lines)


@pytest.mark.parametrize("wording, grade, finding", [
    ("Der Test soll angeboten werden.", "⇑⇑", None),
    ("Der Test soll nicht angeboten werden.", "⇓⇓", None),
    ("Der Test soll nicht angeboten werden.", "⇑⇑", "negated"),          # the reversal the gate is for
    ("Der Test soll angeboten werden.", "⇓⇓", "no negation"),
    ("Der Test sollte angeboten werden.", "⇑⇑", "modal verb"),           # sollte is B, not A
    ("Der Test kann erwogen werden.", "⇔", None),
    # the condition does not describe the action
    ("Der Test kann angeboten werden, wenn ein anderer Test nicht möglich ist.", "⇔", None),
    ("Der Test sollte angeboten werden, wenn ein anderer Test nicht möglich ist.", "⇑", None),
    # the purpose is not the action
    ("Der Test soll erfolgen, um eine Verzögerung nicht zu riskieren.", "⇑⇑", None),
    # what is recommended may itself be a 'not': the recommending is positive
    ("Personen sollte empfohlen werden, eine Grenze nicht zu überschreiten.", "⇑", None),
    # a verb that negates by itself
    ("Kurzwirksame Mittel sollten vermieden werden.", "⇓", None),
    ("Kurzwirksame Mittel sollten vermieden werden.", "⇑", "negated"),
    # a gender colon is part of a word, not the start of a list
    ("Bei Patient:innen sollte der Test nicht wiederholt werden.", "⇓", None),
    # a colon that opens a list ends the clause
    ("Der Test soll anhand dieser Kriterien erfolgen: kein Fieber, keine Schmerzen.", "⇑⇑", None),
    ("Der Test soll nicht ohne Befund und nicht ohne Aufklärung erfolgen.", "⇓⇓", "more than one"),
])
def test_checks(wording, grade, finding):
    found = G.check_record(wording, grade, "recommendation")
    if finding is None:
        assert found == []
    else:
        assert any(finding in f for f in found), found


def test_a_box_without_a_readable_grade_is_held_back():
    assert G.check_record("Der Test soll erfolgen.", None, "recommendation") == ["no grade symbol found in the box"]
    assert G.check_record("Der Test soll erfolgen.", "?", "recommendation") == ["two different grade symbols in one box"]
    assert G.check_record("Ein Befund begründet keine Therapie.", None, "statement") == []


def test_lab_values_named_in_the_wording_become_loinc_links():
    terms = lambda w: {x["term"] for x in G.link_loinc(w)}
    assert terms("Die eGFR und das Kalium sollen bestimmt werden.") == {"eGFR", "Kalium"}
    assert terms("Die Albumin-Kreatinin Ratio im Urin soll bestimmt werden.") == {"Albuminurie"}
    assert terms("Eine glukosesenkende Therapie soll erfolgen.") == set()
    assert terms("Die Nüchternglukose soll bestimmt werden.") == {"Glukose"}
    assert {x["code"] for x in G.link_loinc("die eGFR")} >= {"62238-1", "33914-3"}


def test_numbering_gaps_show_missing_boxes():
    assert G.numbering_gaps(["2-1", "2-3", "3-1", "3-2a", "3-2b"]) == ["2-2"]


# The DEGAM layout: a header with kind, basis and status, the grade letter in a column to the right,
# parts a), b) each with their own letter, a dissent note in a third column, the consensus below.
DEGAM_PAGE = """9.1    Ein erfundenes Kapitel

 9.1-2 Empfehlung evidenzbasiert neu 2024
 a) Bei einem erfundenen Risiko ≥ 20 % in                         Empfehlungsgrad   Dissens: Zwei erfundene
 10 Jahren soll ein Test angeboten werden.                                            Gesellschaften stimmen
                                                                    A                 nicht zu.
 b) Bei einem absoluten Risiko unter 10 % soll der Test nicht
                                                                    A
 angeboten werden.

 9.1-3 Empfehlung konsensbasiert bestätigt 2024                         Empfehlungsgrad
 Vor dem Test sollten erfundene Ursachen bedacht werden.          Empfehlungsgrad
                                                                         EK
 Ergebnis Konsensverfahren: starker Konsens

Rationale
                                                   127
"""

# A symbol font: the legend's wording column says which glyph means which direction.
LEGEND_PAGE = """\uf0dd\uf0dd            soll                                   Starke Positiv-Empfehlung        A
\uf0df\uf0df            soll nicht                             Starke Negativ-Empfehlung        A

 4-1 | k | neu 2024
 Ein erfundener Test soll nicht wiederholt werden.                                   \uf0df\uf0df
"""


def test_the_degam_layout_letter_grades_and_dissent():
    b = {x.number: x for x in G.find_degam_boxes([DEGAM_PAGE])}
    assert sorted(b) == ["9.1-2a", "9.1-2b", "9.1-3"]
    assert (b["9.1-2a"].grade, b["9.1-2b"].grade, b["9.1-3"].grade) == ("A", "A", "EK")
    assert b["9.1-2a"].dissent and not b["9.1-3"].dissent
    assert b["9.1-3"].consensus == "starker Konsens" and b["9.1-2a"].printed_page == 127
    assert b["9.1-3"].status == "bestätigt 2024"  # not the column label beside it
    # the letter says how strong, the wording which way
    a = G.interpret(G._join_lines(b["9.1-2a"].lines), "A", "recommendation")
    bb = G.interpret(G._join_lines(b["9.1-2b"].lines), "A", "recommendation")
    ek = G.interpret(G._join_lines(b["9.1-3"].lines), "EK", "recommendation")
    assert (a["strength"], a["direction"]) == ("soll", "do")
    assert (bb["strength"], bb["direction"]) == ("soll nicht", "do not")
    assert (ek["strength"], ek["direction"], ek["findings"]) == ("sollte", "do", [])
    assert G.interpret("Der Test sollte erfolgen.", "A", "recommendation")["findings"]  # B wording, A letter
    # the dissent note in the right-hand column is not part of the wording
    assert "Gesellschaften" not in G._join_lines(b["9.1-2a"].lines)
    assert G.normalise(G._join_lines(b["9.1-2a"].lines)) in G.normalise(G.text_column(DEGAM_PAGE))


def test_a_symbol_font_is_read_with_the_guidelines_own_legend():
    assert G.symbol_legend([LEGEND_PAGE]) == {"\uf0dd\uf0dd": "⇑⇑", "\uf0df\uf0df": "⇓⇓"}
    box = G.find_boxes([LEGEND_PAGE])[0]
    assert box.grade == "⇓⇓" and G.check_record(G._join_lines(box.lines), box.grade, box.kind) == []


def test_a_cardiovascular_risk_links_to_the_risk_score():
    assert G.link_scores("Bei einem absoluten Risiko für kardiovaskuläre Ereignisse ≥ 20 %") == [
        {"id": "score2", "term": "kardiovaskuläres Risiko"}]
    assert G.link_scores("Die eGFR soll bestimmt werden.") == []


def test_nicht_in_a_compound_and_a_relative_clause_do_not_mislead():
    assert G.check_record("Es sollen nicht-medikamentöse Hilfen angeboten werden.", "⇑⇑", "recommendation") == []
    assert G.check_record("Wirkstoffe, die den Zustand verschlechtern können, sollen geprüft werden.",
                          "⇑⇑", "recommendation") == []


def test_degam_is_refused_without_consent(tmp_path):
    manifest = {"guidelines": [{"id": "degam-x", "awmfId": "053-999", "publisher": "DEGAM", "title": "x",
                                "files": {"long": {"pdf": "x.pdf"}}}]}
    out = G.build(manifest, tmp_path)
    assert out["guidelines"][0]["extracted"] is False and "DEGAM" in out["guidelines"][0]["reason"]
    assert out["recommendations"] == []


# ── no text leaves the extraction ───────────────────────────────────────────


def artefact(**override):
    rec = {
        "id": "nvl-009:3-1", "guidelineId": "nvl-009", "number": "3-1", "type": "recommendation",
        "basis": "evidence", "status": "neu 2023", "grade": "⇑⇑", "strength": "soll", "direction": "do",
        "gradeLetter": "A", "page": 22, "printedPage": 22, "section": "3.2",
        "pdfUrl": "https://www.leitlinien.de/themen/hypertonie/langfassung/x.pdf#page=22",
        "wordingSha256": "0" * 64, "loinc": [{"code": "62238-1", "term": "eGFR"}, {"code": "2823-3", "term": "Kalium"}],
        "checks": {"verbatim": True, "gate": True, "shortVersion": "same"}, "needsReview": False, "reviewReasons": [],
    }
    rec.update(override)
    return {"schemaVersion": G.SCHEMA_VERSION, "generatedAt": "2026-11-27T12:00:00+00:00",
            "guidelines": [{"id": "nvl-009", "version": "1.0", "extracted": True}], "recommendations": [rec]}


def test_an_artefact_with_wording_is_refused():
    with pytest.raises(ValueError, match="wording"):
        G.assert_no_text(artefact(wording="Der Test soll erfolgen."))
    with pytest.raises(ValueError, match="not allowed"):
        G.validate(artefact(wording="Der Test soll erfolgen."))
    with pytest.raises(ValueError, match="reviewReasons"):
        G.validate(artefact(reviewReasons=["x" * 200]))
    with pytest.raises(ValueError, match="grade"):
        G.validate(artefact(grade="Z"))
    with pytest.raises(ValueError, match="id"):
        G.validate(artefact(id="nvl-009 3-1"))
    with pytest.raises(ValueError, match="loinc"):
        G.validate(artefact(loinc=[{"code": "eGFR", "term": "eGFR"}]))
    rows, mentions = G.validate(artefact())
    assert rows[0]["register"] == "NVL 009" and len(mentions) == 2


# ── into the graph ──────────────────────────────────────────────────────────


@pytest.fixture()
def db(tmp_path):
    conn = store.connect(tmp_path / "health.rl")
    store.init_schema(conn)
    for b in BUNDLES:
        store.import_report(conn, fhir.parse_bundle(fhir.load_bundle(b)))
    knowledge.seed(conn)
    yield conn
    conn.close()


def test_recommendations_hang_on_their_guideline_and_name_lab_values(db):
    counts = G.store(db, artefact())
    assert counts["recommendations"] == 1 and counts["unmatched"] == 0
    row = db.execute(
        "MATCH (g:Study)-[:HAS_RECOMMENDATION]->(e:GuidelineRecommendation)-[m:MENTIONS]->(c:LoincCode {code: '62238-1'}) "
        "RETURN g.register AS reg, e.grade AS grade, e.direction AS dir, e.pdfUrl AS url, m.term AS term").single()
    assert (row["reg"], row["grade"], row["dir"], row["term"]) == ("NVL 009", "⇑⇑", "do", "eGFR")
    assert row["url"].endswith("#page=22")
    # nothing on the node could hold guideline text
    keys = db.execute("MATCH (e:GuidelineRecommendation) RETURN keys(e) AS k").single()["k"]
    assert not {"wording", "text", "statement"} & set(keys)


def test_storing_again_replaces_and_prunes(db):
    G.store(db, artefact())
    G.store(db, artefact())
    assert db.execute("MATCH (e:GuidelineRecommendation) RETURN count(e) AS n").single()["n"] == 1
    G.store(db, artefact(id="nvl-009:3-2", number="3-2", loinc=[]))
    ids = [r["id"] for r in db.execute("MATCH (e:GuidelineRecommendation) RETURN e.id AS id")]
    assert ids == ["nvl-009:3-2"]  # 3-1 is no longer in the guideline's artefact
    assert db.execute("MATCH (:GuidelineRecommendation)-[m:MENTIONS]->() RETURN count(m) AS n").single()["n"] == 0


def test_a_letter_grade_and_the_risk_score_are_stored(db):
    a = artefact(id="053-024:9.1-2a", guidelineId="053-024", number="9.1-2a", grade="A", gradeLetter="A",
                 consensus="starker Konsens", dissent=True, loinc=[],
                 scores=[{"id": "score2", "term": "kardiovaskuläres Risiko"}])
    a["guidelines"] = [{"id": "053-024", "version": "2.3", "extracted": True}]
    counts = G.store(db, a)
    assert counts["recommendations"] == 1 and counts["scores"] == 1
    row = db.execute("MATCH (g:Study {register: 'AWMF 053-024'})-[:HAS_RECOMMENDATION]->(e)-[:MENTIONS]->(s:RiskScore) "
                     "RETURN e.grade AS grade, e.dissent AS dissent, s.id AS score").single()
    assert (row["grade"], row["dissent"], row["score"]) == ("A", True, "score2")


def test_a_guideline_version_the_knowledge_layer_does_not_know_is_not_stored(db):
    a = artefact()
    a["guidelines"][0]["version"] = "2.0"
    counts = G.store(db, a)
    assert counts["unmatched"] == 1 and counts["recommendations"] == 0


def test_no_artefact_is_ever_committed():
    tracked = [p for p in ROOT.rglob("*.guidelines.json") if ".build" not in p.parts]
    assert tracked == []
    assert json.dumps(G.NOTICE)  # the notice says what the file holds
