"""Produce the 13-dimension TopicInterestScoreVector the engine consumes.

The engine (``topic_interest_engine``) is complete: weights, thresholds, gating, downgrade
reasons, impingement minting. But ``TopicInterestObservation.signals`` is a REQUIRED field of
type ``TopicInterestScoreVector``, and estate-wide that vector is constructed in exactly two
places -- its own class definition and a test. Nothing produces it, so nothing feeds the engine.
This module is that missing producer.

Why the input is not a TopicInterestObservation
-----------------------------------------------
It cannot be: the observation already REQUIRES the vector. Featurization therefore happens one
step earlier, over the same evidence the observation carries. ``TopicInterestEvidence`` below is
exactly the observation's scoring-relevant fields, under identical names, so composition is:

    evidence = TopicInterestEvidence(...)
    observation = TopicInterestObservation(
        observation_id=..., source_id=..., subject=..., subject_cluster=...,
        grounding_question=...,
        signals=featurize(evidence, now=now),
        **evidence.model_dump(),
    )

Grounding
---------
Every dimension below is derived from named evidence fields that ALREADY exist on the
observation. No new evidence is invented. Where the engine itself later re-derives a dimension
(``_effective_score_vector`` folds TTL age into ``staleness`` and duplicate counts into
``duplicate_pressure``), this module produces a floor and lets the engine raise it -- it never
double-counts, because the engine takes ``max()`` of the two.

Fail-closed
-----------
Absent evidence must not read as safe. Unknown rights state carries non-zero
``rights_privacy_risk``; a current-event claim with no primary or official source carries high
``claim_risk``. Positive dimensions default LOW on missing evidence, penalty dimensions default
NON-ZERO where the missing evidence is safety-relevant.

Calibration status: UNCALIBRATED. The per-kind priors are structural defaults expressing what a
source kind IS, not measured values. They are the input to the calibration question, not its
answer. The engine's five thresholds were authored for a publication pipeline and must not be
reused as cockpit display breaks without deriving them against real scored data.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from hapax.spine.topic_interest_engine import (
    PUBLIC_MODES,
    UNSAFE_RIGHTS_STATES,
    TopicInterestScoreVector,
    TopicInterestSourceKind,
)

# Duplicate count at which duplicate_pressure saturates. Mirrors the engine policy default so a
# featurized floor and the engine's own fold agree on scale.
DEFAULT_DUPLICATE_SATURATION = 5

# Corroborating-source count at which evidence_density's corroboration term saturates.
CORROBORATION_SATURATION = 3


def _clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


class TopicInterestEvidence(BaseModel):
    """The observation's scoring-relevant fields, under identical names.

    Deliberately excludes identity (observation_id/source_id/subject/subject_cluster/
    grounding_question) and ``signals`` itself, so ``**evidence.model_dump()`` composes into a
    TopicInterestObservation without collision.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_kind: TopicInterestSourceKind
    observed_at: datetime
    retrieved_at: datetime | None = None
    freshness_ttl_s: int | None = Field(default=None, ge=0)

    public_mode: str = "dry_run"
    rights_state: str = "unknown"
    rights_hints: tuple[str, ...] = ()

    substrate_refs: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    provenance_refs: tuple[str, ...] = ()

    programme_relevant: bool = True
    publication_relevant: bool = True
    requires_operator_authority: bool = False
    recent_duplicate_count: int = Field(default=0, ge=0)
    quota_available: bool = True

    current_event_claim: bool = False
    sensitive_event: bool = False
    trend_current_event: bool = False
    trend_used_as_truth: bool = False
    trend_decay_score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_bias_score: float | None = Field(default=None, ge=0.0, le=1.0)

    primary_source_count: int = Field(default=0, ge=0)
    official_source_count: int = Field(default=0, ge=0)
    corroborating_source_count: int = Field(default=0, ge=0)

    recency_label_present: bool = False
    title_uncertainty_present: bool = False
    description_uncertainty_present: bool = False
    edsa_context_present: bool = False


# What a source kind IS, structurally -- not a measured prior. Only dimensions that the KIND
# itself speaks to are given a floor; everything else is left to the evidence.
#   research_value  -- the kind exists to answer questions
#   actionability   -- the kind names a thing someone can act on
#   public_value    -- the kind is publication-facing by construction
_KIND_PRIORS: dict[str, dict[str, float]] = {
    "chronicle_event": {"actionability": 0.30},
    "research_registry_entry": {"research_value": 0.70, "actionability": 0.20},
    "cc_task": {"actionability": 0.75, "research_value": 0.20},
    "pull_request": {"actionability": 0.70, "research_value": 0.25},
    "review_outcome": {"actionability": 0.60, "research_value": 0.35},
    "publication_log": {"public_value": 0.65, "actionability": 0.25},
    "programme_boundary": {"actionability": 0.55, "research_value": 0.30},
    "content_observation": {"public_value": 0.60, "research_value": 0.30},
    "platform_aggregate": {"research_value": 0.45, "actionability": 0.35},
    "operator_signal": {"actionability": 0.85, "research_value": 0.25},
    "external_reference": {"research_value": 0.40, "public_value": 0.30},
}


def _prior(kind: str, dimension: str) -> float:
    return _KIND_PRIORS.get(kind, {}).get(dimension, 0.0)


def featurize(
    evidence: TopicInterestEvidence,
    *,
    now: datetime | None = None,
    duplicate_saturation: int = DEFAULT_DUPLICATE_SATURATION,
) -> TopicInterestScoreVector:
    """Map evidence to the 13 bounded dimensions. Deterministic; no I/O."""

    now = (now or datetime.now(UTC)).astimezone(UTC)
    kind = evidence.source_kind

    ref_count = len(evidence.evidence_refs) + len(evidence.provenance_refs)
    sourced = evidence.primary_source_count + evidence.official_source_count
    corroboration = _clamp(evidence.corroborating_source_count / CORROBORATION_SATURATION)
    duplicate_ratio = _clamp(evidence.recent_duplicate_count / max(1, duplicate_saturation))

    # --- positive -------------------------------------------------------------------------
    # novelty: not seen before. Duplicates are the direct counter-evidence; an explicit recency
    # label is weak positive evidence that the thing is new.
    novelty = _clamp((1.0 - duplicate_ratio) * (0.85 if not evidence.recency_label_present else 1.0))

    # surprise: a current-event trend that has NOT yet decayed. trend_decay_score is how far
    # through its arc the trend is, so surprise falls as decay rises.
    if evidence.trend_current_event:
        surprise = _clamp(1.0 - (evidence.trend_decay_score if evidence.trend_decay_score is not None else 0.5))
    else:
        surprise = _clamp(0.20 * (1.0 - duplicate_ratio))

    # relevance: the two relevance flags the observation already carries. Both false is a real
    # signal that this does not concern us.
    relevance = _clamp(
        (0.55 if evidence.programme_relevant else 0.0)
        + (0.45 if evidence.publication_relevant else 0.0)
    )

    # evidence_density: how much backing exists. Primary/official sources dominate;
    # corroboration and raw refs contribute less.
    evidence_density = _clamp(
        0.50 * _clamp(sourced / 2.0) + 0.30 * corroboration + 0.20 * _clamp(ref_count / 4.0)
    )

    # trajectory: is this going somewhere. Only trend evidence speaks to it; absent trend
    # evidence this stays low rather than neutral (fail-closed on positives).
    if evidence.trend_current_event:
        trajectory = _clamp(1.0 - 0.6 * (evidence.trend_decay_score if evidence.trend_decay_score is not None else 0.5))
    else:
        trajectory = 0.15

    # public_value: publishable posture plus official standing.
    public_value = _clamp(
        _prior(kind, "public_value")
        + (0.30 if evidence.public_mode in PUBLIC_MODES else 0.0)
        + (0.20 if evidence.publication_relevant else 0.0)
        + 0.15 * _clamp(evidence.official_source_count / 2.0)
    )

    # research_value: what the kind is for, raised by durable context and substrate anchoring.
    research_value = _clamp(
        _prior(kind, "research_value")
        + (0.20 if evidence.edsa_context_present else 0.0)
        + 0.15 * _clamp(len(evidence.substrate_refs) / 2.0)
    )

    # actionability: what the kind affords, reduced when the quota to act is gone.
    actionability = _clamp(
        _prior(kind, "actionability") * (1.0 if evidence.quota_available else 0.4)
        + (0.15 if evidence.requires_operator_authority else 0.0)
    )

    # --- penalty --------------------------------------------------------------------------
    # staleness: a FLOOR from TTL age. The engine re-folds this via max(), so a floor here is
    # never double-counted. No TTL and no recency label => mild non-zero (we do not know).
    staleness = 0.0
    observed = evidence.observed_at.astimezone(UTC)
    if evidence.freshness_ttl_s:
        age_s = max(0.0, (now - observed).total_seconds())
        staleness = _clamp(age_s / evidence.freshness_ttl_s)
    elif not evidence.recency_label_present:
        staleness = 0.25

    # rights_privacy_risk: fail-closed. Uncleared third-party rights is maximal; unknown is not
    # zero; sensitivity and explicit hints raise it.
    if evidence.rights_state in UNSAFE_RIGHTS_STATES:
        rights_privacy_risk = 1.0
    else:
        rights_privacy_risk = _clamp(
            (0.35 if evidence.rights_state == "unknown" else 0.0)
            + (0.40 if evidence.sensitive_event else 0.0)
            + 0.10 * len(evidence.rights_hints)
        )

    # claim_risk: the core fail-closed rule -- asserting a current event with no primary or
    # official source is the high-risk case. Uncertainty markers and source bias add to it.
    claim_risk = 0.0
    if evidence.current_event_claim:
        claim_risk = 0.75 if sourced == 0 else _clamp(0.45 - 0.15 * min(sourced, 3))
    if evidence.trend_used_as_truth:
        claim_risk = max(claim_risk, 0.60)
    claim_risk = _clamp(
        claim_risk
        + (0.10 if evidence.title_uncertainty_present else 0.0)
        + (0.10 if evidence.description_uncertainty_present else 0.0)
        + 0.20 * (evidence.source_bias_score or 0.0)
    )

    # duplicate_pressure: a floor; the engine re-folds the same ratio via max().
    duplicate_pressure = duplicate_ratio

    # operator_cost: what spending this costs the operator -- their authority, or acting while
    # the quota is exhausted.
    operator_cost = _clamp(
        (0.60 if evidence.requires_operator_authority else 0.0)
        + (0.30 if not evidence.quota_available else 0.0)
    )

    return TopicInterestScoreVector(
        novelty=novelty,
        surprise=surprise,
        relevance=relevance,
        evidence_density=evidence_density,
        trajectory=trajectory,
        public_value=public_value,
        research_value=research_value,
        actionability=actionability,
        staleness=staleness,
        rights_privacy_risk=rights_privacy_risk,
        claim_risk=claim_risk,
        duplicate_pressure=duplicate_pressure,
        operator_cost=operator_cost,
    )
