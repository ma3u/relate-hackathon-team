"""The doctor's letter's reads (health_graph/letter.py) answer on the synthetic fixtures as the Swift letter expects."""
from pathlib import Path

import pytest

from health_graph import anamnesis, fhir, knowledge, letter, store

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = sorted((ROOT / "fixtures" / "fhir").glob("*.json"))


@pytest.fixture()
def conn(tmp_path):
    c = store.connect(tmp_path / "health.rl")
    store.init_schema(c)
    for b in BUNDLES:
        store.import_report(c, fhir.parse_bundle(fhir.load_bundle(b)))
    knowledge.seed(c)
    yield c
    c.close()


def rows(conn, cypher, **params):
    return [dict(r) for r in conn.execute(cypher, params)]


def test_lab_values_come_with_their_report_and_count_once(conn):
    values = rows(conn, letter.LAB_VALUES)
    assert len(values) == 21
    hba1c = [v for v in values if v["code"] == "4548-4"]
    assert [v["date"] for v in hba1c] == ["2026-03-12", "2026-06-10", "2026-09-04"]
    assert all(v["report"] and v["performer"] and v["sourceLine"] for v in hba1c)


def test_ranges_risks_and_links_read_the_knowledge_layer(conn):
    ranges = rows(conn, letter.RANGES, codes=["2089-1"])
    assert any(r["ucum"] == "mg/dL" and r["source"] for r in ranges)
    risks = {r["id"]: r for r in rows(conn, letter.RISKS)}
    assert "2089-1" in risks["cardiovascular"]["codes"]
    links = rows(conn, letter.RISK_LINKS, risk="cardiovascular")
    assert links and all("cardiovascular" in (l["fromId"], l["toId"]) for l in links)


def test_the_latest_answer_per_question_wins(conn):
    pid = conn.execute("MATCH (p:Patient) RETURN p.id AS id").single()["id"]
    anamnesis.store_response(conn, pid, {"smoking": "current"}, authored="2026-10-01T09:00:00+00:00")
    anamnesis.store_response(conn, pid, {"smoking": {"codes": ["never"], "text": "stopped for good"}},
                             authored="2026-11-15T09:00:00+00:00")
    answers = rows(conn, letter.ANSWERS)
    assert [a["linkId"] for a in answers] == ["smoking"]
    assert answers[0]["labels"] == ["Never"] and answers[0]["text"] == "stopped for good"
    assert rows(conn, letter.PATIENT)[0].keys() == {"birthYear", "sex"}
    assert rows(conn, letter.DEVICE_VALUES) == []
