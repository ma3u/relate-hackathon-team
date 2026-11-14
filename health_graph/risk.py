"""Risk scores and value checks from the graph, shared by the dashboard and the
`scores` command (which stores the results in the graph with their inputs).

Values are read once each (copies are skipped), converted to one unit per
measure where the conversion is exact, and never guessed otherwise.
"""
from __future__ import annotations

import datetime as dt

from . import scores

TODAY = dt.date.today()

# Lab markers: title, LOINC codes (same analyte, any unit), display unit.
CHOL = ["22748-8", "13457-7", "18262-6", "2089-1"]
MARKERS = [
    ("LDL cholesterol", CHOL, "mmol/L"),
    ("HDL cholesterol", ["14646-4", "2085-9"], "mmol/L"),
    ("Total cholesterol", ["14647-2", "2093-3"], "mmol/L"),
    ("Triglycerides", ["14927-8", "2571-8"], "mmol/L"),
    ("ApoB", ["1884-6"], "mg/dL"),
    ("Lp(a)", ["10835-7"], "mg/dL"),
    ("HbA1c", ["4548-4"], "%"),
    ("Glucose", ["2345-7", "1558-6"], "mg/dL"),
    ("hs-CRP", ["30522-7"], "mg/L"),
    ("Ferritin", ["2276-4"], "µg/L"),
    ("TSH", ["3016-3"], "mIU/L"),
    ("Creatinine", ["2160-0"], "mg/dL"),
    ("ALT", ["1742-6"], "U/L"),
    ("AST", ["1920-8"], "U/L"),
    ("NT-proBNP", ["33762-6"], "ng/L"),
    ("Non-HDL cholesterol", ["70204-3", "43396-1"], "mmol/L"),
    ("eGFR (lab)", ["62238-1", "98979-8", "33914-3", "48642-3"], "mL/min/{1.73_m2}"),
    ("Vitamin D", ["62292-8", "68438-1", "1989-3"], "ng/mL"),
    ("GGT", ["2324-2"], "U/L"),
    ("Platelets", ["777-3", "26515-7"], "10*9/L"),
    ("Systolic BP", ["8480-6"], "mmHg"),
    ("Diastolic BP", ["8462-4"], "mmHg"),
    ("BMI", ["39156-5"], "kg/m2"),
    ("Body weight", ["29463-7"], "kg"),
    ("Waist", ["8280-0"], "cm"),
]
MARKER = {title: (codes, unit) for title, codes, unit in MARKERS}

# mg/dL per mmol/L, by analyte (LOINC)
MOLAR = {**{c: 38.67 for c in CHOL + ["14646-4", "2085-9", "14647-2", "2093-3", "70204-3", "43396-1"]},
         "14927-8": 88.57, "2571-8": 88.57, "2345-7": 18.016, "1558-6": 18.016}
# Units that are the same quantity, written differently.
SAME = {"ug/ml": "mg/l", "ng/ml": "ug/l", "m[iu]/l": "miu/l", "u[iu]/ml": "miu/l", "uiu/ml": "miu/l",
        "pg/ml": "ng/l", "mm[hg]": "mmhg", "iu/l": "u/l", "[iu]/l": "u/l"}


def norm_unit(unit: str) -> str:
    u = (unit or "").replace(" ", "").lower().replace("µ", "u").replace("μ", "u")
    return SAME.get(u, u)


def convert(code: str, value: float, unit: str, target: str) -> float | None:
    """`value` in `target`, or None for a unit pair we do not know (never guessed)."""
    u, t = norm_unit(unit), norm_unit(target)
    if u == t:
        return value
    if (u, t) == ("g/l", "mg/dl"):
        return value * 100
    if (u, t) == ("ukat/l", "u/l"):
        return value * 60
    if code in ("62292-8", "68438-1", "1989-3") and (u, t) == ("nmol/l", "ng/ml"):  # 25-OH vitamin D
        return value / 2.496
    if code in ("62292-8", "68438-1", "1989-3") and (u, t) == ("ng/ml", "nmol/l"):
        return value * 2.496
    if code in MOLAR and (u, t) == ("mg/dl", "mmol/l"):
        return value / MOLAR[code]
    if code in MOLAR and (u, t) == ("mmol/l", "mg/dl"):
        return value * MOLAR[code]
    return None


def series(conn, codes, convert=None):
    """Points for any of `codes`, oldest first, copies counted once (see the tuple below)."""
    rows = conn.execute(
        """
        MATCH (o:Observation)-[:CODED_BY]->(lc:LoincCode)
        WHERE lc.code IN $codes AND o.duplicateOf IS NULL AND o.valueQuantity IS NOT NULL
        OPTIONAL MATCH (dr:DiagnosticReport)-[:HAS_RESULT]->(o)
        RETURN lc.code AS code, left(o.effectiveDate, 10) AS date, o.valueQuantity AS value,
               o.unit AS unit, o.sourceKind AS source, coalesce(dr.performer, o.performer) AS lab,
               o.referenceLow AS low, o.referenceHigh AS high, o.resourceId AS rid
        ORDER BY date
        """, {"codes": codes})
    out = []
    for r in rows:
        v = convert(r) if convert else r["value"]
        if v is not None and r["date"]:
            # The printed range, in the same unit as the converted value.
            f = float(v) / r["value"] if r["value"] else 1.0
            low = r["low"] * f if r["low"] is not None else None
            high = r["high"] * f if r["high"] is not None else None
            # (date, value, source, lab, printed low, printed high, resourceId, LOINC)
            out.append((r["date"], float(v), r["source"] or "", r["lab"] or "", low, high, r["rid"], r["code"]))
    return out


def marker_series(conn, title):
    codes, unit = MARKER[title]
    return series(conn, codes, lambda r: convert(r["code"], r["value"], r["unit"], unit))


def latest(points):
    return points[-1] if points else None


def years_between(a: str, b: dt.date) -> float:
    d = dt.date.fromisoformat(a[:10])
    return (b - d).days / 365.25


# ── scores ───────────────────────────────────────────────────────────────────
def compute_scores(conn, age, sex, smoker, region):
    out = []
    need = ("year of birth and sex (Klarbefund build 16 or later: More, Profile; then More, Export to my Mac, "
            "Send year of birth and sex)")

    creat = latest(series(conn, ["2160-0"], lambda r: scores.creatinine_mg_dl(r["value"], r["unit"])))
    if creat and age and sex:
        e = scores.egfr_ckd_epi_2021(creat[1], age, sex)
        out.append(scores.Score("eGFR (CKD-EPI 2021)", e, "mL/min/1.73 m²", scores.egfr_stage(e),
                                "Inker et al., NEJM 2021; KDIGO 2012 categories",
                                {"creatinine": f"{creat[1]:.2f} mg/dL ({creat[0]})", "age": str(age), "sex": sex},
                                note="albuminuria not measured; the KDIGO light assumes A1",
                                light=scores.egfr_light(e), id="egfr", observations=[creat[6]],
                                risk="kidney", date=creat[0]))
    else:
        out.append(scores.Score("eGFR (CKD-EPI 2021)", None, "", None, "Inker et al., NEJM 2021",
                                note="needs creatinine and " + need, risk="kidney"))

    # One visit: AST and ALT of the same day and the platelet count nearest it, within 14
    # days, with the age then. Mixing the newest of each from different months (as this did
    # until Nov 15, 2026) can move FIB-4 across a cut-off.
    ast = alt = plt = None
    alt_by_day = {p[0]: p for p in marker_series(conn, "ALT")}
    platelets = series(conn, ["777-3", "26515-7"])
    for a in reversed(marker_series(conn, "AST")):
        near = [p for p in platelets
                if abs((dt.date.fromisoformat(p[0]) - dt.date.fromisoformat(a[0])).days) <= 14]
        if a[0] in alt_by_day and near:
            ast, alt = a, alt_by_day[a[0]]
            plt = min(near, key=lambda p: abs((dt.date.fromisoformat(p[0]) - dt.date.fromisoformat(a[0])).days))
            break
    if ast and alt and plt and age:
        age_then = age - (TODAY.year - int(ast[0][:4]))
        f = scores.fib4(age_then, ast[1], alt[1], plt[1])
        out.append(scores.Score("FIB-4 (liver fibrosis)", f, "", scores.fib4_band(f, age_then),
                                "Sterling et al., Hepatology 2006; EASL 2021 cut-offs",
                                {"AST": f"{ast[1]:.0f} U/L ({ast[0]})", "ALT": f"{alt[1]:.0f} U/L ({alt[0]})",
                                 "platelets": f"{plt[1]:.0f} ×10⁹/L ({plt[0]})", "age": str(age_then)},
                                light=scores.fib4_light(scores.fib4_band(f, age_then)), id="fib4",
                                observations=[ast[6], alt[6], plt[6]], risk="liver",
                                date=min(ast[0], alt[0], plt[0])))
    else:
        out.append(scores.Score("FIB-4 (liver fibrosis)", None, "", None, "Sterling et al., Hepatology 2006",
                                note="needs AST, ALT, platelets and " + need, risk="liver"))

    tc = latest(marker_series(conn, "Total cholesterol"))
    hdl = latest(marker_series(conn, "HDL cholesterol"))
    sbp = latest(series(conn, ["8480-6"]))
    if tc and hdl and sbp and age and sex and 40 <= age <= 69:
        r = scores.score2(age, sex, smoker, sbp[1], tc[1], hdl[1], region)
        stale = max(years_between(tc[0], TODAY), years_between(hdl[0], TODAY))
        out.append(scores.Score("SCORE2 (10-year cardiovascular risk)", r, "%", scores.score2_band(r, age),
                                f"SCORE2 working group, Eur Heart J 2021; ESC 2021 categories; {region}-risk region (Germany)",
                                {"systolic BP": f"{sbp[1]:.0f} mmHg ({sbp[0]})",
                                 "total cholesterol": f"{tc[1]:.2f} mmol/L ({tc[0]})",
                                 "HDL": f"{hdl[1]:.2f} mmol/L ({hdl[0]})",
                                 "smoking": "yes" if smoker else "no", "age": str(age), "sex": sex},
                                note=f"cholesterol is {stale:.1f} years old" if stale > 1 else None,
                                light=scores.score2_light(scores.score2_band(r, age)), id="score2",
                                observations=[tc[6], hdl[6], sbp[6]], risk="cardiovascular",
                                date=min(tc[0], hdl[0], sbp[0])))
        risk_band = scores.score2_band(r, age)
    else:
        why = "SCORE2 covers ages 40 to 69" if age and not 40 <= age <= 69 else \
            "needs systolic BP, total and HDL cholesterol and " + need
        out.append(scores.Score("SCORE2 (10-year cardiovascular risk)", None, "%", None,
                                "SCORE2 working group, Eur Heart J 2021", note=why, risk="cardiovascular"))
        risk_band = None

    tg =latest(marker_series(conn, "Triglycerides"))
    fpg = latest(series(conn, ["1558-6"]))
    if tg and fpg:
        t = scores.tyg(tg[1] * 88.57, fpg[1])
        out.append(scores.Score("TyG index (insulin resistance)", t, "", None,
                                "Simental-Mendía et al., Metab Syndr Relat Disord 2008",
                                {"triglycerides": f"{tg[1]:.2f} mmol/L ({tg[0]})",
                                 "fasting glucose": f"{fpg[1]:.0f} mg/dL ({fpg[0]})"},
                                note="no universal cut-off; around 8.5 to 8.8 is used in several cohorts",
                                id="tyg", observations=[tg[6], fpg[6]], risk="diabetes",
                                date=min(tg[0], fpg[0])))
    if tc and hdl:
        goal = scores.non_hdl_goal(risk_band)
        light, band = scores.non_hdl_light(tc[1] - hdl[1], goal)
        out.append(scores.Score("Non-HDL cholesterol", tc[1] - hdl[1], "mmol/L", band,
                                "ESC/EAS 2019 dyslipidaemia guideline (goal by SCORE2 risk category)",
                                {"total cholesterol": f"{tc[1]:.2f} ({tc[0]})", "HDL": f"{hdl[1]:.2f} ({hdl[0]})"},
                                light=light, risk="cardiovascular", date=min(tc[0], hdl[0])))
    out += lipids_beyond_ldl(conn, risk_band)
    lpa = latest(marker_series(conn, "Lp(a)"))
    if lpa:
        light, band = scores.lpa_light(lpa[1])
        out.append(scores.Score("Lp(a)", lpa[1], "mg/dL", band, "EAS consensus statement, Eur Heart J 2022",
                                {"Lp(a)": f"{lpa[1]:g} mg/dL ({lpa[0]})"},
                                note="largely inherited; one measurement in life is usually enough", light=light,
                                risk="cardiovascular", date=lpa[0]))
    a1c = latest(marker_series(conn, "HbA1c"))
    if a1c:
        light, band = scores.hba1c_light(a1c[1])
        out.append(scores.Score("HbA1c", a1c[1], "%", band, "ADA Standards of Care 2024",
                                {"HbA1c": f"{a1c[1]:g} % ({a1c[0]})"}, light=light, risk="diabetes", date=a1c[0]))
    bmi = latest(series(conn, ["39156-5"]))
    if bmi:
        light, band = scores.bmi_light(bmi[1])
        out.append(scores.Score("BMI", bmi[1], "kg/m²", band, "WHO classification",
                                {"BMI": f"{bmi[1]:.1f} ({bmi[0]})"}, light=light, date=bmi[0]))
    dbp = latest(series(conn, ["8462-4"]))
    if sbp:
        light, band = scores.bp_light(sbp[1], dbp[1] if dbp else None)
        out.append(scores.Score("Blood pressure", sbp[1], f"/ {dbp[1]:.0f} mmHg" if dbp else "mmHg", band,
                                "ESC 2024 guideline on elevated blood pressure and hypertension",
                                {"systolic": f"{sbp[1]:.0f} mmHg ({sbp[0]})",
                                 **({"diastolic": f"{dbp[1]:.0f} mmHg ({dbp[0]})"} if dbp else {})},
                                note="office measurement", light=light, risk="cardiovascular", date=sbp[0]))
    return out




def same_day(*serieses):
    """The newest date on which every series has a value, with those points; None if there is none."""
    by_date = [{p[0]: p for p in s} for s in serieses]
    common = set(by_date[0]).intersection(*by_date[1:])
    if not common:
        return None
    d = max(common)
    return d, [b[d] for b in by_date]


def lipids_beyond_ldl(conn, risk_band: str | None) -> list[scores.Score]:
    """LDL against its goal, and what the newer markers add: ApoB, the TG/HDL ratio, the atherogenic
    index of plasma and remnant cholesterol. Ratios only from values of one day."""
    out = []
    ldl_s, hdl_s = marker_series(conn, "LDL cholesterol"), marker_series(conn, "HDL cholesterol")
    tg_s, tc_s = marker_series(conn, "Triglycerides"), marker_series(conn, "Total cholesterol")
    category = f"goal for {'moderate' if risk_band in (None, 'low to moderate') else risk_band} risk"
    if ldl := latest(ldl_s):
        goal = scores.ldl_goal(risk_band)
        light, band = scores.goal_light(ldl[1], goal, "mmol/L", "ESC/EAS")
        out.append(scores.Score("LDL cholesterol", ldl[1], "mmol/L", band,
                                f"ESC/EAS 2019 dyslipidaemia guideline and 2025 focused update ({category})",
                                {"LDL": f"{ldl[1]:.2f} mmol/L ({ldl[0]})"},
                                note="causal for atherosclerosis (EAS consensus 2017); the goal depends on the "
                                     "overall risk, so it falls when SCORE2 rises",
                                light=light, risk="cardiovascular", date=ldl[0], observations=[ldl[6]]))
    if apob := latest(marker_series(conn, "ApoB")):
        goal = scores.apob_goal(risk_band)
        light, band = scores.goal_light(apob[1], goal, "mg/dL", "ESC/EAS")
        out.append(scores.Score("ApoB", apob[1], "mg/dL", band,
                                f"ESC/EAS 2019 dyslipidaemia guideline ({category}); Sniderman et al. 2019",
                                {"ApoB": f"{apob[1]:g} mg/dL ({apob[0]})"},
                                note="counts the atherogenic particles; the better single measure when "
                                     "triglycerides are high", light=light, risk="cardiovascular",
                                date=apob[0], observations=[apob[6]]))
    if day := same_day(tg_s, hdl_s):
        d, (tg, hdl) = day
        ratio = scores.tg_hdl_ratio(tg[1], hdl[1])
        light, band = scores.tg_hdl_light(ratio)
        inputs = {"triglycerides": f"{tg[1]:.2f} mmol/L", "HDL": f"{hdl[1]:.2f} mmol/L", "date": d}
        out.append(scores.Score("Triglyceride/HDL ratio", ratio, "(mmol/L units)", band,
                                "McLaughlin et al., Ann Intern Med 2003", inputs,
                                note="a sign of insulin resistance, not a diagnosis; cut-offs differ by sex and "
                                     "group", light=light, risk="diabetes", date=d, observations=[tg[6], hdl[6]]))
        value = scores.aip(tg[1], hdl[1])
        out.append(scores.Score("Atherogenic index of plasma", value, "", scores.aip_band(value),
                                "Dobiášová and Frohlich 2001; meta-analysis Assempoor et al., Cardiovasc Diabetol 2025",
                                inputs, note="associated with coronary disease in observational studies; no "
                                             "guideline cut-off", risk="cardiovascular", date=d,
                                observations=[tg[6], hdl[6]]))
    if day := same_day(tc_s, ldl_s, hdl_s):
        d, (tc, ldl, hdl) = day
        value = scores.remnant_cholesterol(tc[1], ldl[1], hdl[1])
        light, band = scores.remnant_light(value)
        out.append(scores.Score("Remnant cholesterol", value, "mmol/L", band,
                                "EAS/EFLM 2016 (Nordestgaard et al.); Balling et al., Clin Chem 2025",
                                {"total": f"{tc[1]:.2f}", "LDL": f"{ldl[1]:.2f}", "HDL": f"{hdl[1]:.2f} mmol/L",
                                 "date": d},
                                note="where the lab calculates LDL with the Friedewald formula this is just "
                                     "triglycerides / 2.2", light=light, risk="cardiovascular", date=d,
                                observations=[tc[6], ldl[6], hdl[6]]))
    return out


# ── values against the guideline range and the optimal band ─────────────────
def load_ranges(conn) -> dict[str, list[dict]]:
    """ReferenceRange nodes by LOINC code (seeded by health_graph/knowledge.py)."""
    out: dict[str, list[dict]] = {}
    for r in conn.execute(
            "MATCH (rr:ReferenceRange)-[:APPLIES_TO]->(lc:LoincCode) RETURN lc.code AS code, rr {.*} AS rr"):
        out.setdefault(r["code"], []).append(dict(r["rr"]))
    return out


def range_for(ranges: dict[str, list[dict]], code: str, unit: str, sex: str | None) -> dict | None:
    """The range for this code in this unit (or one the value converts to exactly), for this sex."""
    candidates = ranges.get(code, [])
    for want_sex in ([sex] if sex else []) + ["any"]:
        for rr in candidates:
            if rr["sex"] == want_sex and convert(code, 1.0, unit, rr["ucum"]) is not None:
                return rr
    return None


def lab_light(ranges, point, unit: str, sex: str | None):
    """(light, label, detail) for the latest value of a measure.

    With a reference range: green inside the optimal band (or inside the
    guideline range when the source names no optimal band), amber inside the
    guideline range but outside the optimal band, red outside the guideline
    range. Without one: the range the laboratory printed, green inside and red
    outside. None when there is neither.
    """
    date, value, _, _, low, high, _, code = point
    rr = range_for(ranges, code, unit, sex)
    if rr:
        v = convert(code, value, unit, rr["ucum"])

        def inside(lo, hi):
            return (lo is None or v >= lo) and (hi is None or v < hi)

        guideline = (rr.get("guidelineLow"), rr.get("guidelineHigh"))
        optimal = (rr.get("optimalLow"), rr.get("optimalHigh"))
        has_opt = optimal != (None, None)
        detail = (f"guideline {_span(*guideline)} {rr['ucum']}"
                  + (f" · optimal {_span(*optimal)}" if has_opt else "")
                  + f" · {rr['sourceLabel']}")
        if guideline != (None, None) and not inside(*guideline):
            return scores.RED, "outside the guideline range", detail
        if has_opt and not inside(*optimal):
            return scores.AMBER, "within the guideline range, not optimal", detail
        return scores.GREEN, "optimal" if has_opt else "within the guideline range", detail
    if low is None and high is None:
        return None
    if (low is not None and value < low) or (high is not None and value > high):
        return scores.RED, "outside the lab's range", f"printed range {_span(low, high)} {unit}"
    return scores.GREEN, "within the lab's range", f"printed range {_span(low, high)} {unit}"


def _span(lo, hi) -> str:
    f = lambda x: f"{x:g}"
    if lo is not None and hi is not None:
        return f"{f(lo)}–{f(hi)}"
    if hi is not None:
        return f"< {f(hi)}"
    return f"≥ {f(lo)}" if lo is not None else "–"
