"""Published clinical risk scores, computed from the graph on the person's own Mac.

These are estimates from published formulas, shown with their source and the
inputs they used. They are not a diagnosis and judge nothing on their own;
Klarbefund itself never does this (it is not a medical device). The person
asked for them on their own private dashboard.

Each function takes plain numbers in the units its paper uses; `units` below
converts what German labs print.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

# ── units ────────────────────────────────────────────────────────────────────
CHOL_MG_PER_MMOL = 38.67   # cholesterol mg/dL per mmol/L
TG_MG_PER_MMOL = 88.57     # triglycerides
GLUCOSE_MG_PER_MMOL = 18.016
CREATININE_UMOL_PER_MG = 88.42  # µmol/L per mg/dL


def to_mg_dl(value: float, unit: str, per_mmol: float) -> float | None:
    """mg/dL from mg/dL or mmol/L; None for a unit we do not know."""
    u = (unit or "").replace(" ", "").lower()
    if u in ("mg/dl",):
        return value
    if u in ("mmol/l",):
        return value * per_mmol
    return None


def creatinine_mg_dl(value: float, unit: str) -> float | None:
    u = (unit or "").replace(" ", "").lower()
    if u == "mg/dl":
        return value
    if u in ("µmol/l", "umol/l", "μmol/l"):
        return value / CREATININE_UMOL_PER_MG
    return None


@dataclass
class Score:
    name: str
    value: float | None
    unit: str
    band: str | None            # the published category, worded as the source words it
    source: str                 # citation
    inputs: dict[str, str] = field(default_factory=dict)
    note: str | None = None


# ── kidney: CKD-EPI 2021 (race-free) ─────────────────────────────────────────
def egfr_ckd_epi_2021(creatinine_mg_dl: float, age: int, sex: str) -> float:
    """eGFR in mL/min/1.73 m². Inker LA et al., N Engl J Med 2021;385:1737-49."""
    female = sex == "female"
    kappa, alpha = (0.7, -0.241) if female else (0.9, -0.302)
    ratio = creatinine_mg_dl / kappa
    egfr = 142 * min(ratio, 1) ** alpha * max(ratio, 1) ** -1.200 * 0.9938 ** age
    return egfr * 1.012 if female else egfr


def egfr_stage(egfr: float) -> str:
    """KDIGO 2012 GFR categories."""
    for limit, stage in ((90, "G1 (normal or high)"), (60, "G2 (mildly decreased)"),
                         (45, "G3a (mildly to moderately decreased)"),
                         (30, "G3b (moderately to severely decreased)"), (15, "G4 (severely decreased)")):
        if egfr >= limit:
            return stage
    return "G5 (kidney failure)"


# ── liver: FIB-4 ─────────────────────────────────────────────────────────────
def fib4(age: int, ast: float, alt: float, platelets_10e9_l: float) -> float:
    """Sterling RK et al., Hepatology 2006;43:1317-25. AST/ALT in U/L."""
    return age * ast / (platelets_10e9_l * math.sqrt(alt))


def fib4_band(value: float, age: int) -> str:
    """Published cut-offs: <1.30 low (<2.0 from age 65), >2.67 high (EASL 2021)."""
    low = 2.0 if age >= 65 else 1.30
    if value < low:
        return "below the low cut-off"
    if value > 2.67:
        return "above the high cut-off"
    return "between the cut-offs (indeterminate)"


# ── cardiovascular: SCORE2 (ESC 2021), ages 40-69 ────────────────────────────
# SCORE2 working group and ESC Cardiovascular risk collaboration, Eur Heart J
# 2021;42:2439-54, supplementary material. Coefficients as in the open-source
# RiskScorescvd implementation, which reproduces the paper's example risks
# (tests/test_scores.py). Cholesterol in mmol/L, SBP in mmHg.
_SCORE2 = {
    "male": dict(age=0.3742, smoking=0.6012, sbp=0.2777, tchol=0.1458, hdl=-0.2698,
                 smoking_age=-0.0755, sbp_age=-0.0255, tchol_age=-0.0281, hdl_age=0.0426, s0=0.9605),
    "female": dict(age=0.4648, smoking=0.7744, sbp=0.3131, tchol=0.1002, hdl=-0.2606,
                   smoking_age=-0.1088, sbp_age=-0.0277, tchol_age=-0.0226, hdl_age=0.0613, s0=0.9776),
}
_SCORE2_REGION = {  # (scale1, scale2) per sex
    "low": {"male": (-0.5699, 0.7476), "female": (-0.7380, 0.7019)},
    "moderate": {"male": (-0.1565, 0.8009), "female": (-0.3143, 0.7701)},
    "high": {"male": (0.3207, 0.9360), "female": (0.5710, 0.9369)},
    "very high": {"male": (0.5836, 0.8294), "female": (0.9412, 0.8329)},
}


def score2(age: int, sex: str, smoker: bool, sbp: float, tchol_mmol: float, hdl_mmol: float,
           region: str = "moderate") -> float:
    """10-year risk of fatal and non-fatal cardiovascular disease, in percent."""
    if not 40 <= age <= 69:
        raise ValueError("SCORE2 is defined for ages 40 to 69")
    c = _SCORE2[sex]
    a = (age - 60) / 5
    s = (sbp - 120) / 20
    t = tchol_mmol - 6
    h = (hdl_mmol - 1.3) / 0.5
    smk = 1.0 if smoker else 0.0
    lp = (c["age"] * a + c["smoking"] * smk + c["sbp"] * s + c["tchol"] * t + c["hdl"] * h
          + c["smoking_age"] * a * smk + c["sbp_age"] * a * s + c["tchol_age"] * a * t + c["hdl_age"] * a * h)
    uncalibrated = 1 - c["s0"] ** math.exp(lp)
    scale1, scale2 = _SCORE2_REGION[region][sex]
    return 100 * (1 - math.exp(-math.exp(scale1 + scale2 * math.log(-math.log(1 - uncalibrated)))))


def score2_band(risk: float, age: int) -> str:
    """ESC 2021 prevention guideline risk categories for apparently healthy people."""
    low, high = (2.5, 7.5) if age < 50 else (5, 10)
    if risk < low:
        return "low to moderate"
    if risk < high:
        return "high"
    return "very high"


# ── metabolic: TyG index ─────────────────────────────────────────────────────
def tyg(triglycerides_mg_dl: float, fasting_glucose_mg_dl: float) -> float:
    """Simental-Mendía LE et al., Metab Syndr Relat Disord 2008;6:299-304."""
    return math.log(triglycerides_mg_dl * fasting_glucose_mg_dl / 2)
