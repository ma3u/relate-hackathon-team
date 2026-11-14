"""Anamnesis from the person's own data: findings, what the graph already answers, the questions left."""
from pathlib import Path

import pytest

from health_graph import __main__ as cli
from health_graph import anamnesis, fhir, knowledge, store

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = sorted((ROOT / "fixtures" / "fhir").glob("*.json"))
TODAY = "2026-11-15"


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


def test_rules_ask_only_known_questions_about_tracked_risks():
    risk_ids = {r["id"] for r in knowledge.HEALTH_RISKS}
    assert len({i["linkId"] for i in anamnesis.ITEMS}) == len(anamnesis.ITEMS)
    for item in anamnesis.ITEMS:
        assert item["risks"] and set(item["risks"]) <= risk_ids, item["linkId"]
    for rule in anamnesis.RULES:
        assert set(rule["questions"]) <= set(anamnesis.ITEM), rule["id"]
        assert set(rule["risks"]) <= risk_ids, rule["id"]
        assert set(rule.get("groups", [])) <= set(anamnesis.GROUP), rule["id"]


def test_findings_come_from_the_newest_values_and_raise_their_questions(db):
    """Same expectations as the Swift AnamnesisTests: the two finders agree."""
    conn, _, _ = db
    plan = anamnesis.plan(conn, today=TODAY)
    assert [f["id"] for f in plan["findings"]] == ["lipids", "ntprobnp", "smoking_unknown"]
    assert [q["key"] for q in plan["questions"]] == [
        "lipid-medication", "diet-fat", "family-lipids", "family-cvd", "cardiac-symptoms",
        "exercise-before-sample@2026-09-04", "smoking"]
    assert [k["fact"] for k in plan["known"]] == ["weight_series"]
    ldl = plan["findings"][0]["values"][0]
    assert ldl["trigger"] == "high" and ldl["range"]["basis"] == "guideline"
    dated = next(q for q in plan["questions"] if q["linkId"] == "exercise-before-sample")
    assert "2026-09-04" in dated["text"] and dated["basedOn"] == ["33762-6"]


def test_answers_are_stored_skipped_next_time_and_linked(db):
    conn, _, pid = db
    counts = anamnesis.store_response(conn, pid, {
        "smoking": {"codes": ["current"], "text": "a few a week"},
        "cardiac-symptoms": ["breathless", "palpitations"],
        "exercise-before-sample@2026-09-04": {"codes": ["yes"], "basedOn": ["33762-6"], "findings": ["ntprobnp"]},
        "liver-imaging": {"text": "not sure"},
    }, authored="2026-11-15T09:00:00+00:00")
    assert counts == {"answers": 4, "riskFactors": 2, "basedOn": 1}
    plan = anamnesis.plan(conn, today=TODAY)
    assert "smoking_unknown" not in [f["id"] for f in plan["findings"]]
    keys = [q["key"] for q in plan["questions"]]
    assert "cardiac-symptoms" not in keys and "exercise-before-sample@2026-09-04" not in keys
    skipped = {s["key"]: s["reason"] for s in plan["skipped"]}
    assert skipped["cardiac-symptoms"].startswith("answered on 2026-11-15")
    got = rows(conn, "MATCH (a:Answer {linkId: 'exercise-before-sample'})-[:BASED_ON]->(c) "
                     "RETURN a.context AS d, c.code AS c, a.question AS q, a.findings AS f")
    assert got == [{"d": "2026-09-04", "c": "33762-6", "f": ["ntprobnp"],
                    "q": "Did you do hard endurance exercise or HIIT in the 48 hours before the blood "
                         "sample on 2026-09-04?"}]
    # A year later the answers are asked again.
    later = anamnesis.plan(conn, today="2027-12-01")
    assert "smoking" in [q["key"] for q in later["questions"]]


def test_an_old_value_goes_on_the_recheck_list(db):
    conn, _, _ = db
    plan = anamnesis.plan(conn, today="2028-11-15")
    assert [f["id"] for f in plan["findings"]] == ["smoking_unknown"]
    assert {r["name"] for r in plan["rechecks"]} >= {"LDL cholesterol", "NT-proBNP"}


def test_fib4_uses_one_visit():
    row = {"date": "2025-05-10", "age": 60, "ast": 0.6, "astUnit": "ukat/L", "alt": 0.5, "altUnit": "ukat/L",
           "platelets": [["2025-05-12", 240], ["2025-11-20", 180]]}
    got = anamnesis.fib4(row)
    assert got["value"] == 1.64 and got["platelets"] == 240 and got["ast"] == 36.0
    far = {**row, "platelets": [["2025-11-20", 180]]}
    assert anamnesis.fib4(far) is None  # six months apart is not one visit


@pytest.mark.parametrize("answers", [
    {"smoking": "sometimes"},                       # not an option
    {"nonsense": "yes"},                            # not a question
    {"alcohol": ["none", "1-7"]},                   # one answer only
    {"alcohol": {"codes": ["none"], "findings": ["made-up"]}},  # not a finding
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
