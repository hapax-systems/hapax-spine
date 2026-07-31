"""Pin the topic-interest engine as extracted from hapax-council/shared.

WHY THIS FILE EXISTS. The featurizer — the per-source-kind mapping from a datum to this vector — is
named in the reins corpus as "the single hard unbuilt piece" and "THE UNBUILT KEYSTONE ... the one
gap shared by all 4 score components. This is the foundational build." A design-recovery pass
reported it as having zero design. That is true of the FEATURIZER and false of everything around it:
the target type, both weight sets, the aggregation and the policy thresholds were fully specified and
sitting in council, unextracted and unimported by reins.

These tests pin the extracted values against the council originals so the extraction cannot drift
silently — hapax-spine and hapax-council/shared have already forked bidirectionally across nine
modules, and this must not become the tenth.
"""

from hapax.spine.topic_interest_engine import (
    PENALTY_WEIGHTS,
    POSITIVE_WEIGHTS,
    TopicInterestPolicy,
    TopicInterestScoreVector,
)


def test_positive_dimensions_are_the_eight():
    """"The 8 topic-interest dimensions" the corpus names means the POSITIVE half; the vector
    carries 13 fields in total, 5 of them penalties."""
    assert set(POSITIVE_WEIGHTS) == {
        "novelty", "surprise", "relevance", "evidence_density",
        "trajectory", "public_value", "research_value", "actionability",
    }
    assert set(PENALTY_WEIGHTS) == {
        "staleness", "rights_privacy_risk", "claim_risk", "duplicate_pressure", "operator_cost",
    }
    assert len(POSITIVE_WEIGHTS) + len(PENALTY_WEIGHTS) == 13


def test_weights_are_the_council_values_and_normalised():
    """The corpus records these weights as 'operator-bound twice, never supplied'. They were
    supplied — here — and each set sums to 1.0. Pinning the exact values so an extraction copy
    cannot drift from the original."""
    assert POSITIVE_WEIGHTS == {
        "novelty": 0.15, "surprise": 0.12, "relevance": 0.16, "evidence_density": 0.17,
        "trajectory": 0.10, "public_value": 0.10, "research_value": 0.12, "actionability": 0.08,
    }
    assert PENALTY_WEIGHTS == {
        "staleness": 0.22, "rights_privacy_risk": 0.28, "claim_risk": 0.24,
        "duplicate_pressure": 0.16, "operator_cost": 0.10,
    }
    assert abs(sum(POSITIVE_WEIGHTS.values()) - 1.0) < 1e-9
    assert abs(sum(PENALTY_WEIGHTS.values()) - 1.0) < 1e-9


def test_aggregation_is_positive_minus_penalty_at_0_55_clamped():
    v = TopicInterestScoreVector(
        novelty=1.0, surprise=1.0, relevance=1.0, evidence_density=1.0,
        trajectory=1.0, public_value=1.0, research_value=1.0, actionability=1.0,
    )
    assert abs(v.positive_score() - 1.0) < 1e-9
    assert v.penalty_score() == 0.0
    assert abs(v.total_score() - 1.0) < 1e-9

    penalised = v.model_copy(update={"rights_privacy_risk": 1.0})
    assert abs(penalised.total_score() - (1.0 - 0.55 * 0.28)) < 1e-9


def test_total_score_is_clamped_to_unit_interval():
    """Relevant to reins: Importance() is an unbounded product while clamp01(0.18 + 0.27*salience)
    presumes salience in [0,1]. total_score() is already clamped, which may be the intended
    normalisation — untested against the reins consumer, but the clamp is real."""
    worst = TopicInterestScoreVector(
        novelty=0.0, surprise=0.0, relevance=0.0, evidence_density=0.0,
        trajectory=0.0, public_value=0.0, research_value=0.0, actionability=0.0,
        staleness=1.0, rights_privacy_risk=1.0, claim_risk=1.0,
        duplicate_pressure=1.0, operator_cost=1.0,
    )
    assert 0.0 <= worst.total_score() <= 1.0


def test_policy_thresholds_are_the_council_defaults():
    """Candidate answer to the corpus's 'BREAKS cut-points are nowhere'. CAUTION: these were
    authored for a publication pipeline (watch -> research -> frame -> content -> operator_question),
    NOT for cockpit display tiers. Reusing the vector is well founded; reusing these as display
    BREAKS is an assumption to be tested against scored cockpit data, not inherited."""
    p = TopicInterestPolicy()
    assert (p.watch_threshold, p.research_threshold, p.frame_threshold,
            p.content_threshold, p.operator_question_threshold) == (0.25, 0.45, 0.60, 0.70, 0.78)


def test_no_residual_council_namespace_in_the_extraction():
    """The extraction rewrote `shared.*` to `hapax.spine.*`. A residual import would make the wheel
    depend on a repo it does not ship with."""
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "hapax" / "spine"
    for mod in ("topic_interest_engine", "content_candidate_discovery",
                "trend_current_event_gate", "impingement"):
        src = (root / f"{mod}.py").read_text()
        assert "from shared." not in src, mod
        assert "import shared." not in src, mod
