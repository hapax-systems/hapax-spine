from __future__ import annotations

import hashlib
import json
import runpy
from datetime import UTC, datetime
from pathlib import Path

import pytest

import hapax.spine.route_decision_topic_interest as route_unit
from hapax.spine.route_decision_topic_interest import (
    ADAPTER_VERSION,
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

FIXTURE = Path(__file__).parents[1] / "fixtures" / "route-decisions-20260826.jsonl"
MANIFEST = FIXTURE.with_suffix(".manifest.json")
REPORT = (
    Path(__file__).parents[1] / "reports" / "route-decision-falsifier-20260826.json"
)
ANALYSIS_AT = datetime(2026, 8, 28, tzinfo=UTC)


def _rows() -> list[dict[str, object]]:
    return [json.loads(line) for line in FIXTURE.read_text().splitlines()]


def _emission(index: int = 0) -> RouteDecisionEmission:
    datum = FrozenRouteDecisionDatum.model_validate(_rows()[index])
    return emit_route_decision_topic_interest(
        datum,
        source_frontier=SourceFrontier(
            frontier_ref="fixture:route-decisions-20260826",
            air_allowed=True,
            air_evidence_ref="operator:option-a-selected-field-freeze",
            prior_same_task_count=0,
            resource_state_refs_vary=False,
        ),
        adapter_version=ADAPTER_VERSION,
        clocks=EmissionClocks(analysis_at=ANALYSIS_AT, production_at=datum.created_at),
        parameters=AdapterParameters(),
    )


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


def test_frozen_fixture_is_the_declared_history_without_sensitive_fields() -> None:
    payload = FIXTURE.read_bytes()
    rows = _rows()
    manifest = json.loads(MANIFEST.read_text())

    assert len(rows) == manifest["row_count"] == 619
    assert hashlib.sha256(payload).hexdigest() == manifest["derived_sha256"]
    assert manifest["source_sha256"] == (
        "0b8f310f46c909246b729b7561c56d6c6880dc8bfffababceea88fdd6b126711"
    )
    assert manifest["fixture_kind"] == "historical_selected_field_projection"
    assert payload.count(b"\n") == 619
    assert b"/home/" not in payload
    forbidden = {
        "task_id",
        "source_id",
        "message",
        "candidates",
        "operator_constraints",
        "artifact_path",
    }
    assert all(not (forbidden & row.keys()) for row in rows)
    assert all(set(row) == set(rows[0]) for row in rows)


def test_freeze_transform_replaces_identity_and_reference_paths(tmp_path: Path) -> None:
    freeze_rows = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts" / "freeze_route_decisions.py")
    )["freeze_rows"]
    source = tmp_path / "raw.jsonl"
    base = {
        "created_at": "2026-08-26T01:02:03Z",
        "task_id": "private-task",
        "authority_allowed": True,
        "quota_freshness_green": True,
        "registry_freshness_green": True,
        "resource_freshness_green": True,
        "quota_evidence_refs": ["/home/operator/private/quota"],
        "resource_state_refs": ["/home/operator/private/resource"],
        "candidate_snapshot_ref": {
            "artifact_path": "/home/operator/candidate",
            "hash": "abc",
        },
        "demand_vector_ref": {
            "artifact_path": "/home/operator/demand",
            "freshness_state": "fresh",
            "hash": "def",
        },
        "stale_metadata": [],
    }
    source.write_text("\n".join(json.dumps(base) for _ in range(2)) + "\n")

    frozen, counts = freeze_rows(source)

    assert frozen[0]["task_token"] == frozen[1]["task_token"] == "task-0001"
    assert frozen[0]["quota_evidence_refs"] == ["quota-ref-0001"]
    assert frozen[0]["resource_state_refs"] == ["resource-ref-0001"]
    assert "/home/" not in json.dumps(frozen)
    assert counts == {"quota-ref": 1, "resource-ref": 1, "task": 1}


def test_falsifier_report_contains_every_required_measurement_family() -> None:
    report = json.loads(REPORT.read_text())
    analyze = runpy.run_path(
        str(Path(__file__).parents[1] / "scripts" / "analyze_route_decision_fixture.py")
    )["analyze"]
    recomputed = analyze(FIXTURE, MANIFEST)

    assert report == recomputed
    assert report["corpus"]["row_count"] == 619
    assert report["corpus"]["source_kind_drift"] == "not measurable from one kind"
    assert report["provisional_vindication"] is True
    assert set(report["dimensions"]) == {
        "novelty",
        "surprise",
        "relevance",
        "evidence_density",
        "trajectory",
        "public_value",
        "research_value",
        "actionability",
        "staleness",
        "rights_privacy_risk",
        "claim_risk",
        "duplicate_pressure",
        "operator_cost",
    }
    for dimension in report["dimensions"].values():
        assert sum(item["count"] for item in dimension["states"].values()) == 619
        assert "witnessed_numeric_distribution" in dimension
        assert (
            "emitted_numeric_distribution_including_typed_absence_projection"
            in dimension
        )
        assert "saturation_count" in dimension
        assert "nominal_positive_weight" in dimension
        assert "empirical_witnessed_coverage" in dimension
    assert len(report["pairwise"]) == 13 * 13
    assert set(report["conditional_order_sensitivity_non_adjudicative"]) == {
        "positive_score",
        "total_score",
    }
    assert len(report["admission"]["mutation_refusals"]) == 7
    assert report["vindication_wording_if_future_conditions_pass"] == (
        "will hold when dispatch resumes"
    )


def test_emitter_is_deterministic_and_keeps_absence_visible() -> None:
    first = _emission()
    second = _emission()
    states = {item.dimension: item.state for item in first.receipt.dimension_evidence}

    assert first == second
    assert first.receipt.vector_digest == second.receipt.vector_digest
    assert first.evidence.programme_relevant is False
    assert first.evidence.publication_relevant is False
    assert (
        first.evidence.substrate_refs == ()
    )  # constant in this freeze, so not evidence
    assert states == {
        "novelty": "witnessed",
        "surprise": "absent",
        "relevance": "absent",
        "evidence_density": "witnessed",
        "trajectory": "absent",
        "public_value": "not_applicable",
        "research_value": "absent",
        "actionability": "witnessed",
        "staleness": "partial",
        "rights_privacy_risk": "blocked",
        "claim_risk": "partial",
        "duplicate_pressure": "known_zero",
        "operator_cost": "witnessed",
    }
    assert first.receipt.numeric_projection_non_authorizing is True


def test_air_denial_happens_before_any_consumer_visible_derivative(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    datums = [
        FrozenRouteDecisionDatum.model_validate(_rows()[index]) for index in (0, 1)
    ]
    denied = SourceFrontier(
        frontier_ref="fixture:denied",
        air_allowed=False,
        air_evidence_ref="air:deny",
        prior_same_task_count=999,
        resource_state_refs_vary=True,
    )

    def forbidden_derivative(*args: object, **kwargs: object) -> object:
        raise AssertionError("denied input reached a derivative")

    monkeypatch.setattr(route_unit, "featurize", forbidden_derivative)
    monkeypatch.setattr(route_unit, "_digest", forbidden_derivative)
    refusals = []
    for datum in datums:
        with pytest.raises(
            EmissionRefusal, match="before computing counts, digests, or scores"
        ) as caught:
            emit_route_decision_topic_interest(
                datum,
                source_frontier=denied,
                adapter_version=ADAPTER_VERSION,
                clocks=EmissionClocks(
                    analysis_at=ANALYSIS_AT,
                    production_at=datum.created_at,
                ),
                parameters=AdapterParameters(),
            )
        refusals.append(str(caught.value))
    assert refusals[0] == refusals[1]


def test_consumer_refuses_without_declared_producer_binding_with_remedy() -> None:
    emission = _emission()
    with pytest.raises(AdmissionRefusal) as caught:
        admit_route_decision_topic_interest(
            emission,
            binding=None,
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda _: True,
        )
    message = str(caught.value)
    assert "route_decision_topic_interest_binding" in message
    assert "remedy: declare" in message


def test_consumer_refuses_raw_vector_wrong_producer_and_digest_mismatch() -> None:
    emission = _emission()
    binding = _binding(emission)
    with pytest.raises(AdmissionRefusal, match="raw or fabricated vector"):
        admit_route_decision_topic_interest(
            emission.vector,
            binding=binding,
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda _: True,
        )
    with pytest.raises(AdmissionRefusal, match="wrong producer identity"):
        admit_route_decision_topic_interest(
            emission,
            binding=binding.model_copy(update={"producer_id": "undeclared.producer"}),
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda _: True,
        )
    tampered_vector = emission.vector.model_copy(update={"novelty": 0.123})
    tampered = emission.model_copy(update={"vector": tampered_vector})
    with pytest.raises(AdmissionRefusal, match="delivery vector digest mismatch"):
        admit_route_decision_topic_interest(
            tampered,
            binding=binding,
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda _: True,
        )


def test_consumer_refuses_undeclared_source_states_and_stale_source() -> None:
    emission = _emission()
    binding = _binding(emission)
    wrong_source = binding.model_copy(update={"allowed_source": "pull_request"})
    with pytest.raises(AdmissionRefusal, match="undeclared source"):
        admit_route_decision_topic_interest(
            emission,
            binding=wrong_source,
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda _: True,
        )

    changed_states = tuple(
        item.model_copy(update={"state": "stale"})
        if item.dimension == "staleness"
        else item
        for item in emission.receipt.dimension_evidence
    )
    stale_receipt = emission.receipt.model_copy(
        update={"dimension_evidence": changed_states}
    )
    stale = emission.model_copy(update={"receipt": stale_receipt})
    stale_binding = binding.model_copy(update={"dimension_evidence": changed_states})
    with pytest.raises(AdmissionRefusal, match="stale source refused"):
        admit_route_decision_topic_interest(
            stale,
            binding=stale_binding,
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda _: True,
        )


def test_consumer_refuses_mismatched_dimension_states() -> None:
    emission = _emission()
    binding = _binding(emission)
    changed = tuple(
        item.model_copy(update={"state": "absent"})
        if item.dimension == "novelty"
        else item
        for item in binding.dimension_evidence
    )
    with pytest.raises(AdmissionRefusal, match="mismatched evidence states"):
        admit_route_decision_topic_interest(
            emission,
            binding=binding.model_copy(update={"dimension_evidence": changed}),
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda _: True,
        )


def test_consumer_refuses_when_existing_receipt_path_cannot_append() -> None:
    emission = _emission()
    with pytest.raises(AdmissionRefusal, match="receipt was not appended"):
        admit_route_decision_topic_interest(
            emission,
            binding=_binding(emission),
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda _: False,
        )


def test_accepted_delivery_binds_native_input_and_receipt_before_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    emission = _emission()
    appended: list[AcceptanceReceipt] = []
    original_observation = route_unit.TopicInterestObservation

    def sink(receipt: AcceptanceReceipt) -> bool:
        appended.append(receipt)
        return True

    def observation_after_receipt(**kwargs: object):
        assert appended, (
            "consumer observation constructed before acceptance receipt append"
        )
        return original_observation(**kwargs)

    monkeypatch.setattr(
        route_unit, "TopicInterestObservation", observation_after_receipt
    )

    admitted = admit_route_decision_topic_interest(
        emission,
        binding=_binding(emission),
        accepted_at=ANALYSIS_AT,
        append_acceptance=sink,
    )

    assert appended == [admitted.acceptance_receipt]
    assert admitted.observation.signals is emission.vector
    assert admitted.observation.source_kind == "cc_task"
    assert admitted.observation.source_id.startswith("task-")
    assert admitted.acceptance_receipt.vector_digest == emission.receipt.vector_digest
    assert admitted.acceptance_receipt.authority == "derived_non_authorizing"


@pytest.mark.parametrize(
    ("field", "replacement", "reason"),
    [
        ("producer_version", "wrong", "wrong producer version"),
        ("adapter_version", "wrong", "mismatched adapter version"),
        ("evidence_ref", "wrong", "mismatched evidence reference"),
        ("vector_digest", "0" * 64, "mismatched bound vector digest"),
    ],
)
def test_consumer_binding_fields_are_mandatory(
    field: str, replacement: str, reason: str
) -> None:
    emission = _emission()
    binding = _binding(emission).model_copy(update={field: replacement})
    with pytest.raises(AdmissionRefusal, match=reason):
        admit_route_decision_topic_interest(
            emission,
            binding=binding,
            accepted_at=ANALYSIS_AT,
            append_acceptance=lambda _: True,
        )
