"""The Norwegian guideline reader (norway.py), the clinical questions (evidence.QUESTIONS) and their links.

HAPI is never called: a fake opener serves responses shaped like HAPI's documented content model
(product, chapter, normative unit; links with rel, type and href). The wording is synthetic, not the
directorate's. The real field names are confirmed once against the live API with `--dump`.
"""
import io
import json
import urllib.error

import pytest

from health_graph import evidence, guidelines as G, knowledge, norway as N, store

PAGE = N.WEB + "/retningslinjer/" + N.SLUG


def unit(uid, slug, text, styrke="Sterk", **extra):
    return {"id": uid, "infoType": "anbefaling", "tittel": f"Synthetic {uid}",
            "tekst": f"<p>{text}</p>", "url": f"{PAGE}/kapittel/{slug}",
            "data": {"styrke": styrke}, "sistFagligOppdatert": "2024-12-05T00:00:00",
            "koder": [{"kodeverk": "SNOMED-CT", "kode": "414916001"}, {"kodeverk": "ICPC-2", "kode": "T93"}],
            "links": [{"rel": "barn", "type": "referanse", "href": N.API + "/innhold/referanser/x"}], **extra}


TOP = {"id": "0006-0001-top", "infoType": "retningslinje", "tittel": N.TITLE, "url": PAGE,
       "sistFagligOppdatert": "05.12.2024",
       "links": [{"rel": "barn", "type": "kapittel", "href": N.API + "/innhold/kapitler/k1"}]}
CHAPTER = {"id": "0006-0041-k1", "infoType": "kapittel", "tittel": "Legemidler",
           "links": [{"rel": "barn", "type": "anbefaling", "href": N.API + "/innhold/anbefalinger/a1"},
                     {"rel": "barn", "type": "anbefaling", "href": N.API + "/innhold/anbefalinger/a2"},
                     {"rel": "barn", "type": "anbefaling", "href": N.API + "/innhold/anbefalinger/a3"},
                     {"rel": "forelder", "type": "retningslinje", "href": N.API + "/innhold/retningslinjer/top"}]}
RESPONSES = {
    "/innhold/innhold?infoTyper=retningslinje": [{"id": "other", "tittel": "Something else", "url": N.WEB + "/x"}, TOP],
    "/innhold/kapitler/k1": CHAPTER,
    "/innhold/anbefalinger/a1": unit("0006-0002-a1", "statinbehandling-hos-eldre-75-ar",
                                     "Det kan vurderes å fortsette behandlingen med LDL-mål.", styrke="Svak"),
    "/innhold/anbefalinger/a2": unit("0006-0002-a2", "utredning-av-lipidverdiene-ved-primaer-og-sekundaer"
                                     "forebygging-av-hjerte-og-karsykdom",
                                     "Måling av Lp(a) anbefales ikke rutinemessig."),
    "/innhold/anbefalinger/a3": unit("0006-0002-a3", "ukjent-side", "Pasienten ikke alltid trenger dette."),
}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def fake_opener(calls):
    def opener(req, timeout):
        calls.append(req)
        path = req.full_url[len(N.API):]
        if path not in RESPONSES:
            raise AssertionError(f"unexpected call {path}")
        return FakeResponse(json.dumps(RESPONSES[path]).encode())
    return opener


@pytest.fixture()
def artefact(monkeypatch):
    monkeypatch.setattr(N, "PAUSE", 0)
    calls = []
    a = N.build(N.Client("k" * 32, opener=fake_opener(calls)))
    a["_calls"] = calls
    return a


def by_id(a):
    return {r["id"].split(":")[1]: r for r in a["recommendations"]}


def test_the_reader_walks_the_guideline_and_keeps_facts_only(artefact):
    calls = artefact.pop("_calls")
    assert all(c.get_header("Ocp-apim-subscription-key") == "k" * 32 for c in calls)
    assert not any("referanser" in c.full_url for c in calls)  # references and PICO are not fetched
    g = artefact["guidelines"][0]
    assert (g["id"], g["version"], g["country"]) == ("hdir-hjerte-kar", "2024-12-05", "NO")
    recs = by_id(artefact)
    assert set(recs) == {"0006-0002-a1", "0006-0002-a2", "0006-0002-a3"}
    G.assert_no_text(artefact)
    assert "LDL-mål" not in json.dumps(artefact, ensure_ascii=False)  # no wording in the artefact


def test_strength_direction_and_questions(artefact):
    recs = by_id(artefact)
    weak = recs["0006-0002-a1"]
    assert (weak["grade"], weak["strength"], weak["direction"], weak["needsReview"]) == ("svak", "weak", "do", False)
    assert weak["questions"] == ["q-statin-over-75"]
    assert {x["term"] for x in weak["loinc"]} == {"LDL-kolesterol"}
    against = recs["0006-0002-a2"]
    assert (against["grade"], against["direction"], against["questions"]) == ("sterk", "do not", ["q-lpa-measurement"])
    assert {x["code"] for x in against["loinc"]} == {"10835-7"}
    assert against["codes"] == [{"system": "SNOMED-CT", "code": "414916001"}, {"system": "ICPC-2", "code": "T93"}]
    assert against["pdfUrl"].startswith(N.WEB) and against["scores"] == []  # NORRISK 2 is not SCORE2


def test_a_negation_the_reader_cannot_place_holds_the_record_back(artefact):
    unclear = by_id(artefact)["0006-0002-a3"]
    assert unclear["direction"] is None and unclear["needsReview"] and unclear["questions"] == []
    assert any("negation" in r for r in unclear["reviewReasons"])


@pytest.mark.parametrize("text, expected", [
    ("Det anbefales at personer med høy risiko får statin.", "do"),
    ("Statiner bør ikke startes hos personer over 85 år.", "do not"),
    ("Det frarådes å bruke kosttilskudd.", "do not"),
    ("Pasienter som ikke tåler statin, bør få ezetimib.", None),  # a negation in a relative clause: a person reads it
    ("En oversikt over legemidlene.", None),
])
def test_direction_from_the_first_sentence(text, expected):
    assert N.direction({}, text)[0] == expected


def test_a_direction_field_wins_and_retningslinje_is_not_one():
    assert N.direction({"retning": "Mot"}, "Det anbefales.")[0] == "do not"
    assert N.direction({"retningslinjeId": "for"}, "Statiner bør ikke gis.")[0] == "do not"


def test_dates_and_strength_in_text():
    assert N.iso_date("05.12.2024") == N.iso_date("2024-12-05T10:00") == "2024-12-05"
    assert N.strength({"tekst": "<b>Svak anbefaling</b>"}) == "svak"
    assert N.strength({"tekst": "Sterk anbefaling … svak anbefaling"}) is None  # two: not guessed


def test_the_key_is_required_and_never_world_readable(tmp_path, monkeypatch):
    monkeypatch.delenv(N.KEY_ENV, raising=False)
    monkeypatch.setattr(N, "KEY_FILE", tmp_path / "hapi.key")
    with pytest.raises(SystemExit, match="utvikler.helsedirektoratet.no"):
        N.api_key()
    (tmp_path / "hapi.key").write_text("a" * 32)
    (tmp_path / "hapi.key").chmod(0o644)
    with pytest.raises(SystemExit, match="chmod 600"):
        N.api_key()
    (tmp_path / "hapi.key").chmod(0o600)
    assert N.api_key() == "a" * 32


def test_a_refused_key_stops_with_a_clear_message(monkeypatch):
    def refuse(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Access denied", {}, None)
    monkeypatch.setattr(N, "PAUSE", 0)
    with pytest.raises(SystemExit, match="refused the subscription key"):
        N.Client("k" * 32, opener=refuse).get("/innhold/innhold")
    with pytest.raises(ValueError, match="not a HAPI address"):
        N.Client("k" * 32, opener=refuse).get("https://example.org/x")


# ── questions: German first, another country only for a reason ─────────────

def test_questions_have_reasons_only_where_the_german_answer_is_open():
    rows = {q["id"]: q for q in evidence.question_rows()}
    assert set(rows) == {q["id"] for q in evidence.QUESTIONS}
    assert rows["q-statin-over-75"]["reasons"] == []  # German alone
    assert any(r.startswith("disputed:") and "ESC/EAS" in r for r in rows["q-ldl-target"]["reasons"])
    assert any(r.startswith("newer study") for r in rows["q-statin-muscle"]["reasons"])
    assert any(r.startswith("dissent") for r in rows["q-lpa-measurement"]["reasons"])


def test_every_question_a_record_names_exists():
    known = {q["id"] for q in evidence.QUESTIONS}
    assert {q for qs in G.QUESTION_OF.values() for q in qs} <= known
    assert {q for qs in N.QUESTION_OF_SLUG.values() for q in qs} <= known


def test_every_guideline_states_country_and_licence():
    for g in evidence.GUIDELINES:
        assert g["country"] and g["licenceClass"] in ("open", "quote-with-attribution", "non-commercial", "permission")
    nor = next(g for g in evidence.GUIDELINES if g["id"] == "hdir-hjerte-kar")
    assert (nor["register"], nor["licenceClass"], nor["riskModel"]) == ("HDIR hjerte-kar", "open", "NORRISK 2")
    assert G.register_of(N.GUIDELINE_ID) == nor["register"]


def test_validation_refuses_bad_questions_and_codes(artefact):
    artefact.pop("_calls")
    rec = artefact["recommendations"][0]
    for field, value, match in [("questions", ["statins"], "questions"),
                                ("codes", [{"system": "LOINC", "code": "1-1"}], "codes")]:
        bad = json.loads(json.dumps(artefact))
        bad["recommendations"][0][field] = value
        with pytest.raises(ValueError, match=match):
            G.validate(bad)
    assert rec["id"].startswith("hdir-hjerte-kar:")


@pytest.fixture()
def db(tmp_path):
    conn = store.connect(tmp_path / "health.rl")
    store.init_schema(conn)
    knowledge.seed(conn)
    yield conn
    conn.close()


def test_norwegian_and_german_answers_meet_at_the_question(db, artefact):
    artefact.pop("_calls")
    counts = G.store(db, artefact)
    assert counts["recommendations"] == 3 and counts["unmatched"] == 0 and counts["answers"] == 2
    german = {"schemaVersion": G.SCHEMA_VERSION, "generatedAt": "2026-11-28T12:00:00+00:00",
              "guidelines": [{"id": "053-024", "version": "2.3", "extracted": True}],
              "recommendations": [{"id": "053-024:7-2", "guidelineId": "053-024", "number": "7-2",
                                   "grade": "B", "direction": "do not", "wordingSha256": "0" * 64,
                                   "dissent": True, "questions": G.QUESTION_OF["053-024:7-2"]}]}
    G.store(db, german)
    rows = list(db.execute(
        "MATCH (q:ClinicalQuestion {id: 'q-lpa-measurement'})<-[:ANSWERS]-(e:GuidelineRecommendation)"
        "<-[:HAS_RECOMMENDATION]-(g:Study) "
        "RETURN g.country AS country, g.licenceClass AS licence, e.direction AS dir, size(q.reasons) > 0 AS open "
        "ORDER BY country"))
    assert [(r["country"], r["licence"], r["dir"]) for r in rows] == [("DE", "permission", "do not"),
                                                                      ("NO", "open", "do not")]
    assert all(r["open"] for r in rows)
    codes = db.execute("MATCH (e:GuidelineRecommendation {id: 'hdir-hjerte-kar:0006-0002-a2'}) "
                       "RETURN e.codes AS c").single()["c"]
    assert codes == ["SNOMED-CT|414916001", "ICPC-2|T93"]
