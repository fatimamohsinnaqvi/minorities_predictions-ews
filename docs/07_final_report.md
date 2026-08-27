# 07 — Final Report (10–15 pages)

**Phase:** W11–12 deliverable
**Status:** Outline + skeleton; populated as phases complete
**Last updated:** 2026-06-22

> The final report is the academic / professional writeup of the entire
> project, intended for the internship supervisor and a knowledgeable
> non-specialist reader. It mirrors the style of the parent Research
> Design Report — clear prose, numbered sections, embedded figures.
>
> This file is the outline. Fill in each section's body as the
> corresponding phase completes. Tables of contents and references
> at the end will be generated last.

---

## Title
A Predictive Early-Warning System for Minority-Targeted Crime in Lahore:
Construction, Evaluation, and Operational Guidance

## Abstract (200 words)
- One-sentence problem statement
- One sentence on data (4,110 incidents Punjab-wide, 928 Lahore)
- One sentence on method
- Top-line result (precision @ 20, ROC AUC)
- Key recommendation

## 1. Introduction (1–1.5 pages)
- Why minority-targeted crime is the focus
- The Punjab Safe Cities / VCM operational context (refer to Research
  Design page 1)
- Limitation of reactive systems
- Statement of research question (from Research Design §2)

## 2. Scope and Research Question (0.5–1 page)
- Geographic and temporal bounds
- Definition of "risk event" (carried over from Research Design)
- What is and is not in scope (one bullet list each)

## 3. Data (2 pages)
- Source: Emergency-15 / `response_time`
- Filter rule and rationale ([01_data_pipeline.md](01_data_pipeline.md))
- Working table: `minority_incidents` ([00_data_dictionary.md](00_data_dictionary.md))
- Data quality issues — be honest
- Embed Figure 1 (cases per month, stacked) and Table 1 (top districts)

## 4. Exploratory Analysis (1.5–2 pages)
- Temporal patterns including the Dec 25 2025 spike
- Geographic concentration — Lahore + four secondary districts
- Community mix — Christian dominance in description, large
  unspecified base
- Police-station concentration — Nisthar Colony, Chung, Factory Area
- Embed Figures 2 and 4

## 5. Feature Engineering (1.5 pages)
- The six families (sentiment, misinformation, political calendar,
  religious calendar, prior incident density, responsiveness)
- Which were operational at submission time, which were placeholders
- Cite [03_feature_engineering.md](03_feature_engineering.md)

## 6. Modeling (2 pages)
- Models tried (LR → RF → optional XGB)
- Train / test split with rationale (temporal, no shuffle)
- Metrics chosen (precision@k, recall@k, ROC AUC, PR AUC, calibration)
- Headline result(s)
- **Per-community performance breakdown** — the most important sub-section
- Failure modes (worked examples of misses)
- Cite [04_modeling_methodology.md](04_modeling_methodology.md)

## 7. Dashboard (1 page)
- Layers, filters, intended user
- Screenshots (2–3) from `outputs/screenshots/`
- Cite [05_dashboard_design.md](05_dashboard_design.md)

## 8. Ethics and Limitations (1 page)
- Under-reporting bias
- Selection bias in the label
- Risk of misuse
- Safeguards built into the system (access control, audit log, no
  individual-level outputs)
- Cite [ethics_and_limitations.md](ethics_and_limitations.md)

## 9. Recommendations (0.5–1 page)
- Synthesis of the policy brief
- Three concrete next experiments / extensions

## 10. Conclusion (0.5 page)

## Appendices
- A. Data dictionary (carry over [00_data_dictionary.md](00_data_dictionary.md))
- B. Model card for the chosen model
- C. Reproducibility — exact commands to rebuild the project

## References (cited APA / numbered)
- Internal docs:
  - Research Design Report (parent folder)
  - Timeline (parent folder)
  - District Dataset and Data Dictionary (parent folder)
  - Each numbered docs/0*.md file
- External:
  - Mitchell et al., "Model Cards for Model Reporting", 2019
  - HRCP / South Asia Watch reports on minority incidents in Punjab
  - PSCA Annual Reports (where available)

---

## Drafting checklist
- [ ] All numbers cited with table/source
- [ ] All figures captioned with title / source / what to notice
- [ ] All claims that hint at policy direction have a `[caveat]` reference
- [ ] Run a Flesch-Kincaid pass; aim for grade-12-or-lower readability
- [ ] Spell-check the Urdu transliterations
- [ ] One review pass with a community-organization contact before submit
