"""Published risk scores against the numbers their sources publish."""
import pytest

from health_graph import scores


@pytest.mark.parametrize("sex,region,expected", [
    # SCORE2 paper abstract: 50-year-old smoker, SBP 140, total cholesterol 5.5, HDL 1.3 mmol/L
    ("male", "low", 5.9), ("male", "very high", 14.0),
    ("female", "low", 4.2), ("female", "very high", 13.7),
])
def test_score2_reproduces_the_papers_examples(sex, region, expected):
    risk = scores.score2(50, sex, True, 140, 5.5, 1.3, region)
    assert round(risk, 1) == pytest.approx(expected, abs=0.1)


def test_score2_refuses_ages_it_was_not_made_for():
    with pytest.raises(ValueError):
        scores.score2(72, "male", False, 120, 5, 1.3)


def test_score2_bands_follow_esc_2021():
    assert scores.score2_band(2.0, 45) == "low to moderate"
    assert scores.score2_band(8.0, 45) == "very high"
    assert scores.score2_band(8.0, 55) == "high"


def test_egfr_ckd_epi_2021():
    # Male, 50, creatinine 1.0 mg/dL: 142 x (1/0.9)^-1.2 x 0.9938^50
    assert scores.egfr_ckd_epi_2021(1.0, 50, "male") == pytest.approx(91.7, abs=0.1)
    # Female, 50, creatinine 0.7 mg/dL: at kappa, so 142 x 0.9938^50 x 1.012
    assert scores.egfr_ckd_epi_2021(0.7, 50, "female") == pytest.approx(142 * 0.9938 ** 50 * 1.012, rel=1e-9)
    assert scores.egfr_stage(91.7) == "G1 (normal or high)"
    assert scores.egfr_stage(50) == "G3a (mildly to moderately decreased)"


def test_fib4_and_its_cut_offs():
    # (age x AST) / (platelets x sqrt(ALT)): 50 x 25 / (250 x 5) = 1.0
    assert scores.fib4(50, 25, 25, 250) == pytest.approx(1.0)
    assert scores.fib4_band(1.0, 50) == "below the low cut-off"
    assert scores.fib4_band(1.5, 66) == "below the low cut-off"  # 2.0 from 65
    assert scores.fib4_band(3.0, 50) == "above the high cut-off"


def test_tyg_and_units():
    assert scores.tyg(150, 100) == pytest.approx(8.92, abs=0.01)
    assert scores.to_mg_dl(5.0, "mmol/l", scores.CHOL_MG_PER_MMOL) == pytest.approx(193.35)
    assert scores.creatinine_mg_dl(88.42, "µmol/l") == pytest.approx(1.0)
    assert scores.to_mg_dl(5.0, "furlongs", 1) is None
