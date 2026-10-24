#!/usr/bin/env python3
"""Evaluate the Option A falsifier over the frozen route-decision history."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hapax.spine.route_decision_topic_interest import (
    ADAPTER_VERSION,
    DIMENSIONS,
    PRODUCER_ID,
    PRODUCER_VERSION,
    AcceptanceReceipt,
    AdapterParameters,
    AdmissionRefusal,
    EmissionClocks,
    EmissionRefusal,
    FrozenRouteDecisionDatum,
    ProducerBinding,
    RouteDecisionEmission,
    SourceFrontier,
    admit_route_decision_topic_interest,
    emit_route_decision_topic_interest,
)
from hapax.spine.topic_interest_engine import PENALTY_WEIGHTS, POSITIVE_WEIGHTS

STATES = (
    "witnessed",
    "partial",
    "absent",
    "stale",
    "blocked",
    "known_zero",
    "not_applicable",
)
MEASURED_STATES = frozenset({"witnessed", "known_zero"})
APPLICABLE_MAPPINGS = (
    "novelty",
    "evidence_density",
    "actionability",
    "duplicate_pressure",
    "operator_cost",
)
ANALYSIS_AT = datetime(2026, 8, 28, tzinfo=UTC)


def _binding(emission: RouteDecisionEmission) -> ProducerBinding:
    receipt = emission.receipt
    return ProducerBinding(
        binding_name="route_decision_topic_interest_binding",
        allowed_source="cc_task",
        producer_id=PRODUCER_ID,
        producer_version=PRODUCER_VERSION,
        evidence_ref=receipt.evidence_ref,
        adapter_version=ADAPTER_VERSION,
        vector_digest=receipt.vector_digest,
        dimension_evidence=receipt.dimension_evidence,
    )


def _quantile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _distribution(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            key: None
            for key in (
                "minimum",
                "p05",
                "p25",
                "median",
                "p75",
                "p95",
                "maximum",
                "mean",
                "population_variance",
            )
        }
    return {
        "minimum": min(values),
        "p05": _quantile(values, 0.05),
        "p25": _quantile(values, 0.25),
        "median": statistics.median(values),
        "p75": _quantile(values, 0.75),
        "p95": _quantile(values, 0.95),
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "population_variance": statistics.pvariance(values),
    }


def _mode(values: list[Any]) -> tuple[Any | None, float | None]:
    if not values:
        return None, None
    encoded = [
        json.dumps(value, sort_keys=True, separators=(",", ":")) for value in values
    ]
    value, count = Counter(encoded).most_common(1)[0]
    return json.loads(value), count / len(encoded)


def _ranks(values: list[float], *, descending: bool = False) -> list[float]:
    ordered = sorted(range(len(values)), key=lambda i: values[i], reverse=descending)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        rank = (start + end - 1) / 2
        for index in ordered[start:end]:
            ranks[index] = rank
        start = end
    return ranks


def _spearman(left: list[float], right: list[float]) -> float | None:
    if len(left) < 2 or len(set(left)) < 2 or len(set(right)) < 2:
        return None
    a = _ranks(left)
    b = _ranks(right)
    mean_a = statistics.fmean(a)
    mean_b = statistics.fmean(b)
    numerator = sum((x - mean_a) * (y - mean_b) for x, y in zip(a, b, strict=True))
    denominator = math.sqrt(
        sum((x - mean_a) ** 2 for x in a) * sum((y - mean_b) ** 2 for y in b)
    )
    return numerator / denominator if denominator else None


def _source_signature(datum: FrozenRouteDecisionDatum, fields: tuple[str, ...]) -> Any:
    raw = datum.model_dump(mode="json")
    signature: dict[str, Any] = {}
    for field in fields:
        if field == "*_freshness_green":
            signature[field] = {
                key: raw[key]
                for key in (
                    "quota_freshness_green",
                    "registry_freshness_green",
                    "resource_freshness_green",
                )
            }
            continue
        cursor: Any = raw
        for part in field.split("."):
            cursor = cursor[part]
        signature[field] = cursor
    return signature


def _pairwise_reversal_fraction(base: list[float], alternate: list[float]) -> float:
    reversed_pairs = 0
    comparable = 0
    for left in range(len(base)):
        for right in range(left + 1, len(base)):
            base_delta = base[left] - base[right]
            alt_delta = alternate[left] - alternate[right]
            if base_delta == 0 or alt_delta == 0:
                continue
            comparable += 1
            reversed_pairs += (base_delta > 0) != (alt_delta > 0)
    return reversed_pairs / comparable if comparable else 0.0


def _sensitivity(vectors: list[Any], projection: str) -> dict[str, Any]:
    if projection == "positive_score":
        base = [vector.positive_score() for vector in vectors]
    else:
        base = [vector.total_score() for vector in vectors]
    base_ranks = _ranks(base, descending=True)
    top_count = math.ceil(len(base) * 0.10)
    base_top = set(sorted(range(len(base)), key=lambda i: (-base[i], i))[:top_count])
    report: dict[str, Any] = {}
    for dimension in DIMENSIONS:
        if projection == "positive_score":
            weight = POSITIVE_WEIGHTS.get(dimension, 0.0)
            alternate = [
                score - getattr(vector, dimension) * weight
                for score, vector in zip(base, vectors, strict=True)
            ]
        else:
            alternate = []
            for vector in vectors:
                positive = vector.positive_score() - getattr(
                    vector, dimension
                ) * POSITIVE_WEIGHTS.get(dimension, 0.0)
                penalty = vector.penalty_score() - getattr(
                    vector, dimension
                ) * PENALTY_WEIGHTS.get(dimension, 0.0)
                alternate.append(max(0.0, min(1.0, positive - 0.55 * penalty)))
        alternate_ranks = _ranks(alternate, descending=True)
        displacements = [
            abs(left - right)
            for left, right in zip(base_ranks, alternate_ranks, strict=True)
        ]
        alt_top = set(
            sorted(range(len(alternate)), key=lambda i: (-alternate[i], i))[:top_count]
        )
        report[dimension] = {
            "rows_with_rank_change": sum(value > 0 for value in displacements),
            "rank_change_fraction": sum(value > 0 for value in displacements)
            / len(base),
            "median_absolute_rank_displacement": statistics.median(displacements),
            "maximum_absolute_rank_displacement": max(displacements),
            "pairwise_order_reversal_fraction": _pairwise_reversal_fraction(
                base, alternate
            ),
            "top_10_percent_set_turnover": len(base_top - alt_top) / top_count,
        }
    return report


def _admission_mutations(
    emission: RouteDecisionEmission, datum: FrozenRouteDecisionDatum
) -> dict[str, str]:
    binding = _binding(emission)

    def refusal(name: str, call: Any) -> tuple[str, str]:
        try:
            call()
        except (AdmissionRefusal, EmissionRefusal) as error:
            return name, str(error)
        raise AssertionError(f"mutation {name} unexpectedly passed")

    states = tuple(
        item.model_copy(update={"state": "stale"})
        if item.dimension == "staleness"
        else item
        for item in emission.receipt.dimension_evidence
    )
    stale = emission.model_copy(
        update={
            "receipt": emission.receipt.model_copy(
                update={"dimension_evidence": states}
            )
        }
    )
    stale_binding = binding.model_copy(update={"dimension_evidence": states})
    mutations = dict(
        [
            refusal(
                "missing_producer",
                lambda: admit_route_decision_topic_interest(
                    emission,
                    binding=None,
                    accepted_at=ANALYSIS_AT,
                    append_acceptance=lambda _: True,
                ),
            ),
            refusal(
                "wrong_producer",
                lambda: admit_route_decision_topic_interest(
                    emission,
                    binding=binding.model_copy(update={"producer_id": "wrong"}),
                    accepted_at=ANALYSIS_AT,
                    append_acceptance=lambda _: True,
                ),
            ),
            refusal(
                "fabricated_vector",
                lambda: admit_route_decision_topic_interest(
                    emission.vector,
                    binding=binding,
                    accepted_at=ANALYSIS_AT,
                    append_acceptance=lambda _: True,
                ),
            ),
            refusal(
                "denied_input",
                lambda: emit_route_decision_topic_interest(
                    datum,
                    source_frontier=SourceFrontier(
                        frontier_ref="fixture:denied",
                        air_allowed=False,
                        air_evidence_ref="air:deny",
                        prior_same_task_count=0,
                        resource_state_refs_vary=False,
                    ),
                    adapter_version=ADAPTER_VERSION,
                    clocks=EmissionClocks(
                        analysis_at=ANALYSIS_AT, production_at=datum.created_at
                    ),
                    parameters=AdapterParameters(),
                ),
            ),
            refusal(
                "stale_source",
                lambda: admit_route_decision_topic_interest(
                    stale,
                    binding=stale_binding,
                    accepted_at=ANALYSIS_AT,
                    append_acceptance=lambda _: True,
                ),
            ),
            refusal(
                "digest_mismatch",
                lambda: admit_route_decision_topic_interest(
                    emission,
                    binding=binding.model_copy(update={"vector_digest": "0" * 64}),
                    accepted_at=ANALYSIS_AT,
                    append_acceptance=lambda _: True,
                ),
            ),
            refusal(
                "receipt_failure",
                lambda: admit_route_decision_topic_interest(
                    emission,
                    binding=binding,
                    accepted_at=ANALYSIS_AT,
                    append_acceptance=lambda _: False,
                ),
            ),
        ]
    )
    return mutations


def analyze(fixture: Path, manifest_path: Path) -> dict[str, Any]:
    rows = [json.loads(line) for line in fixture.read_text().splitlines()]
    manifest = json.loads(manifest_path.read_text())
    datums = [FrozenRouteDecisionDatum.model_validate(row) for row in rows]
    resource_state_refs_vary = (
        len({json.dumps(datum.resource_state_refs) for datum in datums}) > 1
    )
    prior_counts: Counter[str] = Counter()
    emissions: list[RouteDecisionEmission] = []
    accepted = 0
    for datum in datums:
        emission = emit_route_decision_topic_interest(
            datum,
            source_frontier=SourceFrontier(
                frontier_ref=f"fixture:{manifest['derived_sha256']}",
                air_allowed=True,
                air_evidence_ref="operator:option-a-selected-field-freeze",
                prior_same_task_count=prior_counts[datum.task_token],
                resource_state_refs_vary=resource_state_refs_vary,
            ),
            adapter_version=manifest["adapter_version"],
            clocks=EmissionClocks(
                analysis_at=ANALYSIS_AT, production_at=datum.created_at
            ),
            parameters=AdapterParameters(**manifest["parameters"]),
        )
        prior_counts[datum.task_token] += 1
        admit_route_decision_topic_interest(
            emission,
            binding=_binding(emission),
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda receipt: isinstance(receipt, AcceptanceReceipt),
        )
        accepted += 1
        emissions.append(emission)

    dimension_reports: dict[str, Any] = {}
    for dimension in DIMENSIONS:
        state_items = [
            next(
                item
                for item in emission.receipt.dimension_evidence
                if item.dimension == dimension
            )
            for emission in emissions
        ]
        counts = Counter(item.state for item in state_items)
        emitted = [getattr(emission.vector, dimension) for emission in emissions]
        measured_indexes = [
            index
            for index, item in enumerate(state_items)
            if item.state in MEASURED_STATES
        ]
        measured = [emitted[index] for index in measured_indexes]
        raw_values = [
            _source_signature(datums[index], state_items[index].source_fields)
            for index in measured_indexes
        ]
        raw_mode, raw_mode_share = _mode(raw_values)
        numeric_mode, numeric_mode_share = _mode(measured)
        dimension_reports[dimension] = {
            "total_rows": len(rows),
            "states": {
                state: {
                    "count": counts[state],
                    "percentage": 100 * counts[state] / len(rows),
                }
                for state in STATES
            },
            "distinct_witnessed_values": len(
                {json.dumps(value, sort_keys=True) for value in raw_values}
            ),
            "distinct_emitted_numeric_values": len(set(emitted)),
            "witnessed_mode_value": raw_mode,
            "witnessed_mode_share": raw_mode_share,
            "measured_numeric_mode_value": numeric_mode,
            "measured_numeric_mode_share": numeric_mode_share,
            "witnessed_numeric_distribution": _distribution(measured),
            "emitted_numeric_distribution_including_typed_absence_projection": _distribution(
                emitted
            ),
            "measured_share_exactly_zero": (
                sum(value == 0 for value in measured) / len(measured)
            )
            if measured
            else None,
            "measured_share_exactly_one": (
                sum(value == 1 for value in measured) / len(measured)
            )
            if measured
            else None,
            "saturation_count": sum(value in {0.0, 1.0} for value in measured),
            "clamp_count": None,
            "clamp_count_reason": "the recovered scorer does not expose pre-clamp values",
            "source_fields_responsible": sorted(
                {field for item in state_items for field in item.source_fields}
            ),
            "nominal_positive_weight": POSITIVE_WEIGHTS.get(dimension),
            "nominal_penalty_weight": PENALTY_WEIGHTS.get(dimension),
            "empirical_witnessed_coverage": len(measured) / len(rows),
        }

    pairwise: dict[str, Any] = {}
    for left in DIMENSIONS:
        for right in DIMENSIONS:
            left_values = [getattr(emission.vector, left) for emission in emissions]
            right_values = [getattr(emission.vector, right) for emission in emissions]
            left_states = [
                next(
                    item.state
                    for item in emission.receipt.dimension_evidence
                    if item.dimension == left
                )
                for emission in emissions
            ]
            right_states = [
                next(
                    item.state
                    for item in emission.receipt.dimension_evidence
                    if item.dimension == right
                )
                for emission in emissions
            ]
            shared = [
                index
                for index, (a, b) in enumerate(
                    zip(left_states, right_states, strict=True)
                )
                if a in MEASURED_STATES and b in MEASURED_STATES
            ]
            shared_left = [left_values[index] for index in shared]
            shared_right = [right_values[index] for index in shared]
            witnessed_rho = _spearman(shared_left, shared_right)
            included_rho = _spearman(left_values, right_values)
            pairwise[f"{left}|{right}"] = {
                "all_rows_spearman": included_rho,
                "witnessed_shared_rows": len(shared),
                "witnessed_only_spearman": witnessed_rho,
                "exact_equality_all_rows": left_values == right_values,
                "monotone_order_all_rows": included_rho is not None
                and math.isclose(abs(included_rho), 1.0, abs_tol=1e-12),
                "monotone_order_witnessed_only": witnessed_rho is not None
                and math.isclose(abs(witnessed_rho), 1.0, abs_tol=1e-12),
            }

    sensitivity = {
        projection: _sensitivity(
            [emission.vector for emission in emissions], projection
        )
        for projection in ("positive_score", "total_score")
    }
    mapping_outcomes: dict[str, Any] = {}
    for dimension in APPLICABLE_MAPPINGS:
        report = dimension_reports[dimension]
        ordering_changes = max(
            sensitivity[projection][dimension]["rows_with_rank_change"]
            for projection in sensitivity
        )
        redundancies = [
            other
            for other in APPLICABLE_MAPPINGS
            if other != dimension
            and pairwise[f"{dimension}|{other}"]["monotone_order_witnessed_only"]
        ]
        tests = {
            "non_zero_witnessed_coverage": report["empirical_witnessed_coverage"] > 0,
            "non_constant_numeric_projection": report["distinct_emitted_numeric_values"]
            > 1,
            "not_fully_boundary_saturated": report["saturation_count"]
            < sum(report["states"][state]["count"] for state in MEASURED_STATES),
            "not_exactly_monotone_redundant": not redundancies,
            "changes_conditional_ordering": ordering_changes > 0,
        }
        mapping_outcomes[dimension] = {
            "passes": all(tests.values()),
            "tests": tests,
            "redundant_with": redundancies,
        }

    return {
        "report_schema": 1,
        "corpus": {
            "kind": manifest["fixture_kind"],
            "row_count": len(rows),
            "source_sha256": manifest["source_sha256"],
            "derived_sha256": hashlib.sha256(fixture.read_bytes()).hexdigest(),
            "created_at_min": manifest["created_at_min"],
            "created_at_max": manifest["created_at_max"],
            "source_kind_drift": "not measurable from one kind",
            "live_dispatch_status": "frozen; no dispatch witnessed after 2026-08-26",
        },
        "dimensions": dimension_reports,
        "pairwise": pairwise,
        "conditional_order_sensitivity_non_adjudicative": sensitivity,
        "admission": {
            "accepted": accepted,
            "refused": 0,
            "mutation_refusals": _admission_mutations(emissions[0], datums[0]),
        },
        "applicable_mapping_outcomes": mapping_outcomes,
        "provisional_vindication": all(
            item["passes"] for item in mapping_outcomes.values()
        ),
        "vindication_wording_if_future_conditions_pass": "will hold when dispatch resumes",
    }


def _markdown(report: dict[str, Any]) -> str:
    outcome = "PASS" if report["provisional_vindication"] else "FAIL"
    lines = [
        "# Route-decision Option A falsifier — frozen 2026-08-26 history",
        "",
        "This report measures a frozen HISTORY, not a live dispatch stream. No dispatch has been witnessed since the freeze. "
        "If the applicable mappings eventually pass, the claim is **will hold when dispatch resumes**, never “holds live.”",
        "",
        f"- Rows: **{report['corpus']['row_count']}**",
        f"- Source SHA-256: `{report['corpus']['source_sha256']}`",
        f"- Selected-field fixture SHA-256: `{report['corpus']['derived_sha256']}`",
        f"- Provisional vindication: **{outcome}**",
        f"- Diagnostic admissions: **{report['admission']['accepted']} accepted, {report['admission']['refused']} refused**",
        f"- Negative admission mutations: **{len(report['admission']['mutation_refusals'])}/7 refused as required**",
        "",
        "## Applicable mapping results",
        "",
        "| Dimension | Result | Distinct numeric | Witnessed coverage | Redundant with | Ordering changed |",
        "|---|---:|---:|---:|---|---:|",
    ]
    sensitivity = report["conditional_order_sensitivity_non_adjudicative"]
    for dimension, result in report["applicable_mapping_outcomes"].items():
        stats = report["dimensions"][dimension]
        changed = max(
            sensitivity[p][dimension]["rows_with_rank_change"] for p in sensitivity
        )
        lines.append(
            f"| `{dimension}` | {'PASS' if result['passes'] else 'FAIL'} | "
            f"{stats['distinct_emitted_numeric_values']} | {stats['empirical_witnessed_coverage']:.1%} | "
            f"{', '.join(result['redundant_with']) or 'none'} | {changed} |"
        )
    lines.extend(
        [
            "",
            "The complete per-state counts and percentages, witnessed and emitted modes, distributions, boundary saturation, "
            "pairwise correlations/equality checks, nominal weights, conditional leave-one-out ordering sensitivity, and refusal "
            "messages are in the adjacent JSON report. `clamp_count` is explicitly absent because the recovered scorer does not "
            "expose pre-clamp values; it is not fabricated from boundary values.",
            "",
            "## Decision",
            "",
        ]
    )
    if report["provisional_vindication"]:
        lines.append(
            "The frozen history provisionally vindicates testing another source. It does not establish live delivery, calibration, "
            "freshness ownership, or the 13-dimension scheme estate-wide."
        )
    else:
        failed = [
            name
            for name, item in report["applicable_mapping_outcomes"].items()
            if not item["passes"]
        ]
        lines.append(
            "The frozen-history falsifier does **not** provisionally vindicate route decisions as the first source. "
            f"Failed applicable mappings: {', '.join(f'`{name}`' for name in failed)}. The unit remains diagnostic and dormant."
        )
    lines.extend(
        [
            "",
            "No service, hook, timer, binding registration, live consumer, DOI scalar, Reins route, store, dashboard, or activation "
            "was added or changed.",
            "",
            "## §4 constraint posture",
            "",
            "| # | Status | Implemented posture |",
            "|---:|---|---|",
            "| 1–5 | SATISFIED | Recovered 13-field contract and scorer; one deterministic, declarative, local `cc_task` emitter. |",
            "| 6 | SATISFIED | The injected AIR seal refuses before clocks, counts, digest, or scoring are used. |",
            "| 7–9 | SATISFIED / NOT-APPLICABLE | No Reins/publication-ladder route, DOI `I`, cost placement, or screenspace composition. |",
            "| 10–13 | SATISFIED | AIR default-deny, non-authorizing score/receipt, no alert-channel claim, authority capped as derived. |",
            "| 14 | CONFLICT—LIVE WITHHELD | Typed missingness is carried, but no source-specific projection policy was adjudicated. |",
            "| 15 | SATISFIED | JSON report carries evidence states, fields, reasons, provenance digests, and values. |",
            "| 16 | CONFLICT—LIVE WITHHELD | Timestamps are retained; no TTL owner/budget or freshness-valid activation is claimed. |",
            "| 17–24 | SATISFIED | Versioned parameters/contracts; dimension falsifier; no hidden preference gate, tenant machinery, new substrate, rendering, or personification. |",
            "",
            "The two conflicts narrow the result to frozen-history measurement and diagnostic admission. They are not treated as "
            "permission for live release.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("fixture", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("json_report", type=Path)
    parser.add_argument("markdown_report", type=Path)
    args = parser.parse_args()
    report = analyze(args.fixture, args.manifest)
    args.json_report.parent.mkdir(parents=True, exist_ok=True)
    args.json_report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    args.markdown_report.write_text(_markdown(report))
    return 0 if report["admission"]["accepted"] == report["corpus"]["row_count"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
