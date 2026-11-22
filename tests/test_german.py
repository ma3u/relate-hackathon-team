"""The German texts (health_graph/german.py) cover every question and answer, and change nothing else."""
import re

from health_graph import anamnesis, german, protocols


def test_every_question_and_answer_has_its_german_text():
    assert german.missing() == []


def test_no_german_text_without_an_english_one():
    """No stale linkId, option code or rule id: each German key names something that exists."""
    a = german.ANAMNESIS
    assert set(a["items"]) == set(anamnesis.ITEM)
    assert set(a["rules"]) == set(anamnesis.RULE)
    assert set(a["groups"]) == set(anamnesis.GROUP)
    for link, de in a["items"].items():
        assert set(de["options"]) == {c for c, _, _ in anamnesis.ITEM[link]["options"]}, link
    ps = german.PROTOCOLS["protocols"]
    assert set(ps) == set(protocols.PROTOCOL)
    for pid, de in ps.items():
        assert set(de["items"]) == {i["linkId"] for i in protocols.PROTOCOL[pid]["items"]}, pid
        for link, di in de["items"].items():
            assert set(di["options"]) == {x["code"] for x in protocols.ITEM[(pid, link)]["options"]}, (pid, link)
    assert set(german.PROTOCOLS["prefill"]) == set(protocols.PREFILL)


def test_summary_bands_cover_the_family_and_plant_summaries():
    bands = german.PROTOCOLS["summaryBands"]
    assert set(protocols.PLANT_GROUPS) <= set(bands)
    assert {"none", "premature", "age unknown", "later in life", "vegetarian", "not vegetarian"} <= set(bands)


def test_german_texts_are_german_and_plain():
    def texts(x):
        if isinstance(x, str):
            yield x
        elif isinstance(x, dict):
            for v in x.values():
                yield from texts(v)
        elif isinstance(x, list):
            for v in x:
                yield from texts(v)

    for t in texts([german.ANAMNESIS, german.PROTOCOLS]):
        assert "\u2014" not in t, t  # no em dash
        assert t == t.strip() and "  " not in t, t
    # A sample of the official wording: AUDIT-C (German AUDIT) and PHQ-2 (PHQ-D).
    audit = german.PROTOCOLS["protocols"]["audit-c"]["items"]
    assert audit["audit-c-1"]["text"] == "Wie oft trinken Sie Alkohol?"
    phq = german.PROTOCOLS["protocols"]["phq-2"]["items"]["phq2-1"]
    assert phq["options"] == {"0": "Überhaupt nicht", "1": "An einzelnen Tagen",
                              "2": "An mehr als der Hälfte der Tage", "3": "Beinahe jeden Tag"}


def test_the_seed_does_not_change():
    """Display texts only: the protocols' seed (and so its version) is the English definition."""
    rows = protocols._protocol_rows()
    blob = repr(rows)
    assert "Überhaupt nicht" not in blob and "Wie oft" not in blob
    assert re.fullmatch(r"[0-9a-f]{16}", protocols.version())
