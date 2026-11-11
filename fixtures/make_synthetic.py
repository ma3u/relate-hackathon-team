"""Derive two more SYNTHETIC lab reports from the Klarbefund golden fixture.

All people, labs and values are fictional. The golden bundle comes from
ma3u/MinimumViableHealthDataspacev2 (clients/ios/Tests/SharedTests/Fixtures/
fhir-golden-bundle.json); the two derived reports give the demo a time series.

Run from the repo root:  python3 fixtures/make_synthetic.py
"""
import copy
import json
from pathlib import Path

HERE = Path(__file__).parent / "fhir"
GOLDEN = HERE / "2026-09-04-praxis-muster.json"
SOURCE_KIND = "https://ehds.mabu.red/fhir/StructureDefinition/epa-ingest-source-kind"
OCR_CONF = "https://ehds.mabu.red/fhir/StructureDefinition/epa-ingest-ocr-confidence"
VERIFIED = "https://ehds.mabu.red/fhir/StructureDefinition/epa-ingest-verified-by-patient"
ORIGINAL = "https://ehds.mabu.red/fhir/StructureDefinition/epa-ingest-original-reading"

# report id, date, lab, source kind, {LOINC: new value}
REPORTS = [
    ("rpt-2026-03-12", "2026-03-12", "Labor Beispielstadt", "lab-issued-digital",
     {"2089-1": 162, "4548-4": 5.9, "33762-6": 410, "2276-4": 22, "1988-5": 1.1, "29463-7": 84}),
    ("rpt-2026-06-10", "2026-06-10", "Praxis Dr. Muster", "ocr-transcribed",
     {"2089-1": 150, "4548-4": 5.6, "33762-6": 780, "2276-4": 15, "1988-5": 4.2, "29463-7": 82}),
]


def loinc_of(obs):
    for c in obs.get("code", {}).get("coding", []):
        if c.get("system") == "http://loinc.org":
            return c["code"]
    return None


def derive(golden, report_id, date, lab, kind, values):
    b = copy.deepcopy(golden)
    b["identifier"] = {"system": "urn:klarbefund:report", "value": report_id}
    doc_title = f"laborbefund-{date}.pdf"
    status = "final" if kind == "lab-issued-digital" else "preliminary"
    for e in b["entry"]:
        r = e["resource"]
        t = r["resourceType"]
        if t == "DocumentReference":
            r["description"] = doc_title
            r["content"][0]["attachment"] = {"title": doc_title, "creation": date}
        elif t == "DiagnosticReport":
            r["effectiveDateTime"] = date
            r["status"] = status
            r["performer"] = [{"display": lab}]
            r["presentedForm"] = [{"title": doc_title}]
        elif t == "Provenance":
            if kind == "lab-issued-digital":
                r["activity"]["text"] = "Values read from the lab's digital report"
                r["agent"][0]["who"]["display"] = "klarbefund (digital import)"
        elif t == "Observation":
            r["effectiveDateTime"] = date
            r["status"] = status
            exts = []
            for x in r.get("extension", []):
                if x["url"] == SOURCE_KIND:
                    x = {"url": SOURCE_KIND, "valueCode": kind}
                if x["url"] in (OCR_CONF, VERIFIED, ORIGINAL) and kind == "lab-issued-digital":
                    continue  # no OCR artefacts on a digital report
                exts.append(x)
            r["extension"] = exts
            code = loinc_of(r)
            if code in values and "valueQuantity" in r:
                r["valueQuantity"]["value"] = values[code]
                r["valueQuantity"].pop("comparator", None)
    return b


def main():
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for report_id, date, lab, kind, values in REPORTS:
        slug = lab.lower().replace("dr. ", "").replace(" ", "-")
        out = HERE / f"{date}-{slug}.json"
        out.write_text(json.dumps(derive(golden, report_id, date, lab, kind, values),
                                  ensure_ascii=False, indent=2), encoding="utf-8")
        print("wrote", out)


if __name__ == "__main__":
    main()
