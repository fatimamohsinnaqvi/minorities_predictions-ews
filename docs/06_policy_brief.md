# 06 — Policy Brief (2 pages)

**Phase:** W11–12 deliverable
**Status:** Outline + skeleton; final content depends on W7-8 model results
**Last updated:** 2026-06-22
**Audience:** Punjab Police senior leadership, Punjab Safe City Authority,
relevant minority-rights stakeholders.

> The final two-page brief lives in `outputs/policy_brief/`. This document
> is the working scaffold — section headings, claim shapes, and
> placeholders for results that depend on later phases.

---

## Page 1

### 1. The problem (one paragraph)

Between January 2024 and June 2026, **4,110 minority-related incidents**
were logged across Punjab via PSCA Emergency-15. Lahore alone accounts
for **928 of them — 22.6% of the provincial total**. The volume is
trending upward year-on-year (2024: 1,450 → 2025: 2,117 → 2026 YTD: 525).
Existing institutional response is **reactive**: a call comes in, force
is dispatched. There is no operational system that flags **rising risk
in a place × time window before an incident has happened**.

### 2. The opportunity

This project demonstrates that publicly available institutional data —
case nature, free-text descriptions, time, and place — already contain a
**measurable advance signal**. Pattern findings from the Research Design:
clusters of incidents arrive *together* in a single neighborhood; the
**December 25, 2025 nation-wide Christmas-day spike** showed five separate
districts logging Christian-targeted cases the same day; certain
police stations (e.g. **Nisthar Colony at 82 Lahore cases, 8.8% of the
city total**) repeat across months.

The predictive system built in this project takes those signals and
scores every PS-week in Punjab for the likelihood of a minority-targeted
incident in the next 7 days.

### 3. Top three early-warning indicators (model output — placeholder)

> Filled in after Phase 4 (modeling). Expected to include:

1. **Prior-incident density** — number of minority-related cases in the
   same police station in the prior 30 days. Strongest standalone
   predictor.
2. **Religious-calendar proximity** — days to the next major minority
   religious event (Christmas, Holi, Diwali, Easter, Eid-e-Milad).
3. **Sentiment / misinformation velocity** — rapid rise in negative
   social-media discussion of a community in the relevant area.

## Page 2

### 4. Recommendations

For **Punjab Safe City Authority / Punjab Police**:
- Stand up a **weekly risk-watch routine** using the top-N flagged PSes
  from the model. Allocate proactive patrol budget to those PSes.
- Pre-position force around the **calendar dates** the model identifies
  as high-risk — Christmas Day, Holi, Eid-e-Milad-un-Nabi, Muharram, etc.
- Set a **community-disaggregated dashboard target**: model performance
  must not be materially worse for any single minority community.

For **Information / Media authorities**:
- Treat viral minority-related misinformation as a measurable predictor.
  Build a simple monitoring desk for known patterns (church-land
  disputes, blasphemy allegations) — the model says these *precede*
  violence, not follow it.

For **PSCA Virtual Center for Minorities**:
- Continue logging incidents in detail. The free-text descriptions are
  the **single most valuable input** to this system — more so than the
  structured case-nature tag.
- Establish formal data-sharing with the early-warning system on a
  monthly cadence.

For **community organizations / civil society**:
- Engage with the development of the system; review of false positives
  protects the communities the system is meant to defend.

### 5. Caveats (must read)

- The system predicts **reports of incidents**, not incidents themselves.
  Communities that under-report will be **under-flagged**. Do not draw
  the conclusion that low-reporting areas are low-risk areas.
- The system is intended for **resource allocation and watch routines**,
  **not for individual targeting** of suspects or for any kind of
  pre-emptive enforcement against community members. Misuse of model
  scores for individual-level decisions is explicitly out of scope.
- All risk scores should be reviewed by a human analyst before any
  operational action.

### 6. What's next

- Pilot the dashboard with PSCA's command center for one quarter.
- Quarterly review of model fairness and accuracy with minority-community
  representatives.
- Open-source the methodology (without the underlying case data) so
  other provinces can adapt.

---

## Drafting notes (not part of the brief)

- Total length when typeset must fit two pages. Aim for ~1,200 words.
- One small chart on each page: monthly trend (page 1), per-community
  performance (page 2).
- Use [outputs/figures/heatmap_lahore.html](../outputs/figures/heatmap_lahore.html)
  in the live presentation, not the brief.
- Hand the final draft for review to minority-community contacts BEFORE
  submission. The ethics doc explains why.

## References

- Numbers in §1: [02_eda_findings.md](02_eda_findings.md), [`data/processed/eda_summary.json`](../data/processed/eda_summary.json)
- Top three indicators: pending [04_modeling_methodology.md](04_modeling_methodology.md) outputs
- Ethics: [ethics_and_limitations.md](ethics_and_limitations.md)
