# Appraisal: a statin that makes a person tired (2026-11-20)

Question, as a patient asks it: _A statin makes me tired. Is it the statin, does
coenzyme Q10 help, and what else lowers LDL if I cannot take one?_

Not medical advice. This says how far each study can answer the question, not
what anyone should do. Status checked in PubMed on 2026-11-20, with a known
retracted paper (PMID 32450107) as positive control. Registrations read from
ClinicalTrials.gov (API v2) and from the full texts in Europe PMC.

## Quality gate

Revised on 2026-11-21 after a review by a clinical pharmacologist. His points: what a study can say lies in its confidence interval, not
in its number of participants; very small studies still raise the suspicion of
chance, bias or worse; and formal criteria such as "peer reviewed" and "not
retracted" are too coarse, because they miss the weaknesses a paper does not
mention. The fixed rule of at least 1,000 participants is gone. A study is set
against a guideline only when it passes three layers (`gate()` in
`health_graph/evidence.py`):

1. **Form.** Peer reviewed, not retracted, a randomised trial or meta-analysis
   registered in advance, or a prospective cohort with a registered,
   prespecified analysis. Necessary, never enough.
2. **Precision, after GRADE**
   ([Guyatt et al., J Clin Epidemiol 2011](https://doi.org/10.1016/j.jclinepi.2011.01.012)).
   The 95% CI of the result that bears on the guideline must not hold both no
   effect and an appreciable one (a relative change of 25%, or the minimal
   important difference: 1 point on a 10-point pain scale,
   [IMMPACT](https://pubmed.ncbi.nlm.nih.gov/18055266/)). The evidence must
   reach the optimal information size, by GRADE's rule of thumb 400 events or
   800 participants (the 400 participants of the 2011 paper were
   [corrected in 2021](https://usblog.gradeworkinggroup.org/2021/08/correction-to-guidance-for-assessing.html)).
   Pooled trials of fewer than 50 people hold a result back: such trials report
   effects about 48% larger than trials of 1,000 or more
   ([Dechartres et al., BMJ 2013](https://doi.org/10.1136/bmj.f2304)).
3. **A person's reading.** Risk of bias judged domain by domain with RoB 2,
   ROBINS-E or AMSTAR 2, by a person who read the full text and the protocol.
   Until then a study through layers 1 and 2 is linked provisionally and shown as
   such. A model's rating does not count: in a comparison of three models on one
   registered, peer-reviewed trial, all three first called it sound and found
   its impossible figures only when probed step by step
   ([Niedenthal and Uehleke, Z Phytother 2026](https://doi.org/10.1055/a-2683-2290),
   abstract read).

| Study | Design | Result the gate judged | Gate |
| --- | --- | --- | --- |
| [CTT, Lancet 2026](https://doi.org/10.1016/S0140-6736(25)01578-8) | IPD meta-analysis, 123,940 | liver transaminases RR 1.41 (1.26 to 1.57), 1,339 events | provisional, risk of bias not yet judged |
| [CLEAR Outcomes, NEJM 2023](https://doi.org/10.1056/NEJMoa2215024) | RCT, 13,970, NCT02993406 | MACE HR 0.87 (0.79 to 0.96), 1,746 events | provisional, risk of bias not yet judged |
| [SAMSON, NEJM 2020 (letter)](https://doi.org/10.1056/NEJMc2031173) | randomised n-of-1, 60, NCT02668016 | not read (letter) | estimate not read; 60 participants, fewer than 800 |
| [Qu, J Am Heart Assoc 2018](https://doi.org/10.1161/JAHA.118.009835) | meta-analysis of 12 trials, 575 | muscle pain WMD -1.60 (-1.75 to -1.44) | not registered; 575 participants, fewer than 800 |
| [Kennedy, Atherosclerosis 2020](https://doi.org/10.1016/j.atherosclerosis.2020.03.006) | meta-analysis of 7 trials, 321 | muscle pain WMD -0.42 (-1.47 to 0.62) | registration not found; imprecise; 321 participants; trials of 37 people |
| [Kovacic, J Nutr Sci 2025](https://doi.org/10.1017/jns.2025.10043) | meta-analysis of 7 trials, 389, PROSPERO | muscle pain WMD -0.96 (-1.88 to -0.03) | 389 participants, fewer than 800; trials of 35 people |

Qu 2018 shows why precision alone is not enough either: twelve small trials
(575 people in all) pooled with a fixed effect give a narrow interval. Size shrinks
random error, not bias.

## What it means for the question

- **Is it the statin?** In blinded trials (CTT 2026) tiredness is not among the
  effects that differ from placebo. SAMSON tested it one person at a time: about
  90% of the symptom burden on the statin came on placebo as well. Both are
  averages; a pause and re-challenge, ideally blinded, answers it for one person.
- **Does Q10 help?** Three meta-analyses of largely the same small, short trials
  disagree (benefit, no benefit, a small benefit with an interval reaching almost
  zero). All measured muscle pain, none general tiredness. Certainty: low to very
  low. Statins do lower Q10 in the blood (Qu, Eur J Med Res 2018), so the idea is
  plausible, not shown.
- **What else lowers LDL?** Bempedoic acid has an outcome trial in
  statin-intolerant people at high risk (CLEAR Outcomes). Ezetimibe and PCSK9
  inhibitors are the other options a doctor will weigh.

## Related sources already in the graph

- LDL causes atherosclerosis: EAS consensus 2017 (`eas-2017-ldl`).
- HDL is not causal: Voight et al., Lancet 2012 (mendelian randomisation).
- ApoB counts every particle that can build plaque, LDL, remnants and Lp(a), and
  is in the ESC/EAS 2025 lipid guideline (`esc-eas-2025-lipids`).
