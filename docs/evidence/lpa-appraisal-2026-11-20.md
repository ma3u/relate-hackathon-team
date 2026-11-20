# Lipoprotein(a): appraisal of four studies for one person's question

Question, for a rounded case profile: a man aged 45 to 55 without cardiovascular disease, untreated LDL-C about 170 mg/dL, Lp(a) 30 mg/dL (0.3 g/L) in one laboratory and 10 mg/dL (0.1 g/L) in another. "Does Lp(a) at this level raise his risk, and does any treatment of Lp(a) help?"

This is an appraisal of evidence. It contains no therapy recommendation.

Prepared 2026-11-20. Legend: ✔ read in full, ◐ abstract (or abstract plus front matter) only.

| # | Study | PMID | What was read |
|---|---|---|---|
| 1 | Lp(a)HORIZON, pelacarsen, NEJM 2026 | 43001734 | ◐ PubMed abstract; NEJM full text is subscription only (Europe PMC: "Subscription required") |
| 1b | Lp(a)HORIZON extended analyses, NEJM Evidence 2026 | 42998055 | ◐ PubMed abstract; subscription only |
| 1c | ClinicalTrials.gov NCT04023552 | n/a | ✔ current registry record (CT.gov MCP). Version history: not reachable (HTTP 403 on the history endpoint; not bypassed) |
| 2 | EPIC-Norfolk, Eur Heart J 2025 | 40167249 | ✔ PMC12517748 full text (body, tables, declarations; supplement not read) |
| 3 | Women's Health Study, JAMA Cardiol 2026 | 41499112 | ◐ PMC12780984 is under embargo: only abstract, key points and article information (disclosures, funding) were available. Methods, tables and results body not read |
| 4 | Tel Aviv ambulatory cohort, Clin Res Cardiol 2026 | 41400669 | ◐ PubMed abstract and declarations; paywalled |
| G | ESC/EAS 2025 focused update | 40878289 | Not read: PubMed record has no abstract, not in PMC, publisher page answered with a bot check (not bypassed). Only the PubMed record (erratum link) was read |

All quotes below are in `quotes.json` and were checked by `check_quotes.py` against the saved source texts in this folder: 52 of 52 quotes are exact substrings after whitespace normalisation, all 25 words or fewer.

## Two things to settle before reading any study

**Units.** 0.3 g/L = 30 mg/dL; 0.1 g/L = 10 mg/dL. Both are mass units. Trial and guideline thresholds in nmol/L (particle number) cannot be converted exactly from mg/dL because the conversion depends on apo(a) isoform size; commonly used factors of about 2.0 to 2.5 nmol/L per mg/dL are approximations (background knowledge, not from the sources read).

**Two values from two laboratories, 10 and 30 mg/dL.** Lp(a) is largely genetically determined and usually stable within a person, so a threefold difference is more likely to reflect different assays, calibrators or labs than a biological change (background knowledge, not from the sources read). None of the four studies addresses repeat or discordant measurements: every one uses a single baseline value. Which of the two values is the person's "true" level is therefore outside what these studies can answer, and this matters because 10 mg/dL and 30 mg/dL fall into different categories in every study below.

---

## Study 1: Lp(a)HORIZON (pelacarsen) ◐ (abstracts) plus ✔ registry

### A. Facts checked by code or registry

- Publication status: NEJM, online ahead of print 7 Nov 2026 (PubMed status `aheadofprint`). PubMed `CommentsCorrections`: none (no erratum, retraction, expression of concern or linked comment). elink `pubmed_pubmed_comments`: none. Same for the NEJM Evidence companion 42998055. Both are two weeks old, so absence of comments is expected and uninformative.
- Design: international, randomised, double-blind, placebo-controlled phase 3 trial; pelacarsen 80 mg subcutaneous monthly vs placebo, 1:1.
- Registration: NCT04023552 (registry DataBank entry in PubMed record matches). Start 2019-12-12, primary completion 2026-07-16, status COMPLETED, `has_results: false` on CT.gov.
- Registered vs reported primary outcome: the current registry record lists **two** primary outcomes: expanded MACE (CV death, non-fatal MI, non-fatal stroke, urgent coronary revascularisation requiring hospitalisation) in Lp(a) at least 70 mg/dL, and the same in Lp(a) at least 90 mg/dL. The NEJM abstract reports both (HR 1.02 and HR 1.00). This matches the current record. Whether the record was changed during the trial (for example, adding the 90 mg/dL population) could not be checked: the CT.gov history endpoint returned 403.
- Sample size: 8350 randomised, 8322 in efficacy analysis (abstract); CT.gov enrollment field 8323. Small discrepancy (one participant) between registry and efficacy set; not explained in what was read.
- Follow-up: median 4.7 years (registry time frame "approximately 4 years").
- Funding: Novartis (sponsor). Several authors are Novartis employees (affiliation list).

### B. Checklist with quotes

- Population: "involving patients with preexisting cardiovascular disease and a lipoprotein(a) level of at least 70 mg per deciliter" (43001734). "The mean age of the patients was 59.7 years, and 27.0% were women." Registry: "Lp(a) ≥ 70 mg/dL at the screening visit, measured at the Central laboratory". Match to the person: no on every axis that matters: secondary prevention (he has no CVD), Lp(a) at least 70 mg/dL (he has 30 or 10), older on average. Sex partly matches (73% men). Ethnic/European share not given in the abstract.
- Unit and assay: entry in mg/dL, results in nmol/L: "The median lipoprotein(a) level at baseline was 236 nmol per liter." Assay not described in the abstract.
- Exposure measured once? Not applicable as exposure; eligibility on a central-lab screening value; on-treatment Lp(a) measured at 3 and 12 months.
- Adjustment set: randomised comparison; not applicable.
- Absolute risks: "A primary end-point event occurred in 511 patients (12.3%) in the pelacarsen group and in 503 (12.1%) in the placebo group"; "hazard ratio, 1.02, 95% confidence interval [CI], 0.90 to 1.15, P = 0.76". At least 90 mg/dL: "(hazard ratio, 1.00; 95% CI, 0.87 to 1.15; P = 0.99)". Safety: "Serious adverse events occurred in 1553 of 4166 patients (37.3%) who received pelacarsen and in 1709 of 4154 (41.1%) who received placebo."
- Pre-specified vs post hoc: the two primary analyses are registered. The NEJM Evidence analyses are explicitly further analyses: "Analyses included on-treatment, uninterrupted treatment, total primary end point events (first and recurrent events), landmark analyses". Whether these were pre-specified in the SAP cannot be judged from the abstract. Landmark result: "participants who achieved lipoprotein(a) lower than or equal to the median (69.5 nmol/l) (hazard ratio, 1.10; 95% CI, 0.93 to 1.29)". "There was also no association between pelacarsen treatment and the primary end point in any of the evaluated key subgroups".
- Funding statement: "(Funded by Novartis; Lp[a]HORIZON ClinicalTrials.gov number, NCT04023552.)"

### C. Judgement items (listed, not rated)

- Risk of bias: randomised, placebo-controlled, blinded per registry title, adjudicated end points (clinical endpoint committee per registry). Allocation concealment, missing data, adherence (the uninterrupted-treatment subset of about 1500 per arm suggests many interruptions) could not be checked without full text.
- Conflicts of interest: industry-funded; the result is null against the sponsor's commercial interest, which lowers concern about favourable spin in the main paper.
- Publication / spin: the authors' conclusion is plainly null. The NEJM Evidence paper explores on-treatment and landmark analyses; these are observational within a trial and also null, so no positive spin was found.
- Applicability: indirect for this person in population (secondary vs primary prevention), in exposure level (at least 70 mg/dL vs 10 to 30 mg/dL) and in intervention (one antisense agent). Other Lp(a)-lowering agents (siRNA, oral inhibitors) are not tested here.

### Verdict

Lp(a)HORIZON can say, with randomised evidence, that lowering Lp(a) by roughly 70% with pelacarsen did not reduce major cardiovascular events over 4.7 years in about 8300 people with established cardiovascular disease and Lp(a) at least 70 mg/dL, including those at least 90 mg/dL and in subgroups by LDL-C and hsCRP. The upper end of benefit compatible with the result is about a 10% to 13% relative reduction. It cannot say anything direct about a man without CVD at 30 mg/dL: such people were not enrolled, and his level is far below the entry threshold. Its main relevance to him is negative: it removes the one trial that could have shown that lowering Lp(a) itself prevents events, and it weakens the inference "Lp(a) causes risk, therefore lowering it helps".

---

## Study 2: EPIC-Norfolk one-time screening ✔

### A. Facts checked by code or registry

- Publication status: Eur Heart J 2025;46(39):3875-3884, published. PubMed `CommentsCorrections`: none (no erratum, retraction, EoC). elink comments: none. The full text names an editorial comment (Rocha, doi 10.1093/eurheartj/ehaf396), which is not linked in PubMed.
- Design: prospective population cohort, secondary analysis; PubMed type "Validation Study". Recruitment 1993 to 1997, data through 31 March 2016.
- Registration: "Pre-registered Clinical Trial Number None supplied." No protocol registration for this analysis.
- Sample size: 17 087 (discussion says 17 078 once; internal inconsistency). 3249 first MACE.
- Follow-up: median 20.5 (IQR 19.6 to 21.5) years.
- Funding: "All authors declare no funding for this contribution." Several authors report industry ties (see C).

### B. Checklist with quotes

- Population: "recruited men and women aged 40–79 through general practices in Norfolk, UK, between 1993 and 1997"; primary prevention (no prior MACE); mean age 59.0; 7342 men. Limitation stated: "the EPIC-Norfolk cohort primarily consists of men and women of white descent". Match: good on sex (men analysed separately), primary prevention, European; age somewhat older; era 1990s.
- Unit and assay: "The Lp(a) concentrations were assessed using an isoform-independent immunoturbidimetric assay" (Denka Seiken); reported in mg/dL. Cohort distribution: "Baseline plasma levels of LDL cholesterol, hsCRP, and Lp(a) were 4.0 ± 1.0 mmol/L, 1.5 (0.7–3.2) mg/L, and 11 (6–27) mg/dL, respectively."
- Exposure measured once: "had each biomarker evaluated once at study entry".
- Adjustment set: "the second model included additional adjustments for diabetes mellitus, systolic blood pressure, current smoking, and the presence of the other two biomarkers". Not adjusted for BMI, HDL-C, family history, education, or statin initiation: "We also lack data on statin initiation during follow-up."
- Where 30 mg/dL falls: Lp(a) quintile limits "Range of plasma levels, mg/dL <6 6 to <9 9 to <16 16 to <36 ≥36". So 30 mg/dL is in quintile 4 and 10 mg/dL in quintile 3.
- Hazard ratios by Lp(a) quintile, multivariable, all participants: "1.0 (reference) 0.88 (0.78, 0.99) 1.00 (0.90, 1.12) 0.97 (0.87, 1.09) 1.19 (1.07, 1.33)". Men only, quintiles 2 to 5: "0.87 (0.74, 1.02) 1.01 (0.87, 1.18) 1.05 (0.90, 1.22) 1.26 (1.09, 1.46)". Note: sex-specific quintile cut-offs were used in this table and the men's cut-offs are not in the text read, so the men's quintile 4 is approximately, not exactly, 16 to 36 mg/dL. Top vs bottom by sex: "the HR was 1.13 (95% CI: 0.96–1.32) in women and 1.26 (95% CI: 1.09–1.46) in men".
- Absolute risks: crude 20-year MACE proportions: "including 1755 events in the 9745 (18.0%) female participants and 1494 events in the 7342 (20.3%) male participants". Per Lp(a) quintile (Table 2): 596/3419 (17.4%), 547/3416 (16.0%), 652/3419 (19.1%), 694/3417 (20.3%), 760/3416 (22.2%), crude, not age-standardised (computed from table counts).
- For comparison within the same model, LDL-C top vs bottom quintile HR 1.78 (1.57 to 2.00), larger than Lp(a). The authors themselves: "a single random blood measure of hsCRP provided long-term risk estimates comparable with that of LDL cholesterol and greater than that of Lp(a)".
- Pre-specified vs post hoc: no registered protocol; the analysis is framed as replication of the WHS paper. No discrimination statistic (c-statistic, NRI) was reported, although the discussion speaks of "risk discrimination".

### C. Judgement items (listed, not rated)

- Risk of bias: single baseline measurement (regression dilution, biases toward null); limited adjustment set; no statin data during follow-up; residual confounding possible; outcome ascertainment by hospital records and death registry (reasonably complete in UK NHS).
- Conflicts of interest: "G.K.H. has a part-time employment at Novo Nordisk."; other authors report Novartis (maker of pelacarsen), Amgen, IONIS, Novo Nordisk fees; two are cofounders of Lipid Tools; P.M.R. extensive industry consulting.
- Publication / spin: the conclusion goes beyond the data: "we believe the time has come for universal screening of these three biomarkers in primary as well as secondary prevention". The data show associations, not that screening improves outcomes; no discrimination or clinical-utility analysis was performed. The Lp(a) association was the weakest of the three and non-monotonic below quintile 5.
- Applicability: closest of the four to the person (European, men included, primary prevention, mass units, isoform-independent assay). Older recruitment era and older mean age.

### Verdict

EPIC-Norfolk is the most applicable study and the only one read in full. It can say that, in European men and women without CVD, Lp(a) at or above about 36 mg/dL (the top fifth) was associated with roughly 20% higher 20-year MACE hazard (about 26% in men), after basic adjustment. It also shows that values in the 16 to 36 mg/dL band (where 30 mg/dL lies) carried no detectable excess hazard versus the lowest fifth (HR 0.97, 0.87 to 1.09; men 1.05, 0.90 to 1.22). It cannot say whether a measured 30 mg/dL changes this person's predicted risk beyond standard factors (no discrimination statistics), cannot resolve his 10 vs 30 discrepancy, and is silent on treatment.

---

## Study 3: Women's Health Study, 30-year risk by thresholds ◐

### A. Facts checked by code or registry

- Publication status: JAMA Cardiol 2026;11(2):175-185, published online 7 Jan 2026. PubMed `CommentsCorrections`: none. elink comments: none. PMC link type is `pubmed_pmc_embargo`: full text not yet released.
- Design: prospective cohort (secondary analysis of a former trial cohort, WHS), plus genetic analysis (LPA rs3798220).
- Registration: none reported in the material read.
- Sample size: 27 748 with Lp(a); 23 279 genotyped. 3707 major CV events.
- Follow-up: median 27.8 years (1993 to 2023).
- Funding: NIH/NHLBI and NCI grants; Independent Research Fund Denmark.

### B. Checklist with quotes

- Population: "This cohort study was conducted among female health professionals participating in the Women’s Health Study"; "Women without cardiovascular disease, cancer, and other major chronic illnesses had blood samples taken at baseline." Age: "(median [IQR] age, 53 [49-60] years)". Follow-up: "median (IQR) follow-up period of 27.8 (22.8-29.4) years". Match: primary prevention and age match; **sex does not match (women only)**; US, not European (genetic analysis restricted to European ancestry).
- Unit and assay: thresholds given in mg/dL; the assay and its isoform sensitivity were not in the text available (methods under embargo).
- Exposure measured once: "baseline" sample only (per abstract).
- Adjustment set: "Age- and multivariable-adjusted cause-specific Cox models were used"; covariates not listed in the text available.
- Main finding relevant to 30 mg/dL: "lipoprotein(a) levels above 30 mg/dL or the 75th percentile (31 mg/dL) were associated with increased 30-year risk of major cardiovascular events and coronary heart disease". Key points: "Only levels greater than 120 mg/dL or above the 99th percentile were associated with increased risk of ischemic stroke and cardiovascular death." The hazard ratio for the 30 to 50 mg/dL band was not in the text available; only the extreme categories were reported in the abstract (above 120 vs below 10 mg/dL: MACE HR 1.54, 1.24 to 1.92).
- Absolute risks: not in the abstract.
- Pre-specified vs post hoc: "The hypothesis was formulated after collection of the data."

### C. Judgement items (listed, not rated)

- Risk of bias: post hoc analysis of an existing cohort with many thresholds and percentiles examined (multiplicity); single baseline measurement; health-professional cohort; adjustment set not seen.
- Conflicts of interest: "Dr Chasman reported a patent for LPA polymorphism (rs3798220) and aspirin use for CVD prevention, with royalties paid from Quest Diagnostics." P.M.R. reports personal fees from Novartis and others; disclosed as outside the submitted work. "The funders had no role in the design and conduct of the study".
- Publication / spin: conclusion "Screening for elevated lipoprotein(a) in the general population may be warranted." while the stroke and CV death associations appeared only above 120 mg/dL. Same senior author and team as EPIC paper (Ridker, Nordestgaard, Kraaijenhof), so EPIC is not an independent replication team.
- Applicability: indirect by sex and country; full methods unseen.

### Verdict

WHS can say that in middle-aged US women without CVD, Lp(a) above 30 mg/dL was associated with somewhat higher 30-year risk of major CV events and coronary disease, and that clearly elevated risk for stroke and CV death appeared only at very high values (above 120 mg/dL). It cannot speak directly to a man, the size of the excess at exactly 30 to 50 mg/dL was not visible in the text available, the hypothesis was post hoc, and threshold-hunting across many cut-offs inflates the chance that "30 mg/dL" is a data-driven boundary. It says nothing about treatment.

---

## Study 4: Tel Aviv primary-prevention ambulatory cohort ◐

### A. Facts checked by code or registry

- Publication status: Clin Res Cardiol 2026;115(2):357-365, epub 16 Dec 2025. PubMed `CommentsCorrections`: none. elink comments: none. Not in PMC; Europe PMC: subscription required.
- Design: "A retrospective cohort of adults with available Lp(a) measurement, taken during a screening program (2008-2024) in a tertiary care center."
- Registration: none reported in the abstract.
- Sample size and follow-up: "3052 people were included with a median (IQR) follow-up of 6.4 (3.5-12) years." Number of events not in the abstract.
- Funding: not stated in the abstract. Conflicts: "We declare no known conflict of interests to any of the contributing authors." Declares ChatGPT used for language editing.

### B. Checklist with quotes

- Population: Israeli tertiary-centre screening programme, "mostly healthy" (abstract); 2778 without cardiovascular comorbidities. Age and sex distribution not in the abstract. Match: primary-prevention majority; not European; selection into a screening programme where Lp(a) was ordered (indication bias possible).
- Unit and assay: mg/dL; assay not stated in the abstract.
- Exposure measured once: implied (one available measurement); not explicit.
- Threshold: "Lp(a) threshold of 50 mg/dL was identified as a risk inflection point."; for those without comorbidities, "it was 48.4 mg/dL in those without (n = 2778)".
- Effect: "High Lp(a) (> 50 mg/dL) was associated with increased MACE risk, independent of clinical data (HR 1.55, 95% CI 1.10-2.17, p = 0.011)". Adjustment set: "clinical and laboratory covariates" (details not available).
- Absolute risks: not in the abstract.
- Pre-specified vs post hoc: threshold derived from the same data (spline) and then "validated" in Cox models on the same cohort; no external validation in the abstract.

### C. Judgement items (listed, not rated)

- Risk of bias: retrospective single-centre data; selection into testing; data-derived cut-off tested on the same data (optimism); wide CI.
- Conflicts of interest: none declared; funding not seen.
- Publication / spin: "Lp(a) showed a strong predictive utility for cardiovascular events." is stronger than an HR of 1.55 with CI 1.10 to 2.17 supports; claims of improved SCORE2/PCE performance in "high-risk patients" have no numbers in the abstract.
- Applicability: modest; non-European, unknown age/sex mix; the person (30 mg/dL) is below the identified threshold.

### Verdict

This cohort can say that, in a tertiary-centre screening population, Lp(a) above about 50 mg/dL was associated with higher MACE over about six years, and that below that level the spline did not show a clear rise. For this person at 30 mg/dL it is, if anything, reassuring, but the cut-off was found and tested in the same data, the setting is selected and non-European, and only the abstract was read. It says nothing about treatment.

---

## Guidelines

**ESC/EAS 2025 focused update (40878289).** Not read. The PubMed record has no abstract; the article is not in PMC; the publisher page answered with a bot check, which was not bypassed. PubMed links an erratum (quote: "Erratum in Eur Heart J. 2026 Feb 11;47(6):697. doi: 10.1093/eurheartj/ehaf1036."), whose content was not read. Its Lp(a) thresholds could therefore not be verified here. From background knowledge only (unverified, to be checked against the text): ESC/EAS documents since 2019 to 2022 advise measuring Lp(a) at least once in adulthood and treat about 50 mg/dL (about 105 nmol/L) as the level above which Lp(a) is a risk-enhancing factor, with 30 to 50 mg/dL as a grey zone. If that holds, 30 mg/dL would sit at the lower edge of the grey zone and 10 mg/dL clearly below it.

**DEGAM S3 053-024 v2.3.** Not read; the description (no routine measurement; ERFC c-statistic gain 0.0016; search update without further hits; dissent by DGK, DGIM, DDG, DHL, DGSP, DGPR favouring one-time measurement) is taken from the request.

### Do studies 1 to 4 support or contradict the DEGAM position?

*Prediction (does a measured Lp(a) add to risk estimation?).* Studies 2 to 4 show that **high** Lp(a) is associated with higher risk (relative hazards about 1.2 to 1.6, mostly in the top fifth or above 50 mg/dL). None of the parts read reports a discrimination gain (c-statistic, NRI) that would contradict the ERFC finding of a negligible c-statistic gain; Tel Aviv claims improved score performance only in high-risk patients, without numbers in the abstract. An association of this size in a minority of people is compatible with both positions: it explains why the ERFC population-level gain is tiny (DEGAM) and why the societies argue for identifying the few with very high values (dissent). So, for prediction, studies 2 to 4 do not contradict DEGAM's evidence base; they add relative-risk data, not discrimination data. Timing: EPIC (accepted March 2025) predates the August 2025 adoption; WHS (January 2026), Tel Aviv (December 2025) and HORIZON (November 2026) appeared after it, so the "no further hits" statement could not have covered them.

*Treatment benefit (does knowing Lp(a) lead to a treatment that helps?).* HORIZON, the first outcome trial of a selective Lp(a)-lowering drug, was null. That supports the DEGAM argument that measuring Lp(a) has, at present, no proven Lp(a)-specific therapeutic consequence, and it weakens the dissenting societies' argument insofar as it rested on expected Lp(a)-lowering therapies (EPIC and Tel Aviv explicitly cite "emerging" therapies as a rationale). It does not settle the dissent's other argument, that a high Lp(a) can shift a person's overall risk category and thereby other preventive decisions; none of the four studies tested that strategy.

---

## Overall answer

### Sub-question 1: Does an Lp(a) of 30 mg/dL raise this man's cardiovascular risk?

Evidence: EPIC-Norfolk (most applicable) found no detectable excess hazard in the 16 to 36 mg/dL band (HR 0.97; men 1.05, CI 0.90 to 1.22), with excess appearing only from about 36 mg/dL. WHS (women, abstract only, post hoc) found increased risk above 30 mg/dL for MACE and coronary disease. Tel Aviv placed the inflection near 50 mg/dL. The earlier value of 10 mg/dL would be in the low-risk range in all three. LDL-C showed a larger association than Lp(a) in the same EPIC model.

Certainty (GRADE): **low** that Lp(a) at 30 mg/dL is associated with any meaningful increase in his risk; the best estimate from the most applicable study is "little or no increase". Reasons: observational cohorts (start low); inconsistency in where the threshold lies (30 vs 36 vs 50 mg/dL); indirectness (WHS women only, Tel Aviv non-European and selected); imprecision around the 30 mg/dL band; single baseline measurement in every study; and his own two discordant values, which no study addresses. For **high** Lp(a) (roughly above 50 mg/dL, or the top fifth) being associated with higher risk, the certainty from these studies is **moderate** (consistent direction across three cohorts, plausible dose-response, genetic support mentioned in WHS), but that level does not describe this person.

### Sub-question 2: Does any treatment that lowers Lp(a) help?

Evidence: one randomised outcome trial, Lp(a)HORIZON, in secondary prevention with Lp(a) at least 70 mg/dL: no reduction in MACE (HR 1.02, 0.90 to 1.15) despite about 70% Lp(a) lowering, no benefit at at least 90 mg/dL, in on-treatment or landmark analyses, or in subgroups. No trial in primary prevention or at Lp(a) near 30 mg/dL was among the studies.

Certainty (GRADE):
- For the trial's own population (established CVD, Lp(a) at least 70 mg/dL, pelacarsen, about 5 years): **high** certainty that pelacarsen does not reduce major cardiovascular events by a clinically important amount (randomised, large, adjudicated, CI excludes reductions larger than about 10%), provisional because only the abstracts and registry were read and risk-of-bias domains could not be checked.
- For this person (no CVD, Lp(a) 10 to 30 mg/dL): **very low** certainty for any benefit of lowering Lp(a) itself. There is no direct trial evidence; the only outcome trial is null and very indirect (population, Lp(a) level, drug). Other Lp(a)-lowering agents still under study are not covered by these sources.

### Limits of this appraisal

- Full text read only for EPIC-Norfolk. HORIZON, the NEJM Evidence paper, Tel Aviv and the ESC/EAS 2025 update are subscription-only or behind a bot check; WHS full text is under PMC embargo. None was bypassed.
- CT.gov version history for NCT04023552 returned HTTP 403, so retrospective changes to the registered primary outcomes could not be checked.
- DEGAM guideline text was not read; its content is as stated in the request.
- Supplementary tables (EPIC Table S1 to S4, including sex-specific quintile cut-offs) were not read.

### Files

- Sources: `43001734_HORIZON_abstract.txt`, `42998055_HORIZON_NEJMEvid_abstract.txt`, `NCT04023552_ctgov_current.txt`, `40167249_EPIC_PMC_fulltext.txt`, `40167249_EPIC_abstract.txt`, `41499112_WHS_PMC.txt`, `41499112_WHS_abstract.txt`, `41400669_TelAviv_abstract.txt`, `40878289_ESC_EAS_2025_pubmed_record.txt`; raw downloads in `raw/`.
- `quotes.json`, `check_quotes.py`, `check_result.txt` (52 of 52 pass).
