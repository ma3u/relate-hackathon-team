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
from health_graph.risk import (MARKERS, compute_scores, lab_light, latest, load_ranges,  # noqa: E402
                               marker_series, series)

TODAY = dt.date.today()

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


def line_chart(points, title, unit, width=360, height=150, light=None):
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
    for (d, v, src, lab, *_), x, y in zip(points, xs, ys):
        tip = f"{d}: {fmt(v)} {unit}" + (f" · {lab}" if lab else "") + (f" · {src}" if src else "")
        marks += (f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="{r}" class="dot"/>'
                  f'<circle cx="{sx(x):.1f}" cy="{sy(y):.1f}" r="10" class="hit" data-tip="{esc(tip)}"><title>{esc(tip)}</title></circle>')
    last_v = points[-1][1]
    badge = ""
    if light:
        badge = lamp(light[0], light[1]) + f'<p class="meta">{esc(light[2])}</p>'
    return (f'<figure class="chart"><figcaption><span>{esc(title)}</span>'
            f'<b>{esc(fmt(last_v))} <small>{esc(unit)}</small></b></figcaption>{badge}'
            f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)} over time">'
            f'{grid}{xlab}<path d="{path}" class="line"/>{marks}</svg>'
            f'<p class="meta">{len(points)} values · latest {esc(points[-1][0])}</p></figure>')


LAMP = {scores.GREEN: ("✓", "Green"), scores.AMBER: ("!", "Amber"), scores.RED: ("✕", "Red")}


def lamp(light: str, label: str, title: str = "") -> str:
    """A traffic light: colour, icon and words, never colour alone."""
    icon, word = LAMP[light]
    return (f'<p class="lamp {light}" title="{esc(title)}"><i aria-hidden="true">{icon}</i>'
            f'<span class="sr">{word}: </span>{esc(label)}</p>')


def score_card(s: scores.Score) -> str:
    if s.value is None:
        return (f'<article class="score missing"><h3>{esc(s.name)}</h3><p class="value">–</p>'
                f'<p class="note">{esc(s.note or "")}</p><p class="src">{esc(s.source)}</p></article>')
    inputs = "".join(f"<li><span>{esc(k)}</span> {esc(v)}</li>" for k, v in s.inputs.items())
    band = lamp(s.light, s.band or "") if s.light else (f'<p class="band">{esc(s.band)}</p>' if s.band else "")
    note = f'<p class="note">{esc(s.note)}</p>' if s.note else ""
    edge = f" edge-{s.light}" if s.light else ""
    return (f'<article class="score{edge}"><h3>{esc(s.name)}</h3>'
            f'<p class="value">{esc(fmt(s.value))} <small>{esc(s.unit)}</small></p>{band}{note}'
            f'<details><summary>Inputs</summary><ul>{inputs}</ul></details>'
            f'<p class="src">{esc(s.source)}</p></article>')



# ── the metadata model, drawn from the graph itself ─────────────────────────
MODEL_POS = {  # label -> (x, y, layer)
    "ScoreResult": (130, 70, "person"), "Patient": (130, 250, "person"), "OMOPPerson": (130, 450, "omop"),
    "Provenance": (390, 40, "person"), "DiagnosticReport": (390, 150, "person"),
    "Observation": (390, 300, "person"), "OMOPMeasurement": (390, 450, "omop"),
    "DocumentReference": (650, 115, "person"), "Organization": (650, 200, "person"),
    "NcbiTaxon": (650, 285, "ontology"), "LoincCode": (650, 370, "ontology"),
    "RiskScore": (920, 90, "knowledge"), "HealthRisk": (1110, 300, "knowledge"),
    "ReferenceRange": (920, 460, "knowledge"), "Knowledge": (1110, 470, "knowledge"),
}
LAYER = {"person": "#2a78d6", "omop": "#6250d6", "ontology": "#1baf7a", "knowledge": "#eb6834"}
LAYER_NAME = {"person": "Your data (FHIR)", "omop": "OMOP research model", "ontology": "Codes (LOINC, NCBI)",
              "knowledge": "Knowledge: risks, scores, ranges"}


def model_svg(conn) -> str:
    nodes = {r["l"]: r["n"] for r in conn.execute("MATCH (n) RETURN labels(n)[0] AS l, count(*) AS n")}
    edges = [dict(r) for r in conn.execute(
        "MATCH (a)-[r]->(b) RETURN labels(a)[0] AS a, type(r) AS t, labels(b)[0] AS b, count(*) AS n")]
    W, H = 1240, 540
    out = [f'<svg viewBox="0 0 {W} {H}" class="model" role="img" aria-label="Metadata model of the health graph">',
           '<defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
           'orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" class="arrow"/></marker></defs>']
    pos = dict(MODEL_POS)
    extra = [l for l in nodes if l not in pos]
    for i, l in enumerate(extra):
        pos[l] = (130 + i * 200, 520, "person")
    for e in edges:
        if e["a"] not in pos or e["b"] not in pos:
            continue
        (x1, y1, _), (x2, y2, _) = pos[e["a"]], pos[e["b"]]
        if e["a"] == e["b"]:  # self-loop (SAME_AS)
            out.append(f'<path d="M{x1 - 30},{y1 - 18} C{x1 - 60},{y1 - 70} {x1 + 60},{y1 - 70} {x1 + 30},{y1 - 18}" '
                       f'class="edge" marker-end="url(#arr)"/><text x="{x1}" y="{y1 - 62}" class="elabel" '
                       f'text-anchor="middle">{esc(e["t"])} · {e["n"]}</text>')
            continue
        # stop the line at the box edges
        dx, dy = x2 - x1, y2 - y1
        L = max((dx * dx + dy * dy) ** 0.5, 1)
        sx_, sy_ = x1 + dx / L * 70, y1 + dy / L * 22
        ex, ey = x2 - dx / L * 72, y2 - dy / L * 24
        out.append(f'<line x1="{sx_:.0f}" y1="{sy_:.0f}" x2="{ex:.0f}" y2="{ey:.0f}" class="edge" marker-end="url(#arr)">'
                   f'<title>{esc(e["a"])} -[:{esc(e["t"])}]-> {esc(e["b"])}: {e["n"]}</title></line>'
                   f'<text x="{(sx_ + ex) / 2:.0f}" y="{(sy_ + ey) / 2 - 4:.0f}" class="elabel" text-anchor="middle">'
                   f'{esc(e["t"])} · {e["n"]}</text>')
    for l, n in nodes.items():
        x, y, layer = pos[l]
        out.append(f'<g><rect x="{x - 70}" y="{y - 22}" width="140" height="44" rx="10" class="node" '
                   f'style="stroke:{LAYER[layer]}"/><text x="{x}" y="{y - 3}" class="nlabel" text-anchor="middle">'
                   f'{esc(l)}</text><text x="{x}" y="{y + 13}" class="ncount" text-anchor="middle">{n:,}</text></g>'
                   .replace(",", " "))
    legend = "".join(f'<span><i style="background:{c}"></i>{esc(LAYER_NAME[k])}</span>' for k, c in LAYER.items())
    return "".join(out) + f'</svg><div class="legend">{legend}</div>'


# ── five views: a health risk, its scores, its measures, your values ────────
RISK_VIEWS = ["cardiovascular", "diabetes", "kidney", "liver", "bone", "fitness"]
VIEW_CYPHER = """MATCH (h:HealthRisk {id: $risk})
OPTIONAL MATCH (rs:RiskScore)-[:ESTIMATES]->(h)
OPTIONAL MATCH (rs)-[:USES]->(u:LoincCode)
OPTIONAL MATCH (m:LoincCode)-[k:MARKER_OF]->(h)
RETURN h.name AS risk, collect(DISTINCT [rs.id, rs.name, u.code]) AS uses,
       collect(DISTINCT [m.code, k.source]) AS markers"""
CODE_TITLE = {c: t for t, codes, _ in MARKERS for c in codes}
CODE_TITLE.update({code: t for code, t, _ in WEARABLES})
CODE_TITLE.update({"59261-8": "HbA1c"})
LIGHT_HEX = {scores.GREEN: "#0ca30c", scores.AMBER: "#fab219", scores.RED: "#d03b3b"}
ICON = {scores.GREEN: "✓", scores.AMBER: "!", scores.RED: "✕"}


def measure_value(conn, title, codes, ranges, sex):
    """(text, light) for the latest value of a measure, or None without data."""
    marker = next(((t, u) for t, cs, u in MARKERS if t == title), None)
    if marker:
        pts = marker_series(conn, title)
        unit = marker[1]
    else:
        pts = series(conn, codes)
        unit = next((u for c, t, u in WEARABLES if t == title), "")
    p = latest(pts)
    if not p:
        return None
    light = lab_light(ranges, p, unit, sex) if marker else None
    if light is None and title in ("Systolic BP", "Diastolic BP"):  # no range in the table: ESC 2024 categories
        light = scores.bp_light(p[1], None) if title == "Systolic BP" else scores.bp_light(0, p[1])
    return f"{fmt(p[1])} {unit}".strip(), (light[0] if light else None)


def risk_measures(conn, risk_id, ranges, sex):
    """(risk name, {score id: (name, codes)}, measures with a value, measures without)."""
    rows = list(conn.execute(VIEW_CYPHER, {"risk": risk_id}))
    if not rows:
        return None
    r = rows[0]
    scores_used: dict[str, tuple[str, set]] = {}
    for sid, sname, code in r["uses"]:
        if sid:
            scores_used.setdefault(sid, (sname, set()))[1].add(code)
    measures: dict[str, set] = {}
    for code, _ in r["markers"]:
        if code:
            measures.setdefault(CODE_TITLE.get(code, code), set()).add(code)
    for _, (_, codes) in scores_used.items():
        for code in codes:
            measures.setdefault(CODE_TITLE.get(code, code), set()).add(code)
    shown, missing = [], []
    for title, codes in sorted(measures.items()):
        v = measure_value(conn, title, sorted(codes), ranges, sex)
        (shown if v else missing).append((title, codes, v))
    return r["risk"], scores_used, shown, missing


def risk_view(conn, risk_id, by_score, ranges, sex) -> str:
    found = risk_measures(conn, risk_id, ranges, sex)
    if not found:
        return ""
    name, scores_used, shown, missing = found
    r = {"risk": name}

    W, H, cx, cy = 620, 470, 310, 235
    out = [f'<svg viewBox="0 0 {W} {H}" class="view" role="img" aria-label="{esc(r["risk"])}: scores and measures">']
    import math as _m
    spos = {}
    for i, (sid, (sname, _)) in enumerate(scores_used.items()):
        a = -_m.pi / 2 + (i + 0.5) * 2 * _m.pi / max(len(scores_used), 1)
        spos[sid] = (cx + 105 * _m.cos(a), cy + 80 * _m.sin(a))
    mpos = {}
    for i, (title, codes, v) in enumerate(shown):
        a = -_m.pi / 2 + i * 2 * _m.pi / max(len(shown), 1)
        mpos[title] = (cx + 240 * _m.cos(a), cy + 185 * _m.sin(a))
    for title, codes, v in shown:  # MARKER_OF: measure -> risk
        x, y = mpos[title]
        out.append(f'<line x1="{x:.0f}" y1="{y:.0f}" x2="{cx}" y2="{cy}" class="vmark"/>')
    for sid, (sname, codes) in scores_used.items():  # USES and ESTIMATES
        sx_, sy_ = spos[sid]
        for title, cs, v in shown:
            if cs & codes:
                x, y = mpos[title]
                out.append(f'<line x1="{sx_:.0f}" y1="{sy_:.0f}" x2="{x:.0f}" y2="{y:.0f}" class="vuse"/>')
        out.append(f'<line x1="{sx_:.0f}" y1="{sy_:.0f}" x2="{cx}" y2="{cy}" class="vest"/>')
    out.append(f'<circle cx="{cx}" cy="{cy}" r="46" class="vrisk"/><text x="{cx}" y="{cy + 4}" class="vrisklabel" '
               f'text-anchor="middle">{esc(r["risk"].replace("Low cardiorespiratory fitness", "Low fitness"))}</text>')
    for sid, (sname, _) in scores_used.items():
        x, y = spos[sid]
        s = by_score.get(sid)
        fill = LIGHT_HEX.get(s.light) if s and s.light else "#5b6270"
        val = f"{fmt(s.value)}{(' ' + s.unit) if s.unit in ('%',) else ''}" if s and s.value is not None else "–"
        icon = ICON.get(s.light, "") if s and s.light else ""
        out.append(f'<rect x="{x - 62:.0f}" y="{y - 20:.0f}" width="124" height="40" rx="20" style="fill:{fill}" class="vscore"/>'
                   f'<text x="{x:.0f}" y="{y - 3:.0f}" class="vscorelabel" text-anchor="middle">{icon} {esc(sname.split(" (")[0])}</text>'
                   f'<text x="{x:.0f}" y="{y + 12:.0f}" class="vscorelabel small" text-anchor="middle">{esc(val)}</text>')
    for title, codes, (text, light) in shown:
        x, y = mpos[title]
        fill = LIGHT_HEX.get(light, "#3a3f48")
        icon = ICON.get(light, "")
        out.append(f'<circle cx="{x:.0f}" cy="{y:.0f}" r="9" style="fill:{fill}" class="vdot"/>'
                   f'<text x="{x:.0f}" y="{y + 4:.0f}" class="vicon" text-anchor="middle">{icon}</text>'
                   f'<text x="{x:.0f}" y="{y + 24:.0f}" class="vmlabel" text-anchor="middle">{esc(title)}</text>'
                   f'<text x="{x:.0f}" y="{y + 38:.0f}" class="vmval" text-anchor="middle">{esc(text)}</text>')
    out.append("</svg>")
    more = f'<p class="meta">Also a marker, no value yet: {esc(", ".join(t for t, _, _ in missing))}</p>' if missing else ""
    return (f'<figure class="chart viewfig"><figcaption><span>{esc(r["risk"])}</span></figcaption>{"".join(out)}{more}'
            f'<details><summary>Cypher</summary><pre>{esc(VIEW_CYPHER.replace("$risk", repr(risk_id)))}</pre></details></figure>')


# ── rings: the state of each health risk and each wearable signal ────────────
RING_HEX = {scores.GREEN: "#16c60c", scores.AMBER: "#f7b500", scores.RED: "#ff3b3b", None: "#5b6270"}
DOMAIN_SHORT = {"cardiovascular": "Heart", "diabetes": "Metabolism", "kidney": "Kidney", "liver": "Liver",
                "fitness": "Fitness", "bone": "Bone"}


def pct_light(pct: float) -> str:
    """Thirds: 67 % and up green, 34 % and up amber, below red."""
    return scores.GREEN if pct >= 67 else scores.AMBER if pct >= 34 else scores.RED


def ring(pct: float | None, light: str | None, big: str, label: str, sub: str, size: int = 150) -> str:
    r, w = 58, 11
    c = 2 * math.pi * r
    filled = c * max(0.0, min(1.0, (pct or 0) / 100))
    col = RING_HEX.get(light, RING_HEX[None])
    icon = {scores.GREEN: "✓", scores.AMBER: "!", scores.RED: "✕"}.get(light, "")
    return (f'<div class="ring"><svg viewBox="0 0 150 150" width="{size}" height="{size}" role="img" '
            f'aria-label="{esc(label)} {esc(big)}">'
            f'<circle cx="75" cy="75" r="{r}" class="track" stroke-width="{w}"/>'
            f'<circle cx="75" cy="75" r="{r}" fill="none" stroke="{col}" stroke-width="{w}" stroke-linecap="round" '
            f'stroke-dasharray="{filled:.1f} {c:.1f}" transform="rotate(-90 75 75)"/>'
            f'<text x="75" y="80" text-anchor="middle" class="ringbig">{esc(big)}</text>'
            f'<text x="75" y="102" text-anchor="middle" class="ringicon" fill="{col}">{icon}</text></svg>'
            f'<b>{esc(label)}</b><span>{esc(sub)}</span></div>')


def own_percentile(values: list[float], latest_value: float, higher_is_better: bool) -> float:
    """Where the latest week sits among the person's own weeks (0-100)."""
    if not values:
        return 50.0
    below = sum(1 for v in values if v < latest_value) + 0.5 * sum(1 for v in values if v == latest_value)
    p = 100 * below / len(values)
    return p if higher_is_better else 100 - p


def weekly_light(code: str, value: float, history: list[float]) -> tuple[float, str]:
    """(ring %, light) for one week of a wearable signal."""
    if code == "93832-4":  # sleep, h/d: adults need 7 to 9 h (AASM/SRS consensus 2015)
        return min(100, value / 8 * 100), (scores.GREEN if value >= 7 else scores.AMBER if value >= 6 else scores.RED)
    if code == "41950-7":  # steps/d: risk falls to about 8,000-10,000 (Paluch 2022); <5,000 sedentary (Tudor-Locke 2013)
        return min(100, value / 10000 * 100), (scores.GREEN if value >= 8000 else scores.AMBER if value >= 5000 else scores.RED)
    higher = code != "40443-4"  # resting heart rate: lower is better
    p = own_percentile(history, value, higher)
    return p, pct_light(p)


WEAR_RINGS = [  # code, label, unit, how it is judged
    ("93832-4", "Sleep", "h", "7–9 h recommended (AASM/SRS)"),
    ("41950-7", "Steps", "/d", "8–10k/d (Paluch 2022)"),
    ("80404-7", "HRV", "ms", "vs your last 52 weeks"),
    ("40443-4", "Resting HR", "/min", "vs your last 52 weeks"),
    ("94122-9", "VO₂ max", "", "vs your last 52 weeks"),
]


def strip(code: str, points, weeks: int = 26) -> str:
    """The last `weeks` weeks as small bars, each coloured by that week's own state."""
    pts = points[-weeks:]
    if not pts:
        return ""
    vals = [p[1] for p in points]
    hi = max(p[1] for p in pts) or 1
    bars = []
    for i, p in enumerate(pts):
        history = [v for v in vals[max(0, len(vals) - len(pts) + i - 52): len(vals) - len(pts) + i]] or vals
        _, light = weekly_light(code, p[1], history)
        h = 6 + 30 * p[1] / hi
        bars.append(f'<rect x="{i * 7}" y="{38 - h:.1f}" width="5" height="{h:.1f}" rx="2" fill="{RING_HEX[light]}">'
                    f'<title>{esc(p[0])}: {esc(fmt(p[1]))}</title></rect>')
    return f'<svg viewBox="0 0 {len(pts) * 7} 40" class="strip" role="img" aria-label="last {len(pts)} weeks">{"".join(bars)}</svg>'


def hero(conn, ranges, sex, by_score) -> str:
    body = []
    for rid in RISK_VIEWS:
        found = risk_measures(conn, rid, ranges, sex)
        if not found:
            continue
        _, _, shown, _ = found
        lights = [v[1] for _, _, v in shown if v and v[1]]
        if rid == "fitness" or not lights:  # wearables only: their own-history rings
            parts = []
            for code in ("94122-9", "40443-4"):
                pts = series(conn, [code])
                if pts:
                    parts.append(weekly_light(code, pts[-1][1], [p[1] for p in pts[-53:-1]])[0])
            pct = sum(parts) / len(parts) if parts else None
            sub = "VO₂ max and resting HR vs your year"
        else:
            g, a, rd = (lights.count(x) for x in (scores.GREEN, scores.AMBER, scores.RED))
            pct = 100 * (g + 0.5 * a) / len(lights)
            sub = f"{g} ✓  {a} !  {rd} ✕"
        score = next((s for s in by_score.values() if s.id and s.value is not None and
                      {"score2": "cardiovascular", "egfr": "kidney", "fib4": "liver", "tyg": "diabetes"}.get(s.id) == rid), None)
        if score:
            sub += f" · {score.name.split(' (')[0]} {fmt(score.value)}{' %' if score.unit == '%' else ''}"
        body.append(ring(pct, pct_light(pct) if pct is not None else None,
                         f"{pct:.0f}%" if pct is not None else "–", DOMAIN_SHORT[rid], sub))
    wear = []
    for code, label, unit, how in WEAR_RINGS:
        pts = series(conn, [code])
        if not pts:
            continue
        pct, light = weekly_light(code, pts[-1][1], [p[1] for p in pts[-53:-1]])
        big = f"{fmt(pts[-1][1])}"
        wear.append(f'<div class="wear">{ring(pct, light, big, f"{label} {unit}".strip(), how)}{strip(code, pts)}'
                    f'<span class="when">week of {esc(pts[-1][0])}</span></div>')
    return (f'<section class="hero"><h2>Health domains</h2><p>Share of each risk\'s measures in range: green counts '
            f'fully, amber half, red not at all. Fitness: VO₂ max and resting heart rate against your own last year.</p>'
            f'<div class="rings">{"".join(body)}</div>'
            f'<h2>This week</h2><p>Latest weekly means from Apple Watch, each against a published recommendation or your '
            f'own last 52 weeks; the bars are the last 26 weeks, coloured the same way.</p>'
            f'<div class="rings wearables">{"".join(wear)}</div></section>')

CSS = """
:root{--surface:#050607;--card:#111317;--ink:#ffffff;--ink2:#b9bfc9;--muted:#7d8590;--line:#3d9bff;
--grid:#22262d;--border:#1d2127;--accent:#3d9bff;color-scheme:dark}
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
.hero h2{margin-top:30px}.rings{display:grid;grid-template-columns:repeat(auto-fit,minmax(165px,1fr));gap:12px}
.ring{background:var(--card);border:1px solid var(--border);border-radius:18px;padding:16px 10px 14px;
display:flex;flex-direction:column;align-items:center;text-align:center}
.ring svg{display:block;margin:0}.ring .track{fill:none;stroke:#23272e}
.ringbig{fill:#fff;font-size:30px;font-weight:800;letter-spacing:-.5px}.ringicon{font-size:15px;font-weight:800}
.ring b{font-size:15px;margin-top:6px;letter-spacing:.06em;text-transform:uppercase}
.ring span{color:var(--ink2);font-size:12px;margin-top:3px}
.wear{display:flex;flex-direction:column;align-items:stretch;gap:6px}.wear .ring{border-radius:18px 18px 6px 6px}
.strip{width:100%;height:40px;background:var(--card);border:1px solid var(--border);border-radius:6px 6px 14px 14px;padding:4px}
.when{color:var(--muted);font-size:11px;text-align:center}
.views{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:14px}
.view,.model{width:100%;height:auto}.vmark{stroke:var(--grid);stroke-width:1.5;stroke-dasharray:4 4}
.vuse{stroke:var(--muted);stroke-width:1.5}.vest{stroke:var(--accent);stroke-width:3}
.vrisk{fill:var(--accent)}.vrisklabel{fill:#fff;font-size:11px;font-weight:700}
.vscore{stroke:var(--card);stroke-width:2}.vscorelabel{fill:#fff;font-size:11px;font-weight:700}
.vscorelabel.small{font-size:11px;font-weight:600}.vdot{stroke:var(--card);stroke-width:2}
.vicon{fill:#fff;font-size:10px;font-weight:800}.vmlabel{fill:var(--ink);font-size:11px;font-weight:600}
.vmval{fill:var(--ink2);font-size:10.5px}pre{white-space:pre-wrap;font-size:11.5px;color:var(--ink2)}
.node{fill:var(--card);stroke-width:2.5}.nlabel{fill:var(--ink);font-size:13px;font-weight:650}
.ncount{fill:var(--ink2);font-size:11.5px}.edge{stroke:var(--muted);stroke-width:1.3;fill:none}
.arrow{fill:var(--muted)}.elabel{fill:var(--ink2);font-size:10px}
.legend{display:flex;flex-wrap:wrap;gap:16px;font-size:12px;color:var(--ink2);margin-top:8px}
.legend i{display:inline-block;width:12px;height:12px;border-radius:3px;margin-right:6px;vertical-align:-1px}
:root{--good:#0ca30c;--warn:#fab219;--crit:#d03b3b}
.lamp{display:flex;align-items:center;gap:8px;margin:6px 0 2px;font-weight:600;font-size:14px}
.lamp i{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:50%;font-style:normal;
font-size:13px;font-weight:800;color:#fff;flex:none}
.lamp.green i{background:var(--good)}.lamp.amber i{background:var(--warn);color:#1a1a19}.lamp.red i{background:var(--crit)}
.chart .lamp{font-size:12px;font-weight:500;color:var(--ink2)}.chart .lamp i{width:18px;height:18px;font-size:11px}
.score.edge-green{border-left:5px solid var(--good)}.score.edge-amber{border-left:5px solid var(--warn)}
.score.edge-red{border-left:5px solid var(--crit)}
.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}
.signal{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 4px}
.signal .lamp{background:var(--card);border:1px solid var(--border);border-radius:999px;padding:6px 12px 6px 8px;margin:0}
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
    ranges = load_ranges(conn)
    labs = []
    for t, _, u in MARKERS:
        pts = marker_series(conn, t)
        labs.append(line_chart(pts, t, u, light=lab_light(ranges, pts[-1], u, sex) if pts else None))
    by_score = {s.id: s for s in risk if s.id}
    model = model_svg(conn)
    views = [risk_view(conn, rid, by_score, ranges, sex) for rid in RISK_VIEWS]
    rings = hero(conn, ranges, sex, by_score)
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
{rings}
<h2>Risk scores</h2><p>Estimates from published formulas, each with the values it used and their dates.
{esc(f"Age {age}, {sex}" if age else "Year of birth not in the graph yet")}, smoking: {esc(args.smoker)}.</p>
<div class="signal">{"".join(lamp(s.light, s.name.split(" (")[0]) for s in risk if s.light)}</div>
<div class="grid">{"".join(score_card(s) for s in risk)}</div>
<p class="disclaimer">These scores estimate risk for groups of people with similar values; they are not a diagnosis
and say nothing certain about one person. Discuss them with your doctor. Klarbefund itself never judges a value.</p>
<h2>Whoop</h2><p>Daily recovery, strain, HRV and sleep from the Whoop export.</p>{whoop_html}
<h2>Apple Watch</h2><p>Weekly means from Apple Health, sent by Klarbefund.</p><div class="grid">{"".join(wear)}</div>
<h2>How the measures connect</h2><p>One Cypher walk per health risk: the scores that estimate it, the measures they
use and the measures guidelines name as its markers, each with your latest value and its light.</p>
<div class="views">{"".join(views)}</div>
<h2>Lab trends</h2><p>Every value once. Lights: green inside the optimal band (or inside the guideline range when no
optimal band is published), amber inside the guideline range but not optimal, red outside it. Ranges from Klarbefund's
sourced reference table, stored in the graph as <code>ReferenceRange</code> nodes; without one, the range the
laboratory printed decides.</p>
<div class="grid">{"".join(labs)}</div>
<h2>The metadata model</h2><p>Every label and relationship in this graph, with live counts, from
<code>MATCH (a)-[r]-&gt;(b) RETURN labels(a)[0], type(r), labels(b)[0], count(*)</code>.</p>
<figure class="chart modelfig">{model}</figure>
<footer>Relate (Neo4j's embedded graph database) · health_graph · scripts/dashboard.py</footer>
</main><div id="tip"></div><script>{JS}</script></body></html>"""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    out.chmod(0o600)
    print(f"wrote {out} ({len(page) // 1024} KB)")


if __name__ == "__main__":
    main()
