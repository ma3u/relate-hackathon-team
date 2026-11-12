"""Private health dashboard from the Relate graph: wearables (Apple Watch, Whoop),
lab trends and published risk scores.

Reads the graph read-only and writes one self-contained HTML file (inline SVG,
no network requests, no external scripts). The output holds real health data,
so it belongs inside the encrypted vault, never in this repository:

    .venv/bin/python scripts/dashboard.py ~/RelateHealth/health.rl \
        --out ~/RelateHealth/demo/dashboard.html [--smoker no] [--region moderate]

Risk scores are estimates from published formulas (health_graph/scores.py),
each with its inputs, their dates and the source. They are not a diagnosis.
"""
from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from health_graph import scores, store  # noqa: E402

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
    ("Body weight", ["29463-7"], "kg"),
    ("Waist", ["8280-0"], "cm"),
]
MARKER = {title: (codes, unit) for title, codes, unit in MARKERS}

# mg/dL per mmol/L, by analyte (LOINC)
MOLAR = {**{c: 38.67 for c in CHOL + ["14646-4", "2085-9", "14647-2", "2093-3"]},
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
    if code in MOLAR and (u, t) == ("mg/dl", "mmol/l"):
        return value / MOLAR[code]
    if code in MOLAR and (u, t) == ("mmol/l", "mg/dl"):
        return value * MOLAR[code]
    return None


WEARABLES = [  # Apple Health weekly means: (LOINC, title, unit)
    ("40443-4", "Resting heart rate", "/min"),
    ("80404-7", "HRV (SDNN)", "ms"),
    ("94122-9", "VO₂ max", "mL/min/kg"),
    ("93832-4", "Sleep", "h/d"),
    ("41950-7", "Steps", "/d"),
    ("9279-1", "Respiratory rate", "/min"),
]

WHOOP = [  # Whoop daily cycles, imported by health_graph/whoop.py
    ("whoop-recovery", "Recovery", "%"),
    ("whoop-strain", "Day strain", ""),
    ("whoop-hrv", "HRV (RMSSD)", "ms"),
    ("whoop-rhr", "Resting heart rate", "/min"),
    ("whoop-sleep-performance", "Sleep performance", "%"),
]


def series(conn, codes, convert=None):
    """[(date, value, source, lab)] for any of `codes`, copies counted once."""
    rows = conn.execute(
        """
        MATCH (o:Observation)-[:CODED_BY]->(lc:LoincCode)
        WHERE lc.code IN $codes AND o.duplicateOf IS NULL AND o.valueQuantity IS NOT NULL
        OPTIONAL MATCH (dr:DiagnosticReport)-[:HAS_RESULT]->(o)
        RETURN lc.code AS code, left(o.effectiveDate, 10) AS date, o.valueQuantity AS value,
               o.unit AS unit, o.sourceKind AS source, coalesce(dr.performer, o.performer) AS lab
        ORDER BY date
        """, {"codes": codes})
    out = []
    for r in rows:
        v = convert(r) if convert else r["value"]
        if v is not None and r["date"]:
            out.append((r["date"], float(v), r["source"] or "", r["lab"] or ""))
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
    need = "year of birth and sex (Klarbefund: Export to my Mac, Send year of birth and sex)"

    creat = latest(series(conn, ["2160-0"], lambda r: scores.creatinine_mg_dl(r["value"], r["unit"])))
    if creat and age and sex:
        e = scores.egfr_ckd_epi_2021(creat[1], age, sex)
        out.append(scores.Score("eGFR (CKD-EPI 2021)", e, "mL/min/1.73 m²", scores.egfr_stage(e),
                                "Inker et al., NEJM 2021; KDIGO 2012 categories",
                                {"creatinine": f"{creat[1]:.2f} mg/dL ({creat[0]})", "age": str(age), "sex": sex}))
    else:
        out.append(scores.Score("eGFR (CKD-EPI 2021)", None, "", None, "Inker et al., NEJM 2021",
                                note="needs creatinine and " + need))

    ast = latest(marker_series(conn, "AST"))
    alt = latest(marker_series(conn, "ALT"))
    plt = latest(series(conn, ["777-3", "26515-7"]))
    if ast and alt and plt and age:
        f = scores.fib4(age, ast[1], alt[1], plt[1])
        out.append(scores.Score("FIB-4 (liver fibrosis)", f, "", scores.fib4_band(f, age),
                                "Sterling et al., Hepatology 2006; EASL 2021 cut-offs",
                                {"AST": f"{ast[1]:.0f} U/L ({ast[0]})", "ALT": f"{alt[1]:.0f} U/L ({alt[0]})",
                                 "platelets": f"{plt[1]:.0f} ×10⁹/L ({plt[0]})", "age": str(age)}))
    else:
        out.append(scores.Score("FIB-4 (liver fibrosis)", None, "", None, "Sterling et al., Hepatology 2006",
                                note="needs AST, ALT, platelets and " + need))

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
                                note=f"cholesterol is {stale:.1f} years old" if stale > 1 else None))
    else:
        why = "SCORE2 covers ages 40 to 69" if age and not 40 <= age <= 69 else \
            "needs systolic BP, total and HDL cholesterol and " + need
        out.append(scores.Score("SCORE2 (10-year cardiovascular risk)", None, "%", None,
                                "SCORE2 working group, Eur Heart J 2021", note=why))

    tg = latest(marker_series(conn, "Triglycerides"))
    fpg = latest(series(conn, ["1558-6"]))
    if tg and fpg:
        t = scores.tyg(tg[1] * 88.57, fpg[1])
        out.append(scores.Score("TyG index (insulin resistance)", t, "", None,
                                "Simental-Mendía et al., Metab Syndr Relat Disord 2008",
                                {"triglycerides": f"{tg[1]:.2f} mmol/L ({tg[0]})",
                                 "fasting glucose": f"{fpg[1]:.0f} mg/dL ({fpg[0]})"},
                                note="no universal cut-off; around 8.5 to 8.8 is used in several cohorts"))
    if tc and hdl:
        out.append(scores.Score("Non-HDL cholesterol", tc[1] - hdl[1], "mmol/L", None,
                                "ESC/EAS 2019 dyslipidaemia guideline (secondary target)",
                                {"total cholesterol": f"{tc[1]:.2f} ({tc[0]})", "HDL": f"{hdl[1]:.2f} ({hdl[0]})"}))
    lpa = latest(marker_series(conn, "Lp(a)"))
    if lpa:
        band = "above 50 mg/dL, the ESC/EAS 2022 threshold for raised risk" if lpa[1] > 50 else \
            "below the ESC/EAS 2022 threshold of 50 mg/dL"
        out.append(scores.Score("Lp(a)", lpa[1], "mg/dL", band, "ESC/EAS consensus, Eur Heart J 2022",
                                {"Lp(a)": f"{lpa[1]:g} mg/dL ({lpa[0]})"},
                                note="largely inherited; one measurement in life is usually enough"))
    return out


# ── rendering ────────────────────────────────────────────────────────────────
def esc(s) -> str:
    return html.escape(str(s))


def fmt(v: float) -> str:
    if abs(v) >= 1000:
        return f"{v:,.0f}".replace(",", " ")
    if abs(v) >= 100:
        return f"{v:.0f}"
    if abs(v) >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"


def line_chart(points, title, unit, width=360, height=150):
    """One series: a 2px line, ≥8px markers when sparse, hover tooltips via <title> and data-tip."""
    if not points:
        return f'<figure class="chart empty"><figcaption>{esc(title)}</figcaption><p>No values yet.</p></figure>'
    pad_l, pad_r, pad_t, pad_b = 40, 12, 10, 22
    xs = [dt.date.fromisoformat(p[0]).toordinal() for p in points]
    ys = [p[1] for p in points]
    x0, x1 = min(xs), max(xs) if max(xs) > min(xs) else min(xs) + 1
    lo, hi = min(ys), max(ys)
    span = hi - lo or abs(hi) * 0.1 or 1
    lo, hi = lo - span * 0.15, hi + span * 0.15
    sx = lambda x: pad_l + (x - x0) / (x1 - x0) * (width - pad_l - pad_r)
    sy = lambda y: pad_t + (hi - y) / (hi - lo) * (height - pad_t - pad_b)
    path = " ".join(f"{'M' if i == 0 else 'L'}{sx(x):.1f},{sy(y):.1f}" for i, (x, y) in enumerate(zip(xs, ys)))
    ticks = [lo + (hi - lo) * f for f in (0.15, 0.5, 0.85)]
    grid = "".join(
        f'<line x1="{pad_l}" x2="{width - pad_r}" y1="{sy(t):.1f}" y2="{sy(t):.1f}" class="grid"/>'
        f'<text x="{pad_l - 6}" y="{sy(t) + 4:.1f}" class="tick" text-anchor="end">{esc(fmt(t))}</text>'
        for t in ticks)
    first, last = points[0][0][:7], points[-1][0][:7]
    xlab = (f'<text x="{pad_l}" y="{height - 4}" class="tick">{esc(first)}</text>'
            f'<text x="{width - pad_r}" y="{height - 4}" class="tick" text-anchor="end">{esc(last)}</text>')
    marks = ""
    r = 4 if len(points) <= 40 else 2.5
    for (d, v, src, lab), x, y in zip(points, xs, ys):
        tip = f"{d}: {fmt(v)} {unit}" + (f" · {lab}" if lab else "") + (f" · {src}" if src else "")
        marks += (f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="{r}" class="dot"/>'
                  f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="10" class="hit" data-tip="{esc(tip)}"><title>{esc(tip)}</title></circle>')
    last_v = points[-1][1]
    return (f'<figure class="chart"><figcaption><span>{esc(title)}</span>'
            f'<b>{esc(fmt(last_v))} <small>{esc(unit)}</small></b></figcaption>'
            f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)} over time">'
            f'{grid}{xlab}<path d="{path}" class="line"/>{marks}</svg>'
            f'<p class="meta">{len(points)} values · latest {esc(points[-1][0])}</p></figure>')


def score_card(s: scores.Score) -> str:
    if s.value is None:
        return (f'<article class="score missing"><h3>{esc(s.name)}</h3><p class="value">–</p>'
                f'<p class="note">{esc(s.note or "")}</p><p class="src">{esc(s.source)}</p></article>')
    inputs = "".join(f"<li><span>{esc(k)}</span> {esc(v)}</li>" for k, v in s.inputs.items())
    band = f'<p class="band">{esc(s.band)}</p>' if s.band else ""
    note = f'<p class="note">{esc(s.note)}</p>' if s.note else ""
    return (f'<article class="score"><h3>{esc(s.name)}</h3>'
            f'<p class="value">{esc(fmt(s.value))} <small>{esc(s.unit)}</small></p>{band}{note}'
            f'<details><summary>Inputs</summary><ul>{inputs}</ul></details>'
            f'<p class="src">{esc(s.source)}</p></article>')


CSS = """
:root{--surface:#fcfcfb;--card:#ffffff;--ink:#0b0b0b;--ink2:#52514e;--muted:#8a8984;--line:#2a78d6;
--grid:#e7e6e2;--border:#e3e2de;--accent:#2a78d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--surface:#1a1a19;--card:#232322;--ink:#f0efec;
--ink2:#c3c2b7;--muted:#8f8e86;--line:#3987e5;--grid:#34332f;--border:#3a3935;--accent:#3987e5}}
:root[data-theme="dark"]{--surface:#1a1a19;--card:#232322;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;
--line:#3987e5;--grid:#34332f;--border:#3a3935;--accent:#3987e5}
*{box-sizing:border-box}body{margin:0;background:var(--surface);color:var(--ink);
font:15px/1.45 -apple-system,BlinkMacSystemFont,"SF Pro Text","Helvetica Neue",Arial,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 16px 60px}
header h1{font-size:28px;margin:0 0 4px}header p{margin:0;color:var(--ink2)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:22px 0 8px}
.kpi{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 14px}
.kpi b{display:block;font-size:24px}.kpi span{color:var(--ink2);font-size:13px}
h2{font-size:19px;margin:34px 0 6px}h2+p{color:var(--ink2);margin:0 0 14px;max-width:820px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px}
.chart,.score{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:12px 14px;margin:0}
figcaption{display:flex;justify-content:space-between;align-items:baseline;font-weight:600}
figcaption b{font-size:20px}figcaption small,.value small{font-weight:400;color:var(--ink2);font-size:12px}
svg{width:100%;height:auto;display:block;margin-top:6px}
.line{fill:none;stroke:var(--line);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.dot{fill:var(--line);stroke:var(--card);stroke-width:2}.hit{fill:transparent;cursor:crosshair}
.grid line,line.grid{stroke:var(--grid);stroke-width:1}.tick{fill:var(--muted);font-size:10px}
.meta,.src,.note{color:var(--muted);font-size:12px;margin:6px 0 0}
.score h3{font-size:14px;margin:0;color:var(--ink2)}.value{font-size:30px;font-weight:650;margin:6px 0 2px}
.band{margin:0;font-weight:600}.score ul{margin:6px 0 0;padding-left:18px;font-size:13px;color:var(--ink2)}
.score li span{color:var(--muted)}.missing .value{color:var(--muted)}
.empty p{color:var(--muted)}.disclaimer{border-left:3px solid var(--accent);padding:8px 12px;margin-top:16px;
background:var(--card);color:var(--ink2);font-size:13px;max-width:900px}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);padding:6px 9px;
border-radius:6px;font-size:12px;display:none;z-index:9}
footer{margin-top:40px;color:var(--muted);font-size:12px}
"""

JS = """
const tip=document.getElementById('tip');
document.addEventListener('mousemove',e=>{const t=e.target.closest('[data-tip]');
if(!t){tip.style.display='none';return}tip.textContent=t.dataset.tip;tip.style.display='block';
tip.style.left=(e.clientX+12)+'px';tip.style.top=(e.clientY+12)+'px'});
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("db")
    ap.add_argument("--out", required=True)
    ap.add_argument("--smoker", choices=["yes", "no"], default="no")
    ap.add_argument("--region", choices=["low", "moderate", "high", "very high"], default="moderate")
    args = ap.parse_args()

    out = Path(args.out).expanduser()
    if str(ROOT) in str(out.resolve()):
        sys.exit("refusing to write health data into the repository")
    conn = store.connect(Path(args.db).expanduser(), read_only=True)

    p = conn.execute("MATCH (p:Patient) RETURN p.birthYear AS y, p.gender AS g").single()
    birth_year, sex = (p["y"], p["g"]) if p else (None, None)
    age = TODAY.year - birth_year if birth_year else None

    counts = {r["k"]: r["n"] for r in conn.execute(
        """MATCH (o:Observation) RETURN CASE WHEN o.sourceReport = 'apple-health-weekly' THEN 'weekly'
           WHEN o.sourceReport = 'whoop' THEN 'whoop' WHEN o.duplicateOf IS NOT NULL THEN 'copy' ELSE 'lab' END AS k,
           count(*) AS n""")}
    reports = conn.execute("MATCH (r:DiagnosticReport) RETURN count(r) AS n").single()["n"]
    loinc = conn.execute("MATCH (l:LoincCode) RETURN count(l) AS n").single()["n"]

    risk = compute_scores(conn, age, sex, args.smoker == "yes", args.region)
    wear = [line_chart(series(conn, [code]), t, u) for code, t, u in WEARABLES]
    whoop_rows = [series(conn, [code]) for code, _, _ in WHOOP]
    whoop = [line_chart(rows, t, u) for rows, (_, t, u) in zip(whoop_rows, WHOOP)] if any(whoop_rows) else []
    labs = [line_chart(marker_series(conn, t), t, u) for t, _, u in MARKERS]
    conn.close()

    kpi = lambda n, label: f'<div class="kpi"><b>{esc(n)}</b><span>{esc(label)}</span></div>'
    whoop_html = ('<div class="grid">' + "".join(whoop) + "</div>") if whoop else \
        "<p>No Whoop data in the graph yet. Put the Whoop export into the vault and import it.</p>"
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>My Health Graph</title>
<style>{CSS}</style></head><body><main>
<header><h1>My Health Graph</h1>
<p>Lab reports from Klarbefund, Apple Watch and Whoop, in one Relate graph on this Mac. Built {TODAY.isoformat()}
from Cypher queries on <code>health.rl</code> in the encrypted vault. Nothing on this page was sent anywhere.</p></header>
<section class="kpis">{kpi(reports, "lab reports")}{kpi(counts.get("lab", 0), "lab values")}
{kpi(loinc, "kinds of test (LOINC)")}{kpi(counts.get("weekly", 0), "Apple Health weekly means")}
{kpi(counts.get("whoop", 0), "Whoop days")}{kpi(counts.get("copy", 0), "copies counted once")}</section>
<h2>Risk scores</h2><p>Estimates from published formulas, each with the values it used and their dates.
{esc(f"Age {age}, {sex}" if age else "Year of birth not in the graph yet")}, smoking: {esc(args.smoker)}.</p>
<div class="grid">{"".join(score_card(s) for s in risk)}</div>
<p class="disclaimer">These scores estimate risk for groups of people with similar values; they are not a diagnosis
and say nothing certain about one person. Discuss them with your doctor. Klarbefund itself never judges a value.</p>
<h2>Whoop</h2><p>Daily recovery, strain, HRV and sleep from the Whoop export.</p>{whoop_html}
<h2>Apple Watch</h2><p>Weekly means from Apple Health, sent by Klarbefund.</p><div class="grid">{"".join(wear)}</div>
<h2>Lab trends</h2><p>Every value once, from scans and the laboratories' own files; hover a point for its source.</p>
<div class="grid">{"".join(labs)}</div>
<footer>Relate (Neo4j's embedded graph database) · health_graph · scripts/dashboard.py</footer>
</main><div id="tip"></div><script>{JS}</script></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    out.chmod(0o600)
    print(f"wrote {out} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    main()
