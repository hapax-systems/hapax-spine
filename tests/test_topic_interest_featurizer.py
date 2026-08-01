"""The featurizer: the missing producer of TopicInterestScoreVector.

Self-contained per the repo testing convention (no shared conftest fixtures).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from hapax.spine.topic_interest_engine import (
    POSITIVE_WEIGHTS,
    TopicInterestObservation,
    TopicInterestPolicy,
    TopicInterestScoreVector,
    decide_topic_interest,
)
from hapax.spine.topic_interest_featurizer import (
    TopicInterestEvidence,
    featurize,
)

NOW = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)

ALL_KINDS = [
    "chronicle_event",
    "research_registry_entry",
    "cc_task",
    "pull_request",
    "review_outcome",
    "publication_log",
    "programme_boundary",
    "content_observation",
    "platform_aggregate",
    "operator_signal",
    "external_reference",
]


def _evidence(**overrides) -> TopicInterestEvidence:
    values = {"source_kind": "cc_task", "observed_at": NOW}
    values.update(overrides)
    return TopicInterestEvidence(**values)


# ------------------------------------------------------------------------------------------
# 1. Totality: every source kind yields a valid, bounded vector
# ------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind", ALL_KINDS)
def test_every_source_kind_produces_a_bounded_vector(kind: str) -> None:
    vector = featurize(_evidence(source_kind=kind), now=NOW)

    assert isinstance(vector, TopicInterestScoreVector)
    for name, value in vector.model_dump().items():
        assert 0.0 <= value <= 1.0, (name, value)


# ------------------------------------------------------------------------------------------
# 2. The featurizer actually feeds the engine -- the whole point of the module
# ------------------------------------------------------------------------------------------
def test_featurized_vector_composes_into_an_observation_the_engine_decides() -> None:
    evidence = _evidence(
        source_kind="cc_task",
        primary_source_count=2,
        corroborating_source_count=2,
        freshness_ttl_s=86_400,
    )
    observation = TopicInterestObservation(
        observation_id="obs-1",
        source_id="src-1",
        subject="a subject",
        subject_cluster="a cluster",
        grounding_question="does the featurizer feed the engine?",
        signals=featurize(evidence, now=NOW),
        **evidence.model_dump(),
    )

    decision = decide_topic_interest(observation, now=NOW, policy=TopicInterestPolicy())

    assert decision.observation_id == "obs-1"
    assert 0.0 <= decision.score <= 1.0
    assert decision.action in {
        "ignore",
        "watch",
        "research_more",
        "frame_candidate",
        "emit_content_observation",
        "operator_question",
        "refusal_candidate",
    }


# ------------------------------------------------------------------------------------------
# 3. Fail-closed: absent evidence must not read as safe
# ------------------------------------------------------------------------------------------
def test_unknown_rights_state_is_not_zero_risk() -> None:
    assert featurize(_evidence(rights_state="unknown"), now=NOW).rights_privacy_risk > 0.0


def test_uncleared_third_party_rights_is_maximal_risk() -> None:
    vector = featurize(_evidence(rights_state="third_party_uncleared"), now=NOW)
    assert vector.rights_privacy_risk == 1.0


def test_current_event_claim_without_any_source_is_high_claim_risk() -> None:
    unsourced = featurize(_evidence(current_event_claim=True), now=NOW)
    sourced = featurize(
        _evidence(current_event_claim=True, primary_source_count=2, official_source_count=1),
        now=NOW,
    )
    assert unsourced.claim_risk >= 0.75
    assert sourced.claim_risk < unsourced.claim_risk


def test_trend_used_as_truth_carries_claim_risk_even_when_sourced() -> None:
    vector = featurize(
        _evidence(trend_used_as_truth=True, primary_source_count=3, official_source_count=3),
        now=NOW,
    )
    assert vector.claim_risk >= 0.60


# ------------------------------------------------------------------------------------------
# 4. Monotonicity of the dimensions that have a clear direction
# ------------------------------------------------------------------------------------------
def test_duplicates_lower_novelty_and_raise_duplicate_pressure() -> None:
    fresh = featurize(_evidence(recent_duplicate_count=0), now=NOW)
    dupe = featurize(_evidence(recent_duplicate_count=5), now=NOW)

    assert dupe.novelty < fresh.novelty
    assert dupe.duplicate_pressure > fresh.duplicate_pressure


def test_trend_decay_lowers_surprise_and_trajectory() -> None:
    rising = featurize(_evidence(trend_current_event=True, trend_decay_score=0.1), now=NOW)
    spent = featurize(_evidence(trend_current_event=True, trend_decay_score=0.9), now=NOW)

    assert spent.surprise < rising.surprise
    assert spent.trajectory < rising.trajectory


def test_more_sources_raise_evidence_density() -> None:
    thin = featurize(_evidence(), now=NOW)
    thick = featurize(
        _evidence(
            primary_source_count=2,
            official_source_count=1,
            corroborating_source_count=3,
            evidence_refs=("e1", "e2"),
            provenance_refs=("p1", "p2"),
        ),
        now=NOW,
    )
    assert thick.evidence_density > thin.evidence_density


def test_irrelevance_on_both_axes_collapses_relevance() -> None:
    vector = featurize(_evidence(programme_relevant=False, publication_relevant=False), now=NOW)
    assert vector.relevance == 0.0


def test_operator_authority_and_exhausted_quota_cost_the_operator() -> None:
    free = featurize(_evidence(), now=NOW)
    costly = featurize(
        _evidence(requires_operator_authority=True, quota_available=False), now=NOW
    )
    assert costly.operator_cost > free.operator_cost


# ------------------------------------------------------------------------------------------
# 5. Staleness is a FLOOR the engine is free to raise -- never double-counted
# ------------------------------------------------------------------------------------------
def test_staleness_floor_tracks_ttl_age() -> None:
    ttl = 3_600
    half = featurize(
        _evidence(observed_at=NOW - timedelta(seconds=ttl // 2), freshness_ttl_s=ttl), now=NOW
    )
    over = featurize(
        _evidence(observed_at=NOW - timedelta(seconds=ttl * 3), freshness_ttl_s=ttl), now=NOW
    )

    assert 0.4 < half.staleness < 0.6
    assert over.staleness == 1.0  # clamped, not unbounded


def test_engine_fold_never_lowers_the_featurized_floor() -> None:
    """_effective_score_vector takes max() of its own derivation and the supplied signals."""
    ttl = 3_600
    evidence = _evidence(
        observed_at=NOW - timedelta(seconds=ttl * 2),
        freshness_ttl_s=ttl,
        recent_duplicate_count=4,
    )
    signals = featurize(evidence, now=NOW)
    observation = TopicInterestObservation(
        observation_id="obs-2",
        source_id="src-2",
        subject="s",
        subject_cluster="c",
        grounding_question="q",
        signals=signals,
        **evidence.model_dump(),
    )

    decision = decide_topic_interest(observation, now=NOW, policy=TopicInterestPolicy())

    assert decision.score_vector.staleness >= signals.staleness
    assert decision.score_vector.duplicate_pressure >= signals.duplicate_pressure


# ------------------------------------------------------------------------------------------
# 6. The vector the featurizer emits is scored by the weights it was built for
# ------------------------------------------------------------------------------------------
def test_positive_weights_still_sum_to_one() -> None:
    """A drift-pin: the featurizer's dimension set is exactly the weighted set."""
    assert sum(POSITIVE_WEIGHTS.values()) == pytest.approx(1.0)

    vector = featurize(_evidence(), now=NOW)
    assert set(POSITIVE_WEIGHTS) <= set(vector.model_dump())


def test_a_risky_unsourced_claim_scores_below_a_clean_sourced_one() -> None:
    clean = featurize(
        _evidence(
            source_kind="research_registry_entry",
            primary_source_count=2,
            official_source_count=2,
            corroborating_source_count=3,
            rights_state="cleared",
            recency_label_present=True,
        ),
        now=NOW,
    )
    risky = featurize(
        _evidence(
            source_kind="external_reference",
            current_event_claim=True,
            sensitive_event=True,
            trend_used_as_truth=True,
            recent_duplicate_count=5,
        ),
        now=NOW,
    )

    assert clean.total_score() > risky.total_score()
