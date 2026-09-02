# Route-decision Option A falsifier — frozen 2026-08-26 history

This report measures a frozen HISTORY, not a live dispatch stream. No dispatch has been witnessed since the freeze. If the applicable mappings eventually pass, the claim is **will hold when dispatch resumes**, never “holds live.”

- Rows: **619**
- Source SHA-256: `0b8f310f46c909246b729b7561c56d6c6880dc8bfffababceea88fdd6b126711`
- Selected-field fixture SHA-256: `1ab12f95f4cbb0202565c1ff86a7cd603a04ca010b9ed7c8093d878776798a1c`
- Provisional vindication: **PASS**
- Diagnostic admissions: **619 accepted, 0 refused**
- Negative admission mutations: **7/7 refused as required**

## Applicable mapping results

| Dimension | Result | Distinct numeric | Witnessed coverage | Redundant with | Ordering changed |
|---|---:|---:|---:|---|---:|
| `novelty` | PASS | 11 | 100.0% | none | 615 |
| `evidence_density` | PASS | 2 | 100.0% | none | 527 |
| `actionability` | PASS | 3 | 100.0% | none | 619 |
| `duplicate_pressure` | PASS | 6 | 100.0% | none | 611 |
| `operator_cost` | PASS | 3 | 100.0% | none | 619 |

The complete per-state counts and percentages, witnessed and emitted modes, distributions, boundary saturation, pairwise correlations/equality checks, nominal weights, conditional leave-one-out ordering sensitivity, and refusal messages are in the adjacent JSON report. `clamp_count` is explicitly absent because the recovered scorer does not expose pre-clamp values; it is not fabricated from boundary values.

## Decision

The frozen history provisionally vindicates testing another source. It does not establish live delivery, calibration, freshness ownership, or the 13-dimension scheme estate-wide.

No service, hook, timer, binding registration, live consumer, DOI scalar, Reins route, store, dashboard, or activation was added or changed.

## §4 constraint posture

| # | Status | Implemented posture |
|---:|---|---|
| 1–5 | SATISFIED | Recovered 13-field contract and scorer; one deterministic, declarative, local `cc_task` emitter. |
| 6 | SATISFIED | The injected AIR seal refuses before clocks, counts, digest, or scoring are used. |
| 7–9 | SATISFIED / NOT-APPLICABLE | No Reins/publication-ladder route, DOI `I`, cost placement, or screenspace composition. |
| 10–13 | SATISFIED | AIR default-deny, non-authorizing score/receipt, no alert-channel claim, authority capped as derived. |
| 14 | CONFLICT—LIVE WITHHELD | Typed missingness is carried, but no source-specific projection policy was adjudicated. |
| 15 | SATISFIED | JSON report carries evidence states, fields, reasons, provenance digests, and values. |
| 16 | CONFLICT—LIVE WITHHELD | Timestamps are retained; no TTL owner/budget or freshness-valid activation is claimed. |
| 17–24 | SATISFIED | Versioned parameters/contracts; dimension falsifier; no hidden preference gate, tenant machinery, new substrate, rendering, or personification. |

The two conflicts narrow the result to frozen-history measurement and diagnostic admission. They are not treated as permission for live release.
