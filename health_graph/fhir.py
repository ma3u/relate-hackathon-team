"""Parse a Klarbefund FHIR R4 Bundle into flat rows for the local graph.

Pure functions, no database: easy to test and to port to Swift later
(the same shape `FhirBundle.swift` writes and the EHDS Hub's
`app-observations.ts` reads).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"
NCBI_TAXON = "http://www.ncbi.nlm.nih.gov/taxonomy"
EXT = "https://ehds.mabu.red/fhir/StructureDefinition/epa-ingest-"
DATA_ABSENT = "http://hl7.org/fhir/StructureDefinition/data-absent-reason"
RENDERED = "http://hl7.org/fhir/StructureDefinition/rendered-value"


@dataclass
class ParsedReport:
    patient_id: str
    report_id: str  # bare id, as the Hub stores it in Observation.sourceReport
    report: dict[str, Any]
    document: dict[str, Any] | None
    provenance: dict[str, Any] | None
    observations: list[dict[str, Any]] = field(default_factory=list)


def load_bundle(path: str | Path) -> dict[str, Any]:
    """Read a Bundle JSON; also accepts Klarbefund's golden-fixture wrapper {"bundle": ...}."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    bundle = data.get("bundle", data)
    if bundle.get("resourceType") != "Bundle":
        raise ValueError(f"{path}: not a FHIR Bundle")
    return bundle


def _ext(resource: dict, name: str) -> Any:
    for x in resource.get("extension", []):
        if x.get("url") == EXT + name:
            for k, v in x.items():
                if k.startswith("value"):
                    return v
    return None


def _coding(concept: dict | None, system: str) -> dict | None:
    for c in (concept or {}).get("coding", []):
        if c.get("system") == system and c.get("code"):
            return c
    return None


def _unmapped_reason(code: dict) -> str | None:
    for x in code.get("extension", []):
        if x.get("url") == DATA_ABSENT:
            for r in x.get("_valueCode", {}).get("extension", []):
                if r.get("url") == RENDERED:
                    return r.get("valueString")
            return x.get("valueCode")
    return None


def _report_id(bundle: dict, report: dict) -> str:
    ident = bundle.get("identifier", {}).get("value")
    if ident:
        return ident
    # Stable fallback: same report content -> same id -> re-import replaces it.
    basis = json.dumps([report.get("effectiveDateTime"), report.get("presentedForm"),
                        report.get("performer")], sort_keys=True)
    return "rpt-" + hashlib.sha256(basis.encode()).hexdigest()[:12]


def parse_bundle(bundle: dict, report_id: str | None = None) -> ParsedReport:
    by_type: dict[str, list[dict]] = {}
    for e in bundle.get("entry", []):
        r = e["resource"]
        by_type.setdefault(r["resourceType"], []).append(r)

    patients = by_type.get("Patient", [])
    if len(patients) != 1:
        raise ValueError("expected exactly one Patient in the bundle")
    patient_id = patients[0]["id"]

    dr = (by_type.get("DiagnosticReport") or [{}])[0]
    rid = report_id or _report_id(bundle, dr)
    prefix = f"{patient_id}-{rid}"
    performer = next((p.get("display") for p in dr.get("performer", []) if p.get("display")), None)

    report = {
        "resourceId": prefix,
        "reportId": rid,
        "fhirId": dr.get("id"),
        "status": dr.get("status"),
        "code": (_coding(dr.get("code"), LOINC) or {}).get("code"),
        "title": (dr.get("code") or {}).get("text"),
        "effectiveDate": dr.get("effectiveDateTime"),
        "issued": dr.get("issued"),
        "performer": performer,
    }

    doc = (by_type.get("DocumentReference") or [None])[0]
    document = None
    if doc:
        att = (doc.get("content") or [{}])[0].get("attachment", {})
        document = {
            "resourceId": f"{prefix}-doc",
            "fhirId": doc.get("id"),
            "title": att.get("title") or doc.get("description"),
            "created": att.get("creation"),
        }

    prov = (by_type.get("Provenance") or [None])[0]
    provenance = None
    if prov:
        provenance = {
            "resourceId": f"{prefix}-prov",
            "recorded": prov.get("recorded"),
            "activity": (prov.get("activity") or {}).get("text"),
            "agent": next((a.get("who", {}).get("display") for a in prov.get("agent", [])), None),
        }

    observations = []
    for index, o in enumerate(by_type.get("Observation", []), start=1):
        code = o.get("code") or {}
        loinc = _coding(code, LOINC)
        q = o.get("valueQuantity") or {}
        rng = (o.get("referenceRange") or [{}])[0]
        category = _coding((o.get("category") or [{}])[0],
                           "http://terminology.hl7.org/CodeSystem/observation-category")
        taxon = None
        for comp in o.get("component", []):
            taxon = _coding(comp.get("valueCodeableConcept"), NCBI_TAXON) or taxon
        value = q.get("value")
        unit = q.get("code") or q.get("unit")
        row = {
            # Hub contract (storeReportRows): resourceId = patient-report-index
            "resourceId": f"{prefix}-{index}",
            "fhirId": o.get("id"),
            "code": loinc["code"] if loinc else None,
            "loincDisplay": loinc.get("display") if loinc else None,
            "display": code.get("text") or (loinc or {}).get("display") or "Unknown",
            "valueQuantity": value,
            "comparator": q.get("comparator"),
            "unit": unit,
            "ucum": q.get("system") in (None, UCUM),
            "referenceLow": (rng.get("low") or {}).get("value"),
            "referenceHigh": (rng.get("high") or {}).get("value"),
            "referenceText": rng.get("text"),
            "effectiveDate": o.get("effectiveDateTime"),
            "category": category["code"] if category else "laboratory",
            "status": o.get("status"),
            "sourceKind": _ext(o, "source-kind"),
            "sourceLine": _ext(o, "source-line"),
            "ocrConfidence": _ext(o, "ocr-confidence"),
            "verifiedByPatientAt": _ext(o, "verified-by-patient"),
            "originalReading": _ext(o, "original-reading"),
            "unmappedReason": None if loinc else _unmapped_reason(code),
            "performer": performer,
            "taxonCode": taxon["code"] if taxon else None,
            "taxonDisplay": taxon.get("display") if taxon else None,
        }
        # Same acceptance rules as POST /api/patient/app/record on the Hub.
        row["hubEligible"] = bool(
            row["status"] == "preliminary" and row["code"] and isinstance(value, (int, float))
            and unit and row["ucum"] and row["effectiveDate"]
        )
        observations.append(row)

    return ParsedReport(patient_id, rid, report, document, provenance, collapse_repeats(observations))


def collapse_repeats(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One value printed twice on the same report is one measurement.

    Microbiome reports list a species in an overview table and again in a
    detail section; read line by line, each copy became its own value and was
    counted twice (Nov 12, 2026: 13 extra rows in one report). The first copy
    stays, with `repeatedOnReport` saying how often it was printed. Only numeric
    values are folded: two text results with one label may well differ.
    """
    kept: list[dict[str, Any]] = []
    seen: dict[tuple, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row["valueQuantity"], (int, float)):
            kept.append(row)
            continue
        key = (row["display"], row["code"], row["taxonCode"], row["valueQuantity"],
               row["comparator"], row["unit"], row["effectiveDate"])
        if key in seen:
            first = seen[key]
            first["repeatedOnReport"] = first.get("repeatedOnReport", 1) + 1
            continue
        seen[key] = row
        kept.append(row)
    return kept


# ── Apple Health weekly means (Klarbefund WearableFHIR.swift) ────────────────
# Same contract as the Hub's ui/src/lib/patient/app-wearables.ts.
WEARABLE_SOURCE_REPORT = "apple-health-weekly"
WEARABLE_SOURCE_KIND = "device-weekly-mean"
WEARABLE_METRICS = {  # LOINC -> (UCUM unit, plausible min, max), as Klarbefund's WearableFHIR codes them
    "40443-4": ("/min", 20, 250),        # resting heart rate
    "80404-7": ("ms", 1, 500),           # HRV SDNN
    "41950-7": ("/d", 0, 200000),        # steps per day
    "29463-7": ("kg", 2, 500),           # body weight
    "55411-3": ("min/d", 0, 1440),       # exercise minutes per day
    "94122-9": ("mL/min/kg", 5, 95),     # VO2 max (Apple Watch cardio fitness estimate)
    "9279-1": ("/min", 3, 70),           # respiratory rate
    "59408-5": ("%", 50, 100),           # blood oxygen (SpO2)
    "41981-2": ("kcal/d", 0, 15000),     # active energy per day
    "41982-0": ("%", 1, 75),             # body fat
    "93832-4": ("h/d", 0, 24),           # sleep, all stages
    "93831-6": ("min/d", 0, 1440),       # deep sleep
    "93829-0": ("min/d", 0, 1440),       # REM sleep
    "93830-8": ("min/d", 0, 1440),       # light (Apple: core) sleep
}


def parse_wearables(bundle: dict, patient_id: str) -> tuple[list[dict], list[dict]]:
    """Weekly-mean Observations -> (rows, skipped). The bundle carries no Patient."""
    rows, skipped, seen = [], [], set()
    for index, e in enumerate(bundle.get("entry", []), start=1):
        o = e.get("resource", {})
        if o.get("resourceType") != "Observation":
            continue
        rid = o.get("id") or f"#{index}"

        def refuse(reason: str):
            skipped.append({"id": rid, "reason": reason})

        if o.get("status") != "final":
            refuse("a device value is sent as final"); continue
        loinc = _coding(o.get("code"), LOINC)
        code = loinc["code"] if loinc else None
        if code not in WEARABLE_METRICS:
            refuse("not a device metric Klarbefund sends"); continue
        unit_expected, lo, hi = WEARABLE_METRICS[code]
        q = o.get("valueQuantity") or {}
        value = q.get("value")
        if not isinstance(value, (int, float)) or q.get("system") != UCUM or q.get("code") != unit_expected:
            refuse(f"a number in {unit_expected} (UCUM) is required"); continue
        if not lo <= value <= hi:
            refuse("the value is not plausible"); continue
        period = o.get("effectivePeriod") or {}
        start, end = period.get("start"), period.get("end")
        if not start or not end or end < start:
            refuse("a week (effectivePeriod start and end) is required"); continue
        key = f"{code}-{start[:10]}"
        if key in seen:
            refuse("the same metric and week twice"); continue
        seen.add(key)
        category = _coding((o.get("category") or [{}])[0],
                           "http://terminology.hl7.org/CodeSystem/observation-category")
        rows.append({
            "resourceId": f"{patient_id}-wear-{key}",
            "fhirId": o.get("id"),
            "code": code,
            "loincDisplay": loinc.get("display"),
            "display": (o.get("code") or {}).get("text") or loinc.get("display"),
            "valueQuantity": value,
            "unit": unit_expected,
            "effectiveStart": start,
            "effectiveDate": end,
            "category": category["code"] if category else "vital-signs",
            "status": "final",
            "sourceKind": WEARABLE_SOURCE_KIND,
            "performer": (o.get("device") or {}).get("display"),
            "note": ((o.get("note") or [{}])[0]).get("text"),
            "hubEligible": True,
        })
    return rows, skipped
