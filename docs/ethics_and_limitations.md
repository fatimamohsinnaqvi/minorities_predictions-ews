# Ethics and Limitations

**Project:** Minorities Early-Warning System — Lahore
**Status:** Living document — to be revisited every phase
**Last updated:** 2026-06-22

---

This is the document I would want to read first if I were a member of one
of the communities this system is meant to protect. It states honestly
what the system can and cannot do, what it might get wrong, and how the
project guards against the worst outcomes.

## What this system is

A research prototype that takes Emergency-15 case records, identifies the
subset relating to minority communities, and predicts the likelihood of
new minority-targeted incidents at a (police-station × time-window) level.
Output is intended to inform **proactive police presence and resource
allocation**, not individual-level enforcement.

## What this system is not

- **Not a tool for identifying individual perpetrators or victims.** The
  outputs are place-time risk scores, not person-level scores.
- **Not a ground-truth measure of minority safety.** It measures
  *reports*, which under-represent communities with low trust in police.
- **Not a substitute for community engagement.** A risk score is an input
  to a human decision, never a replacement for one.

## The five risks I am most worried about

### 1. Under-reporting bias

Communities with lower trust in police institutions report fewer
incidents. The system, trained on reports, will systematically under-flag
those very communities. A naive reading of the dashboard ("Hindu cases
are low → Hindu communities are safe") **inverts the truth**.

**Mitigation in this project:**
- The Research Design Report's framing is followed: model output is paired
  with reported-rate context in every dashboard view.
- The policy brief explicitly states this caveat (page 2 §5).
- The final report dedicates a full sub-section to under-reporting bias.

### 2. Feedback loop ("predictive policing" failure mode)

If police are deployed to areas the model flags, those areas will generate
more incident reports (more eyes, more interventions), which trains the
next iteration of the model to flag them harder. Documented failure mode
of pre-emptive policing systems globally.

**Mitigation:**
- The model is retrained on a fixed cadence, not continuously.
- The dashboard does **not** include "deployment outcome" as a feature.
- The recommendation to PSCA explicitly says: pair model deployment with
  baseline-rate measurement so feedback loops can be detected.

### 3. Aggregation as protection — but also as obscuring

The dashboard aggregates to police-station-week. This protects individual
victims from re-identification, but also means a viewer cannot see whether
one Ahmadi family is being repeatedly targeted at the same address.
Operational handling of that pattern must still happen via the existing
VCM and FIR processes.

**Mitigation:**
- Detail-row sample case descriptions in the dashboard are randomly
  selected and length-truncated.
- No row that could re-identify an individual is exported into the
  policy brief or report.

### 4. Misuse: scores treated as evidence

A risk score is a hypothesis, not evidence. If a senior officer interprets
"this PS is high risk for next week" as "the people who live here are
high risk" — the system has been misused.

**Mitigation:**
- Every dashboard view carries a one-line caveat (`"Risk = predicted
  reports, not predicted offenders"`).
- The model card explicitly states the prediction unit is (place, time),
  not (person).
- The recommendation document spells out: any operational action
  triggered by the model requires human review of the case-level data.

### 5. Selection of what counts as "minority-targeted"

We picked six religious sub-categories and a list of community-name
keywords. That choice has consequences. Anti-Shia incidents that don't
name a sect, gendered minority violence, sectarian disputes between
sub-groups — these are all under-captured by the filter.

**Mitigation:**
- The strict label (`is_minority_targeted`) is conservative; broader
  views are available in the dashboard.
- The data dictionary lists exact filter logic so others can extend it.
- The final report names what the filter misses.

## Access control (when the project moves beyond research)

The current artifact runs on localhost without authentication. **Before
this dashboard is shared with anyone outside the immediate team, the
following must be in place:**

1. Login required. PSCA-provided credentials, not project-managed.
2. Every page view written to an audit log with `user_id`, `timestamp`,
   `view`, `filters`.
3. Role-based access — analysts see PS-level views; commanders see
   district roll-ups; minority-community reps see aggregate only.
4. A public-facing version, if there is one, never shows individual
   incident descriptions.

These controls are deferred from W11-12 to a hypothetical "deployment
phase" and are not part of the internship deliverable. They are recorded
here so a future deployer cannot claim they were not warned.

## What I will *not* build

- A face-or-name recognition layer over the dashboard.
- A real-time push alert that fires without human review.
- A scoring mechanism for individual people in the call records.
- A public-internet version of the dashboard.

## Who should review this document

- The internship supervisor (always).
- At least one representative of a minority civil-society organization
  (before final submission).
- A technically literate human-rights observer (recommended).

If reviewers raise concerns not addressed here, this document is updated
**before** the next phase ships.

## References

- Mitchell et al., "Model Cards for Model Reporting" (2019)
- Lum and Isaac, "To predict and serve?" Significance (2016) — feedback
  loops in predictive policing
- Reporting bias in minority-incident data — HRCP Annual Reports on
  Minorities in Pakistan
