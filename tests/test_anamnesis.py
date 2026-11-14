"""Anamnesis: questions linked to the health risks, answers stored as FHIR-like responses."""
from pathlib import Path

import pytest

from health_graph import __main__ as cli
from health_graph import anamnesis, fhir, knowledge, store

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = sorted((ROOT / "fixtures" / "fhir").glob("*.json"))


@pytest.fixture()
def db(tmp_path):
    path = tmp_path / "health.rl"
    conn = store.connect(path)
    store.init_schema(conn)
    for b in BUNDLES:
        store.import_report(conn, fhir.parse_bundle(fhir.load_bundle(b)))
    knowledge.seed(conn)
    pid = conn.execute("MATCH (p:Patient) RETURN p.id AS id").single()["id"]
    yield conn, path, pid
    conn.close()


def rows(conn, cypher, **params):
    return [dict(r) for r in conn.execute(cypher, params)]


def test_every_question_informs_a_tracked_risk():
    risk_ids = {r["id"] for r in knowledge.HEALTH_RISKS}
    assert len({i["linkId"] for i in anamnesis.ITEMS}) == len(anamnesis.ITEMS)
    for item in anamnesis.ITEMS:
        assert item["risks"] and set(item["risks"]) <= risk_ids, item["linkId"]
        assert 2 <= len(item["options"]) <= 5, item["linkId"]


def test_questionnaire_links_each_item_to_its_risks(db):
    conn, _, _ = db
    anamnesis.seed(conn)
    anamnesis.seed(conn)  # idempotent
    got = rows(conn, "MATCH (:Questionnaire)-[:HAS_ITEM]->(i:QuestionnaireItem) RETURN count(i) AS n")
    assert got[0]["n"] == len(anamnesis.ITEMS)
    links = rows(conn, "MATCH (i:QuestionnaireItem {linkId: 'alcohol'})-[:INFORMS]->(h) RETURN h.id AS id")
    assert {r["id"] for r in links} == {"liver", "cardiovascular", "bone"}


def test_answers_are_stored_with_risk_factors_and_sources(db):
    conn, _, pid = db
    counts = anamnesis.store_response(conn, pid, {
        "smoking": {"codes": ["current"], "text": "a few a week"},
        "alcohol": "1-7",
        "cardiac-symptoms": ["breathless", "palpitations"],
        "blood-pressure": {"codes": ["no"], "basedOn": ["4548-4"]},
        "liver-imaging": {"text": "not sure"},
    }, authored="2026-11-14T10:00:00+00:00")
    assert counts == {"answers": 5, "riskFactors": 2, "basedOn": 1}
    factors = rows(conn, "MATCH (a:Answer)-[:RISK_FACTOR_FOR]->(h) RETURN a.linkId AS q, h.id AS risk")
    assert {(r["q"], r["risk"]) for r in factors} >= {("smoking", "cardiovascular"), ("cardiac-symptoms", "fitness")}
    assert not [r for r in factors if r["q"] == "alcohol"]
    latest = anamnesis.latest_answers(conn, pid)
    assert latest["liver-imaging"]["codes"] == [] and latest["liver-imaging"]["text"] == "not sure"
    assert latest["cardiac-symptoms"]["labels"][0].startswith("Short of breath")


def test_a_later_response_keeps_the_earlier_one_as_history(db):
    conn, _, pid = db
    anamnesis.store_response(conn, pid, {"smoking": "current"}, authored="2026-01-01T00:00:00+00:00")
    anamnesis.store_response(conn, pid, {"smoking": "former"}, authored="2026-11-14T00:00:00+00:00")
    n = rows(conn, "MATCH (:Patient)-[:HAS_RESPONSE]->(r:QuestionnaireResponse) RETURN count(r) AS n")[0]["n"]
    assert n == 2
    assert anamnesis.latest_answers(conn, pid)["smoking"]["codes"] == ["former"]


@pytest.mark.parametrize("answers", [
    {"smoking": "sometimes"},                       # not an option
    {"nonsense": "yes"},                            # not a question
    {"alcohol": ["none", "1-7"]},                   # one answer only
])
def test_a_wrong_answer_never_reaches_the_graph(db, answers):
    conn, _, pid = db
    with pytest.raises(ValueError):
        anamnesis.store_response(conn, pid, answers)
    assert rows(conn, "MATCH (a:Answer) RETURN count(a) AS n")[0]["n"] == 0


def test_scores_take_smoking_from_the_anamnesis(db, capsys):
    conn, path, pid = db
    conn.execute("MATCH (p:Patient) SET p.birthYear = 1970, p.gender = 'male'")
    anamnesis.store_response(conn, pid, {"smoking": "current"})
    conn.close()
    assert cli.main(["scores", "--db", str(path)]) == 0
    assert "smoking: yes (from the anamnesis)" in capsys.readouterr().out
    assert cli.main(["scores", "--db", str(path), "--smoker", "no"]) == 0  # the switch still wins
    assert "from the anamnesis" not in capsys.readouterr().out
