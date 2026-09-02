"""Pure ``cc_task`` route-decision emission and admission-bound delivery.

Nothing in this module registers a hook, timer, service, or live binding.  Callers own I/O,
AIR adjudication, source-frontier construction, and the acceptance-receipt sink.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from hapax.spine.topic_interest_engine import (
    TopicInterestObservation,
    TopicInterestScoreVector,
)
from hapax.spine.topic_interest_featurizer import TopicInterestEvidence, featurize

ADAPTER_VERSION = "route-decision-cc-task-v1"
PRODUCER_ID = "hapax.spine.route_decision_topic_interest"
PRODUCER_VERSION = "1"
DIMENSIONS = (
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
)


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CandidateSnapshot(_FrozenModel):
    hash: str = Field(min_length=1)


class DemandVectorReference(_FrozenModel):
    freshness_state: str = Field(min_length=1)
    hash: str = Field(min_length=1)


class StaleMetadata(_FrozenModel):
    effect: str
    field: str
    observed_at: datetime | None
    source_token: str
    stale_after: str | None


class FrozenRouteDecisionDatum(_FrozenModel):
    """The selected-field fixture schema; raw identifiers and paths are forbidden upstream."""

    authority_allowed: bool
    candidate_snapshot_ref: CandidateSnapshot
    created_at: datetime
    demand_vector_ref: DemandVectorReference
    quota_evidence_refs: tuple[str, ...]
    quota_freshness_green: bool
    registry_freshness_green: bool
    resource_freshness_green: bool
    resource_state_refs: tuple[str, ...]
    stale_metadata: tuple[StaleMetadata, ...]
    task_token: str = Field(pattern=r"^task-[0-9]{4}$")


class SourceFrontier(_FrozenModel):
    """Facts computed by the caller after AIR sealing and before this one datum."""

    frontier_ref: str = Field(min_length=1)
    air_allowed: bool
    air_evidence_ref: str = Field(min_length=1)
    prior_same_task_count: int = Field(ge=0)
    resource_state_refs_vary: bool


class AdapterParameters(_FrozenModel):
    duplicate_saturation: int = Field(default=5, gt=0)
    grounding_question: str = (
        "Which admitted route decision merits allocation attention?"
    )


class EmissionClocks(_FrozenModel):
    analysis_at: datetime
    production_at: datetime


EvidenceState = Literal[
    "witnessed",
    "partial",
    "absent",
    "stale",
    "blocked",
    "known_zero",
    "not_applicable",
]


class DimensionEvidence(_FrozenModel):
    dimension: str
    state: EvidenceState
    source_fields: tuple[str, ...] = ()
    reason: str


class DerivationReceipt(_FrozenModel):
    receipt_schema: Literal[1] = 1
    source_kind: Literal["cc_task"] = "cc_task"
    source_frontier: str
    producer_id: str
    producer_version: str
    adapter_version: str
    analysis_at: datetime
    production_at: datetime
    evidence_ref: str
    air_evidence_ref: str
    input_digest: str
    vector_digest: str
    dimension_evidence: tuple[DimensionEvidence, ...]
    numeric_projection_non_authorizing: Literal[True] = True


class RouteDecisionEmission(_FrozenModel):
    source_token: str
    grounding_question: str
    evidence: TopicInterestEvidence
    vector: TopicInterestScoreVector
    receipt: DerivationReceipt


class ProducerBinding(_FrozenModel):
    binding_name: Literal["route_decision_topic_interest_binding"]
    allowed_source: Literal["cc_task"]
    producer_id: str
    producer_version: str
    evidence_ref: str
    adapter_version: str
    vector_digest: str
    dimension_evidence: tuple[DimensionEvidence, ...]


class AcceptanceReceipt(_FrozenModel):
    receipt_schema: Literal[1] = 1
    binding_name: str
    observation_id: str
    evidence_ref: str
    vector_digest: str
    accepted_at: datetime
    accepted: Literal[True] = True
    authority: Literal["derived_non_authorizing"] = "derived_non_authorizing"


class AdmittedTopicInterest(_FrozenModel):
    observation: TopicInterestObservation
    acceptance_receipt: AcceptanceReceipt


class EmissionRefusal(ValueError):
    """The source was not allowed to enter the derivation boundary."""


class AdmissionRefusal(ValueError):
    """The consumer refused a delivery before normal release."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _digest(value: BaseModel | dict[str, Any]) -> str:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def vector_digest(vector: TopicInterestScoreVector) -> str:
    return _digest(vector)


def _dimension_evidence(
    datum: FrozenRouteDecisionDatum,
    frontier: SourceFrontier,
) -> tuple[DimensionEvidence, ...]:
    refs = bool(datum.quota_evidence_refs or datum.candidate_snapshot_ref.hash)
    claim_state: EvidenceState = "partial" if datum.stale_metadata else "absent"
    duplicate_state: EvidenceState = (
        "known_zero" if frontier.prior_same_task_count == 0 else "witnessed"
    )
    cost_state: EvidenceState = (
        "known_zero"
        if datum.authority_allowed and datum.quota_freshness_green
        else "witnessed"
    )
    values = {
        "novelty": (
            "witnessed",
            ("task_token", "*_freshness_green"),
            "repeat and freshness facts",
        ),
        "surprise": ("absent", (), "not produced by this source"),
        "relevance": ("absent", (), "no programme or publication relevance evidence"),
        "evidence_density": (
            "witnessed" if refs else "absent",
            ("quota_evidence_refs", "candidate_snapshot_ref") if refs else (),
            "opaque evidence and provenance references"
            if refs
            else "no evidence references",
        ),
        "trajectory": ("absent", (), "not produced by this source"),
        "public_value": (
            "not_applicable",
            (),
            "internal routing is not publication evidence",
        ),
        "research_value": (
            "absent",
            (),
            "uncalibrated source-kind prior is not datum evidence",
        ),
        "actionability": (
            "witnessed",
            ("authority_allowed", "quota_freshness_green"),
            "authority and quota availability evidence; kind prior remains uncalibrated",
        ),
        "staleness": (
            "partial",
            ("created_at", "*_freshness_green", "demand_vector_ref.freshness_state"),
            "inputs witnessed; numeric currentness awaits freshness ownership and budget",
        ),
        "rights_privacy_risk": (
            "blocked",
            (),
            "source mapping produces no rights or consent evidence",
        ),
        "claim_risk": (
            claim_state,
            ("stale_metadata",) if datum.stale_metadata else (),
            "stale metadata witnesses uncertainty only"
            if datum.stale_metadata
            else "no claim evidence",
        ),
        "duplicate_pressure": (
            duplicate_state,
            ("task_token",),
            "prior same-task count is observed at the sealed frontier",
        ),
        "operator_cost": (
            cost_state,
            ("authority_allowed", "quota_freshness_green"),
            "authority and quota facts; later scalar placement remains open",
        ),
    }
    return tuple(
        DimensionEvidence(
            dimension=name,
            state=values[name][0],
            source_fields=values[name][1],
            reason=values[name][2],
        )
        for name in DIMENSIONS
    )


def emit_route_decision_topic_interest(
    datum: FrozenRouteDecisionDatum,
    *,
    source_frontier: SourceFrontier,
    adapter_version: str,
    clocks: EmissionClocks,
    parameters: AdapterParameters,
) -> RouteDecisionEmission:
    """Map one already AIR-allowed selected datum through the recovered featurizer."""

    if not source_frontier.air_allowed:
        raise EmissionRefusal(
            "route-decision datum denied by AIR seal; remedy: supply an allowed, auditable "
            "source frontier before computing counts, digests, or scores"
        )
    if adapter_version != ADAPTER_VERSION:
        raise EmissionRefusal(
            f"unsupported adapter version {adapter_version!r}; remedy: bind {ADAPTER_VERSION!r}"
        )
    analysis_at = _utc(clocks.analysis_at)
    production_at = _utc(clocks.production_at)
    observed_at = _utc(datum.created_at)
    freshness_green = (
        datum.quota_freshness_green
        and datum.registry_freshness_green
        and datum.resource_freshness_green
        and datum.demand_vector_ref.freshness_state == "fresh"
    )
    evidence_refs = tuple(datum.quota_evidence_refs)
    provenance_refs = (f"candidate-snapshot:{datum.candidate_snapshot_ref.hash}",)
    substrate_refs = (
        datum.resource_state_refs if source_frontier.resource_state_refs_vary else ()
    )
    evidence = TopicInterestEvidence(
        source_kind="cc_task",
        observed_at=observed_at,
        retrieved_at=production_at,
        freshness_ttl_s=None,
        public_mode="dry_run",
        rights_state="unknown",
        substrate_refs=substrate_refs,
        evidence_refs=evidence_refs,
        provenance_refs=provenance_refs,
        programme_relevant=False,
        publication_relevant=False,
        requires_operator_authority=not datum.authority_allowed,
        recent_duplicate_count=source_frontier.prior_same_task_count,
        quota_available=datum.quota_freshness_green,
        current_event_claim=False,
        sensitive_event=False,
        trend_current_event=False,
        trend_used_as_truth=False,
        recency_label_present=freshness_green,
        title_uncertainty_present=False,
        description_uncertainty_present=bool(datum.stale_metadata),
    )
    vector = featurize(
        evidence,
        now=analysis_at,
        duplicate_saturation=parameters.duplicate_saturation,
    )
    states = _dimension_evidence(datum, source_frontier)
    input_digest = _digest(
        {
            "adapter_version": adapter_version,
            "clocks": clocks.model_dump(mode="json"),
            "datum": datum.model_dump(mode="json"),
            "parameters": parameters.model_dump(mode="json"),
            "source_frontier": source_frontier.model_dump(mode="json"),
        }
    )
    receipt = DerivationReceipt(
        source_frontier=source_frontier.frontier_ref,
        producer_id=PRODUCER_ID,
        producer_version=PRODUCER_VERSION,
        adapter_version=adapter_version,
        analysis_at=analysis_at,
        production_at=production_at,
        evidence_ref=f"{source_frontier.frontier_ref}:datum:{input_digest[:16]}",
        air_evidence_ref=source_frontier.air_evidence_ref,
        input_digest=input_digest,
        vector_digest=vector_digest(vector),
        dimension_evidence=states,
    )
    return RouteDecisionEmission(
        source_token=datum.task_token,
        grounding_question=parameters.grounding_question,
        evidence=evidence,
        vector=vector,
        receipt=receipt,
    )


MISSING_BINDING_REFUSAL = (
    "missing producer binding 'route_decision_topic_interest_binding'; remedy: declare the "
    "cc_task source, producer identity/version, evidence reference, adapter version, vector "
    "digest, and per-dimension evidence states at the consumer composition root"
)


def admit_route_decision_topic_interest(
    delivery: RouteDecisionEmission | TopicInterestScoreVector,
    *,
    binding: ProducerBinding | None,
    accepted_at: datetime,
    append_acceptance: Callable[[AcceptanceReceipt], bool],
) -> AdmittedTopicInterest:
    """Validate the producer binding and append acceptance before consumer release."""

    if binding is None:
        raise AdmissionRefusal(MISSING_BINDING_REFUSAL)
    if not isinstance(delivery, RouteDecisionEmission):
        raise AdmissionRefusal(
            "raw or fabricated vector has no derivation receipt; remedy: deliver the bound "
            "RouteDecisionEmission from the declared producer"
        )
    receipt = delivery.receipt
    checks = (
        (binding.allowed_source == receipt.source_kind, "undeclared source"),
        (binding.producer_id == receipt.producer_id, "wrong producer identity"),
        (
            binding.producer_version == receipt.producer_version,
            "wrong producer version",
        ),
        (binding.evidence_ref == receipt.evidence_ref, "mismatched evidence reference"),
        (
            binding.adapter_version == receipt.adapter_version,
            "mismatched adapter version",
        ),
        (
            binding.vector_digest == receipt.vector_digest,
            "mismatched bound vector digest",
        ),
        (
            binding.dimension_evidence == receipt.dimension_evidence,
            "mismatched evidence states",
        ),
        (
            receipt.vector_digest == vector_digest(delivery.vector),
            "delivery vector digest mismatch",
        ),
    )
    for accepted, reason in checks:
        if not accepted:
            raise AdmissionRefusal(
                f"{reason}; remedy: regenerate and declare the exact producer binding"
            )
    states = {item.dimension: item.state for item in receipt.dimension_evidence}
    if states.get("staleness") == "stale":
        raise AdmissionRefusal(
            "stale source refused; remedy: produce a fresh source envelope under the declared budget"
        )

    observation_id = f"topic-interest:{receipt.input_digest[:24]}"
    acceptance = AcceptanceReceipt(
        binding_name=binding.binding_name,
        observation_id=observation_id,
        evidence_ref=receipt.evidence_ref,
        vector_digest=receipt.vector_digest,
        accepted_at=_utc(accepted_at),
    )
    try:
        appended = append_acceptance(acceptance)
    except Exception as error:
        raise AdmissionRefusal(
            "acceptance receipt append failed; remedy: restore the declared delivery receipt path"
        ) from error
    if appended is not True:
        raise AdmissionRefusal(
            "acceptance receipt was not appended; remedy: restore the declared delivery receipt path"
        )

    evidence = delivery.evidence
    observation = TopicInterestObservation(
        observation_id=observation_id,
        source_id=delivery.source_token,
        subject="opaque cc_task route decision",
        subject_cluster="cc_task",
        grounding_question=delivery.grounding_question,
        signals=delivery.vector,
        **evidence.model_dump(),
    )
    return AdmittedTopicInterest(observation=observation, acceptance_receipt=acceptance)
