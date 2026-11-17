"""Anamnesis answers both ways between the vault and Klarbefund for Mac (synthetic stores only)."""
from pathlib import Path

import pytest

from health_graph import anamnesis, fhir, knowledge, protocols, store, sync

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = sorted((ROOT / "fixtures" / "fhir").glob("*.json"))


def graph(path):
    conn = store.connect(path)
    store.init_schema(conn)
    for b in BUNDLES:
        store.import_report(conn, fhir.parse_bundle(fhir.load_bundle(b)))
    knowledge.seed(conn)
    return conn, store.single_patient(conn)


def read(conn):
    return sync.responses([dict(r) for r in conn.execute(sync.RESPONSES)])


class FakeHelper:
    """Stands in for the app's MCP helper: reads the 'app' store, records what it is handed."""

    def __init__(self, conn):
        self.conn, self.sent = conn, []

    def responses(self):
        return read(self.conn)

    def submit(self, r):
        self.sent.append((r.questionnaire, r.as_answers()))
        return "ok"


@pytest.fixture()
def stores(tmp_path):
    app, pid = graph(tmp_path / "app.rl")
    vault, _ = graph(tmp_path / "vault.rl")
    yield app, vault, pid
    app.close()
    vault.close()


def test_answers_only_in_the_app_reach_the_vault_under_the_same_id(stores):
    app, vault, pid = stores
    protocols.store_response(app, pid, "phq-2", {"phq2-1": "0", "phq2-2": "1"}, source="claude-code",
                             authored="2026-11-15T20:11:54+00:00")
    protocols.store_response(app, pid, "family-cvd", {"family-cvd-who": "none", "family-lipids": "unknown"},
                             source="claude-code", authored="2026-11-15T20:11:53+00:00")
    anamnesis.store_response(app, pid, {"creatine-protein": {"codes": ["creatine"], "text": "5 g a day",
                                                             "basedOn": ["2160-0"]}},
                             source="claude-code", authored="2026-11-15T20:54:25+00:00")
    todo = sync.plan(read(app), read(vault))
    assert [r.questionnaire for r in todo.to_vault] == ["family-cvd", "phq-2", "klarbefund-anamnesis"]
    assert not todo.to_app and not todo.differ
    lines = sync.store_in_vault(vault, pid, todo.to_vault)
    assert all(line.startswith("to vault") for line in lines)
    assert sorted(r.id for r in read(vault)) == sorted(r.id for r in read(app))
    # the vault scored and derived as the app did, and the answer kept its source and its LOINC link
    phq = vault.execute("MATCH (r:QuestionnaireResponse {protocol: 'phq-2'}) RETURN r.score AS s, r.source AS src").single()
    assert phq["s"] == 1 and phq["src"] == "claude-code"
    assert vault.execute("MATCH (a:Answer {linkId: 'family-cvd'}) RETURN a.derivedFrom AS d").single()["d"] == "family-cvd"
    assert vault.execute("MATCH (:Answer {linkId: 'creatine-protein'})-[:BASED_ON]->(c) RETURN c.code AS c").single()["c"] == "2160-0"
    again = sync.plan(read(app), read(vault))
    assert not again.to_vault and not again.to_app and not again.differ  # a second sync moves nothing


def test_the_vault_hands_its_answers_to_the_app_through_the_helper(stores):
    app, vault, pid = stores
    anamnesis.store_response(vault, pid, {"home-bp": "no", "diet-fat": "rarely"}, authored="2026-11-16T16:25:29+00:00")
    # the app answered diet-fat later; that answer must stay the newest one there
    anamnesis.store_response(app, pid, {"diet-fat": "weekly"}, source="claude-code", authored="2026-11-17T08:00:00+00:00")
    helper = FakeHelper(app)
    todo = sync.plan(helper.responses(), read(vault))
    assert [r.questionnaire for r in todo.to_app] == ["klarbefund-anamnesis"]
    assert [line.split()[0] for line in sync.send_to_app(helper, todo.to_app)] == ["to"]
    assert helper.sent == [("klarbefund-anamnesis", {"home-bp": {"codes": ["no"], "basedOn": [], "findings": [],
                                                                "question": anamnesis.ITEM["home-bp"]["text"]}})]


def test_the_app_restamping_a_response_is_matched_by_content(stores):
    app, vault, pid = stores
    answers = {"exercise-before-sample@2026-09-04": {"codes": ["yes"], "basedOn": ["33762-6"]}}
    anamnesis.store_response(vault, pid, answers, authored="2026-11-16T16:25:29+00:00")
    anamnesis.store_response(app, pid, answers, source="vault", authored="2026-11-16T16:26:43+00:00")
    todo = sync.plan(read(app), read(vault))
    assert not todo.to_vault and not todo.to_app


def test_one_response_edited_on_one_side_is_reported_not_copied(stores):
    app, vault, pid = stores
    at = "2026-11-14T14:09:51+00:00"
    anamnesis.store_response(app, pid, {"liver-imaging": {"codes": [], "text": "short"}}, authored=at)
    anamnesis.store_response(vault, pid, {"liver-imaging": {"codes": [], "text": "short, and more"}}, authored=at)
    todo = sync.plan(read(app), read(vault))
    assert not todo.to_vault and not todo.to_app and len(todo.differ) == 1
