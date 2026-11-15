"""Assessments: findings stored with the values, risks and answers they rest on."""
from pathlib import Path

import pytest

from health_graph import assessment, fhir, knowledge, protocols, store

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = sorted((ROOT / "fixtures" / "fhir").glob("*.json"))


@pytest.fixture()
def db(tmp_path):
    conn = store.connect(tmp_path / "health.rl")
    store.init_schema(conn)
    for b in BUNDLES:
        store.import_report(conn, fhir.parse_bundle(fhir.load_bundle(b)))
    knowledge.seed(conn)
    pid = conn.execute("MATCH (p:Patient) RETURN p.id AS id").single()["id"]
    yield conn, pid
    conn.close()


def obs_ids(conn, code):
    return [r["id"] for r in conn.execute(
        "MATCH (o:Observation)-[:CODED_BY]->(:LoincCode {code: $c}) RETURN o.resourceId AS id ORDER BY id", {"c": code})]


def test_validation_refuses_what_the_graph_cannot_hold():
    ok = {"title": "Reading", "findings": [{"kind": "risk", "title": "LDL high"}]}
    assert assessment.validate(ok)["findings"][0]["severity"] == "info"
    for bad, msg in [({"findings": ok["findings"]}, "title"),
                     ({"title": "x", "findings": []}, "findings"),
                     ({"title": "x", "findings": [{"kind": "diagnosis", "title": "y"}]}, "kind"),
                     ({"title": "x", "findings": [{"kind": "risk", "title": "y", "severity": "urgent"}]}, "severity"),
                     ({"title": "x", "findings": [{"kind": "risk", "title": ""}]}, "title"),
                     ({"title": "x", "findings": [{"kind": "risk", "title": "y", "observations": [3]}]}, "observations")]:
        with pytest.raises(ValueError, match=msg):
            assessment.validate(bad)
    with pytest.raises(ValueError, match="unknown risks"):
        assessment.validate({"title": "x", "findings": [{"kind": "risk", "title": "y", "risks": ["cancer"]}]},
                            {"cardiovascular"})


def test_an_assessment_links_its_findings_to_values_risks_and_answers(db):
    conn, pid = db
    protocols.store_response(conn, pid, "tobacco", {"smoking": "current", "tobacco-amount": "occasional"},
                             authored="2026-11-15T10:00:00+00:00")
    ferritin = obs_ids(conn, "2276-4")
    counts = assessment.store(conn, pid, {
        "title": "Anamnesis 2026-11-15", "summary": "Main risk cardiovascular.", "protocols": ["tobacco", "le8"],
        "findings": [
            {"kind": "risk", "severity": "watch", "title": "Smoking, even occasionally", "text": "SCORE2 counts it.",
             "risks": ["cardiovascular"]},
            {"kind": "data-quality", "title": "Check a value", "observations": ferritin[:2] + ["no-such-value"]},
        ]}, authored="2026-11-15T11:00:00+00:00")
    assert counts == {"id": counts["id"], "findings": 2, "observations": 2, "unlinkedObservations": 1, "risks": 1,
                      "basedOn": 1}  # le8 was never answered: only tobacco
    stored = assessment.assessments(conn)
    assert [f["title"] for f in stored[0]["findings"]] == ["Smoking, even occasionally", "Check a value"]
    assert stored[0]["findings"][0]["risks"] == ["cardiovascular"]
    assert sorted(stored[0]["findings"][1]["observations"]) == sorted(ferritin[:2])
    assert conn.execute("MATCH (:Assessment)-[:BASED_ON]->(r:QuestionnaireResponse) RETURN r.protocol AS p"
                        ).single()["p"] == "tobacco"
    with pytest.raises(ValueError, match="unknown risks"):
        assessment.store(conn, pid, {"title": "x", "findings": [{"kind": "risk", "title": "y", "risks": ["cancer"]}]})
