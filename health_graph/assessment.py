"""Assessments: what Claude concluded from the values and the answers, stored with what it rests on.

The protocols and the data-driven anamnesis store the person's answers and the
scores they give. What a reading of all of it concludes (these lipid values were
measured under a statin; this LDL does not fit the other values of the same day;
the watch and the answer disagree on sleep) was lost when the chat ended. An
assessment keeps it, each finding linked to the values, the risks and the
answers it is about, so the next reading starts from it and the person can check
each claim against the paper.

In the graph:

  (:Patient)-[:HAS_ASSESSMENT]->(:Assessment {id, authored, source, title, summary})
  (:Assessment)-[:HAS_FINDING]->(:Finding {id, order, kind, severity, title, text})
  (:Finding)-[:ABOUT]->(:Observation)         the values it is about (resourceId)
  (:Finding)-[:CONCERNS]->(:HealthRisk)       the risks it bears on
  (:Assessment)-[:BASED_ON]->(:QuestionnaireResponse)   the newest response of each protocol it read

An assessment is never a diagnosis: kinds and wording say what the data shows and
what to ask, and the person confirms it before it is stored.
"""
from __future__ import annotations

import datetime as dt
import hashlib

KINDS = {
    "risk": "what the values and answers mean for a health risk",
    "treated": "values measured under a medicine or a diet that changes them",
    "data-quality": "a value that looks misread, duplicated or implausible: check it on the paper",
    "discrepancy": "the data and an answer disagree",
    "habit": "a habit that moves a risk",
    "ask-doctor": "a question to take to the doctor",
    "test": "a test that would close a gap",
}
SEVERITIES = ("info", "watch", "high")
MAX_FINDINGS, MAX_TITLE, MAX_TEXT, MAX_SUMMARY = 30, 200, 2000, 4000


def validate(assessment: dict, risk_ids: set[str] | None = None) -> dict:
    """The assessment checked and normalised; ValueError names the first problem."""
    if not isinstance(assessment, dict):
        raise ValueError("an assessment is an object with title, summary and findings")
    title = str(assessment.get("title") or "").strip()
    summary = str(assessment.get("summary") or "").strip()
    findings = assessment.get("findings")
    if not title or len(title) > MAX_TITLE:
        raise ValueError(f"title: 1 to {MAX_TITLE} characters")
    if len(summary) > MAX_SUMMARY:
        raise ValueError(f"summary: at most {MAX_SUMMARY} characters")
    if not isinstance(findings, list) or not 1 <= len(findings) <= MAX_FINDINGS:
        raise ValueError(f"findings: a list of 1 to {MAX_FINDINGS}")
    protocols = assessment.get("protocols") or []
    if not isinstance(protocols, list) or not all(isinstance(p, str) for p in protocols):
        raise ValueError("protocols: a list of protocol ids")
    out = []
    for n, f in enumerate(findings, 1):
        if not isinstance(f, dict):
            raise ValueError(f"finding {n}: an object")
        kind, severity = f.get("kind"), f.get("severity") or "info"
        if kind not in KINDS:
            raise ValueError(f"finding {n}: kind {kind!r} not among {list(KINDS)}")
        if severity not in SEVERITIES:
            raise ValueError(f"finding {n}: severity {severity!r} not among {list(SEVERITIES)}")
        ftitle, text = str(f.get("title") or "").strip(), str(f.get("text") or "").strip()
        if not ftitle or len(ftitle) > MAX_TITLE:
            raise ValueError(f"finding {n}: title of 1 to {MAX_TITLE} characters")
        if len(text) > MAX_TEXT:
            raise ValueError(f"finding {n}: text of at most {MAX_TEXT} characters")
        observations, risks = f.get("observations") or [], f.get("risks") or []
        if not all(isinstance(x, str) and x for x in observations):
            raise ValueError(f"finding {n}: observations are Observation resourceIds (strings)")
        if not all(isinstance(x, str) and x for x in risks):
            raise ValueError(f"finding {n}: risks are health risk ids (strings)")
        if risk_ids is not None and (bad := [r for r in risks if r not in risk_ids]):
            raise ValueError(f"finding {n}: unknown risks {bad}; known: {sorted(risk_ids)}")
        out.append({"order": n, "kind": kind, "severity": severity, "title": ftitle, "text": text,
                    "observations": list(dict.fromkeys(observations)), "risks": list(dict.fromkeys(risks))})
    return {"title": title, "summary": summary, "protocols": list(dict.fromkeys(protocols)), "findings": out}


STORE_ASSESSMENT = """
MATCH (p:Patient {id: $patientId})
MERGE (a:Assessment {id: $assessmentId})
SET a.authored = $authored, a.source = $source, a.title = $title, a.summary = $summary,
    a.findings = size($findings)
MERGE (p)-[:HAS_ASSESSMENT]->(a)
WITH a
UNWIND $findings AS f
MERGE (n:Finding {id: $assessmentId + '|' + toString(f.order)})
SET n.order = f.order, n.kind = f.kind, n.severity = f.severity, n.title = f.title, n.text = f.text
MERGE (a)-[:HAS_FINDING]->(n)
RETURN count(n) AS findings
"""

STORE_FINDING_ABOUT = """
UNWIND $findings AS f
MATCH (n:Finding {id: $assessmentId + '|' + toString(f.order)})
UNWIND f.observations AS obsId
MATCH (o:Observation {resourceId: obsId})
MERGE (n)-[:ABOUT]->(o)
RETURN count(*) AS links
"""

STORE_FINDING_RISKS = """
UNWIND $findings AS f
MATCH (n:Finding {id: $assessmentId + '|' + toString(f.order)})
UNWIND f.risks AS riskId
MATCH (h:HealthRisk {id: riskId})
MERGE (n)-[:CONCERNS]->(h)
RETURN count(*) AS links
"""

# The newest stored response of each protocol the assessment read.
STORE_ASSESSMENT_BASED_ON = """
MATCH (a:Assessment {id: $assessmentId})<-[:HAS_ASSESSMENT]-(p:Patient)
UNWIND $protocols AS protocolId
MATCH (p)-[:HAS_RESPONSE]->(r:QuestionnaireResponse {protocol: protocolId})
WITH a, protocolId, r ORDER BY r.authored DESC
WITH a, protocolId, collect(r)[0] AS newest
MERGE (a)-[:BASED_ON]->(newest)
RETURN count(*) AS links
"""

ASSESSMENTS = """
MATCH (:Patient)-[:HAS_ASSESSMENT]->(a:Assessment)-[:HAS_FINDING]->(f:Finding)
OPTIONAL MATCH (f)-[:ABOUT]->(o:Observation)
OPTIONAL MATCH (f)-[:CONCERNS]->(h:HealthRisk)
RETURN a.id AS id, a.authored AS authored, a.title AS title, a.summary AS summary, f.order AS order,
       f.kind AS kind, f.severity AS severity, f.title AS finding, f.text AS text,
       collect(DISTINCT o.resourceId) AS observations, collect(DISTINCT h.id) AS risks
ORDER BY authored DESC, order
"""


def _rows(conn, cypher: str, params: dict | None = None) -> list[dict]:
    return [dict(r) for r in conn.execute(cypher, params or {})]


def store(conn, patient_id: str, assessment: dict, source: str = "claude", authored: str | None = None) -> dict:
    """Stores one assessment; returns the counts, with the observations and risks it could not link."""
    risk_ids = {r["id"] for r in _rows(conn, "MATCH (h:HealthRisk) RETURN h.id AS id")}
    a = validate(assessment, risk_ids or None)
    authored = authored or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    digest = hashlib.sha256(f"{patient_id}|{authored}|{a['title']}".encode()).hexdigest()[:12]
    aid = f"{patient_id}|assessment|{authored}|{digest}"
    found = _rows(conn, STORE_ASSESSMENT, {"patientId": patient_id, "assessmentId": aid, "authored": authored,
                                           "source": source, "title": a["title"], "summary": a["summary"],
                                           "findings": a["findings"]})
    if not found or not found[0]["findings"]:
        raise ValueError(f"no person {patient_id!r} in the graph")
    about = _rows(conn, STORE_FINDING_ABOUT, {"assessmentId": aid, "findings": a["findings"]})
    risks = _rows(conn, STORE_FINDING_RISKS, {"assessmentId": aid, "findings": a["findings"]})
    based = _rows(conn, STORE_ASSESSMENT_BASED_ON, {"assessmentId": aid, "protocols": a["protocols"]})
    asked = sum(len(f["observations"]) for f in a["findings"])
    linked = about[0]["links"] if about else 0
    return {"id": aid, "findings": len(a["findings"]), "observations": linked, "unlinkedObservations": asked - linked,
            "risks": risks[0]["links"] if risks else 0, "basedOn": based[0]["links"] if based else 0}


def assessments(conn) -> list[dict]:
    """Every stored assessment, newest first, with its findings."""
    out: dict[str, dict] = {}
    for r in _rows(conn, ASSESSMENTS):
        a = out.setdefault(r["id"], {"id": r["id"], "authored": r["authored"], "title": r["title"],
                                     "summary": r["summary"], "findings": []})
        a["findings"].append({k: r[k] for k in ("order", "kind", "severity", "text", "observations", "risks")}
                             | {"title": r["finding"]})
    return list(out.values())
