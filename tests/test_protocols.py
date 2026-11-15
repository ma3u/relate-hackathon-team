"""Anamnesis protocols: codes, prefill from the data, scoring, storing with SNOMED codes."""
from pathlib import Path

import pytest

from health_graph import anamnesis, fhir, knowledge, protocols, store

ROOT = Path(__file__).resolve().parents[1]
BUNDLES = sorted((ROOT / "fixtures" / "fhir").glob("*.json"))
TODAY = "2026-11-15"


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


def rows(conn, cypher, **params):
    return [dict(r) for r in conn.execute(cypher, params)]


def test_every_code_is_declared_and_every_protocol_is_well_formed():
    risk_ids = {r["id"] for r in knowledge.HEALTH_RISKS}
    assert len(protocols.PROTOCOL) == len(protocols.PROTOCOLS)
    for p in protocols.PROTOCOLS:
        assert set(p["risks"]) <= risk_ids, p["id"]
        assert p["why"] and p.get("source"), p["id"]
        for code in (p.get("snomed"), p.get("scoreSnomed"), *p.get("bandSnomed", [])):
            assert code is None or code in protocols.SNOMED, (p["id"], code)
        links = [i["linkId"] for i in p["items"]]
        assert len(links) == len(set(links)), p["id"]
        for it in p["items"]:
            assert it.get("snomed") is None or it["snomed"] in protocols.SNOMED, it["linkId"]
            assert it.get("prefill") is None or it["prefill"] in protocols.PREFILL or it["prefill"].startswith("answer:")
            for opt in it["options"]:
                assert opt["snomed"] is None or opt["snomed"] in protocols.SNOMED, (it["linkId"], opt["code"])
            for link in (it.get("enableWhen") or {}):
                assert link in links, (it["linkId"], link)
        if p.get("method") in ("sum", "le8"):
            assert all(o["points"] is not None for it in p["items"] for o in it["options"]), p["id"]
    # A question shared with the data-driven anamnesis keeps its answer codes, so both read one answer.
    for link in ("smoking", "lipid-medication", "family-lipids", "supplements"):
        mine = next(i for p in protocols.PROTOCOLS for i in p["items"] if i["linkId"] == link)
        assert [o["code"] for o in mine["options"]] == [c for c, _, _ in anamnesis.ITEM[link]["options"]], link


def test_scores_follow_the_published_points():
    findrisc = protocols.PROTOCOL["findrisc"]
    full = {"findrisc-age": ["55-64"], "findrisc-bmi": [">30"], "findrisc-waist": ["large"],
            "findrisc-activity": ["no"], "findrisc-vegetables": ["not-daily"], "findrisc-bp-drugs": ["yes"],
            "findrisc-glucose": ["yes"], "findrisc-family": ["close"]}
    s = protocols.score(findrisc, full)
    assert s["value"] == 3 + 3 + 4 + 2 + 1 + 2 + 5 + 5 and s["band"] == "very high" and s["flag"]
    part = protocols.score(findrisc, {"findrisc-glucose": ["yes"]})
    assert (part["value"], part["min"], part["max"], part["complete"]) == (5, 5, 26, False)
    audit = protocols.PROTOCOL["audit-c"]
    assert protocols.score(audit, {"audit-c-1": ["never"]})["value"] == 0  # 2 and 3 skipped after "never"
    three = {"audit-c-1": ["2-3-week"], "audit-c-2": ["1-2"], "audit-c-3": ["never"]}
    assert protocols.score(audit, three, "female")["flag"] and not protocols.score(audit, three, "male")["flag"]
    le8 = protocols.PROTOCOL["le8"]
    s = protocols.score(le8, {"le8-activity": ["150+"], "le8-nicotine": ["current"], "le8-home-smoke": ["yes"],
                              "le8-sleep": ["7-9"], "le8-bmi": ["<25"], "le8-lipids": ["<130"],
                              "le8-lipid-drug": ["yes"], "le8-glucose": ["normal"], "le8-bp": ["<120"],
                              "le8-bp-drug": ["no"]})
    # nicotine stays 0 (no deduction below zero), lipids 100 - 20 for the medicine
    assert s["metrics"] == {"activity": 100, "nicotine": 0, "sleep": 100, "bmi": 100, "lipids": 80,
                            "glucose": 100, "bp": 100}
    assert s["value"] == round(580 / 7) and s["band"] == "high"


def test_family_history_counts_only_when_early():
    later = protocols.family_summary({"family-cvd-who": ["father", "mother"], "family-cvd-father-age": ["65+"],
                                      "family-cvd-mother-age": ["65+"]})
    assert later["band"] == "later in life" and later["snomed"] == "266894000" and not later["flag"]
    early = protocols.family_summary({"family-cvd-who": ["father"], "family-cvd-father-age": ["<55"]})
    assert early["flag"] and early["snomed"] == "439724007" and early["derived"] == {"family-cvd": "yes"}


def test_the_plan_prefills_from_the_data_and_ranks_by_the_findings(db):
    conn, _ = db
    plan = protocols.plan(conn, today=TODAY)
    by_id = {p["id"]: p for p in plan["protocols"]}
    assert list(by_id) == [p["id"] for p in sorted(plan["protocols"], key=lambda p: -p["relevance"])]
    glucose = next(i for i in by_id["findrisc"]["items"] if i["linkId"] == "findrisc-glucose")
    assert glucose["prefilled"]["code"] == "yes" and "HbA1c 5.9" in glucose["prefilled"]["text"]
    le8_glucose = next(i for i in by_id["le8"]["items"] if i["linkId"] == "le8-glucose")
    assert le8_glucose["prefilled"]["code"] == "normal"  # the newest HbA1c, 5.4 %
    assert any("LDL cholesterol" in w for w in by_id["le8"]["forYou"])
    assert by_id["audit-c"]["forYou"] == []  # no liver or triglyceride finding in the fixtures
    assert plan["snomed"]["77176002"]["display"] == "Smoker"


def test_answers_are_stored_with_their_snomed_codes_and_count_for_the_anamnesis(db):
    conn, pid = db
    protocols.store_response(conn, pid, "tobacco", {"smoking": "current", "tobacco-amount": "occasional"},
                             authored="2026-11-15T10:00:00+00:00")
    counts = protocols.store_response(conn, pid, "family-cvd", {
        "family-cvd-who": ["father", "mother"], "family-cvd-father-age": "65+", "family-cvd-mother-age": "65+"},
        authored="2026-11-15T10:01:00+00:00")
    assert counts["band"] == "later in life" and counts["derived"] == 1
    codes = rows(conn, "MATCH (a:Answer)-[:CODED_BY]->(s:SnomedCode) WHERE a.linkId IN ['smoking', 'tobacco-amount'] "
                       "RETURN a.linkId AS l, s.code AS c ORDER BY l")
    assert codes == [{"l": "smoking", "c": "77176002"}, {"l": "tobacco-amount", "c": "230059006"}]
    assert rows(conn, "MATCH (r:QuestionnaireResponse {protocol: 'family-cvd'})-[:CODED_BY]->(s) RETURN s.code AS c") \
        == [{"c": "266894000"}]
    # The data-driven anamnesis now knows the smoking status and the family history.
    plan = anamnesis.plan(conn, today=TODAY)
    assert "smoking_unknown" not in [f["id"] for f in plan["findings"]]
    assert "family-cvd" not in [q["key"] for q in plan["questions"]]
    with pytest.raises(ValueError):
        protocols.store_response(conn, pid, "tobacco", {"smoking": "sometimes"})


def test_seeding_twice_gives_one_category(db):
    conn, _ = db
    first = protocols.seed(conn)
    assert protocols.seed(conn) == first
    assert rows(conn, "MATCH (c:AnamnesisCategory)-[:HAS_PROTOCOL]->(p) RETURN count(p) AS n") == [
        {"n": len(protocols.PROTOCOLS)}]
    assert rows(conn, "MATCH (:ProtocolItem {linkId: 'smoking'})-[r:ANSWER_CODE]->(s) "
                      "WHERE r.option = 'never' RETURN s.code AS c") == [{"c": "266919005"}]


def test_lipid_values_under_a_statin_are_marked(db):
    conn, pid = db
    protocols.store_response(conn, pid, "lipid-therapy", {
        "lipid-medication": "stopped", "lipid-from": {"text": "2026-01"}, "lipid-until": {"text": "2026-06"}},
        authored="2026-11-15T10:00:00+00:00")
    treated = protocols.plan(conn, today=TODAY)["treatedLipids"]
    assert {t["date"] for t in treated} == {"2026-03-12", "2026-06-10"}  # not the September value
    with pytest.raises(ValueError):
        protocols.store_response(conn, pid, "lipid-therapy", {"lipid-from": {"text": "spring"}})


def test_the_plant_based_diet_group_follows_ahs2():
    g = lambda **a: protocols.plant_summary({f"plant-{k}": [v] for k, v in a.items()})
    rare, monthly, weekly = "never", "1-3/month", "1+/week"
    assert g(meat=rare, fish=rare, eggs=rare, dairy="<1/month")["snomed"] == "1255165006"  # vegan
    assert g(meat=rare, fish=rare, eggs=monthly, dairy=weekly)["band"] == "lacto-ovo-vegetarian"
    assert g(meat=rare, fish=rare, eggs=rare, dairy=weekly)["snomed"] == "765022009"
    assert g(meat=rare, fish=rare, eggs=weekly, dairy=rare)["snomed"] == "1255167003"
    assert g(meat="<1/month", fish=weekly)["band"] == "pesco-vegetarian"
    assert g(meat=monthly, fish=monthly)["band"] == "semi-vegetarian"
    assert g(meat=monthly, fish=weekly)["band"] == "non-vegetarian" and g(meat=weekly)["band"] == "non-vegetarian"
    open_ = g(meat=rare)
    assert open_["band"] == "vegetarian" and not open_["complete"] and open_["snomed"] == "765021002"
    no_b12 = g(meat=rare, fish=rare, eggs=rare, dairy=rare, b12="no")
    assert no_b12["flag"] and no_b12["complete"]
    assert not g(meat=rare, fish=rare, eggs=rare, dairy=rare, b12="daily")["flag"]
    assert not g(meat=rare, fish=rare, eggs=rare, dairy=rare)["complete"]  # the B12 question is open
    assert protocols.plant_summary({}) is None


def test_a_vegetarian_answer_opens_the_follow_up_with_the_lab_values(db):
    conn, pid = db
    protocols.store_response(conn, pid, "diet-pattern", {"diet-pattern": "vegan"}, authored="2026-11-15T09:00:00+00:00")
    by_id = {p["id"]: p for p in protocols.plan(conn, today=TODAY)["protocols"]}
    plant = by_id["plant-based"]
    assert plant["forYou"][0].startswith("you said you eat vegan")
    pre = {i["linkId"]: (i["prefilled"] or {}).get("code") for i in plant["items"]}
    assert pre["plant-meat"] == pre["plant-fish"] == pre["plant-eggs"] == pre["plant-dairy"] == "never"
    assert all(i["enabled"] for i in plant["items"] if i["linkId"] in ("plant-b12", "plant-iodine", "plant-calcium"))
    assert plant["score"]["band"] == "vegan" and not plant["score"]["complete"]  # B12 still to answer
    labs = plant["labs"]
    assert [v["id"] for v in labs["values"]] == ["ferritin"]  # the fixtures measure ferritin, not B12
    assert labs["values"][0]["date"] == "2026-09-04" and labs["values"][0]["status"]
    assert any(m.startswith("Vitamin B12") for m in labs["missing"])
    assert any(m.startswith("Holotranscobalamin") for m in labs["missing"])
    # Stored: the response carries the diet group's SNOMED concept; a missing B12 source is a risk factor.
    counts = protocols.store_response(conn, pid, "plant-based", {
        "plant-meat": "never", "plant-fish": "never", "plant-eggs": "never", "plant-dairy": "never",
        "plant-b12": "no"}, authored="2026-11-15T09:05:00+00:00")
    assert counts["band"] == "vegan" and counts["flag"]
    assert rows(conn, "MATCH (r:QuestionnaireResponse {protocol: 'plant-based'})-[:CODED_BY]->(s) RETURN s.code AS c") \
        == [{"c": "1255165006"}]
    assert rows(conn, "MATCH (r:QuestionnaireResponse {protocol: 'plant-based'})-[:RISK_FACTOR_FOR]->(h) "
                      "RETURN h.id AS h") == [{"h": "fitness"}]
    # The vegetarian answer in the graph links to the protocol that follows it up.
    assert rows(conn, "MATCH (:AnamnesisProtocol {id: 'plant-based'})-[:CODED_BY]->(s:SnomedCode {code: '765021002'}) "
                      "RETURN count(s) AS n") == [{"n": 1}]
