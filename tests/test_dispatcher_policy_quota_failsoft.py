"""Quota fixture fail-soft regression for the package path Reins imports."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

import hapax.spine.dispatcher_policy as dispatcher_policy


NOW = datetime(2026, 7, 5, 16, 0, tzinfo=UTC)
REGISTRY = Path(__file__).parent / "fixtures" / "platform-capability-registry.json"


def test_policy_sources_fail_soft_when_quota_fixture_resolution_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_fixture_resolution(*, live_path: Path | None = None) -> object:
        raise RuntimeError(
            "hapax-spine: cannot load 'quota-spend-ledger-fixtures.json' "
            "-- set HAPAX_SPINE_CONFIG_DIR"
        )

    monkeypatch.setattr(
        dispatcher_policy,
        "load_quota_spend_ledger_resolved",
        fail_fixture_resolution,
    )
    receipt = dispatcher_policy.build_route_authority_receipt(
        receipt_type="runtime_actuation",
        route_id="codex.headless.full",
        evidence_refs=["route-authority-receipt:test-feed-1e"],
        task_ids=["cc-task-hapax-spine-quota-fixture-failsoft-capability-plane-20260705"],
        mutation_surfaces=["runtime"],
        receipt_id="test-feed-1e-runtime-actuation",
        issued_at=NOW,
    )
    dispatcher_policy.write_route_authority_receipt(receipt, receipt_dir=tmp_path)

    sources = dispatcher_policy.load_dispatch_policy_sources(
        registry_path=REGISTRY,
        receipt_dir=tmp_path,
        now=NOW,
    )

    assert sources.registry is not None
    assert sources.registry.routes
    assert sources.registry_error is None
    assert sources.route_authority_receipts == (receipt,)
    assert sources.quota_ledger is None
    assert sources.quota_ledger_source is None
    assert sources.quota_error is not None
    assert "quota-spend-ledger-fixtures.json" in sources.quota_error


def test_policy_sources_do_not_mask_unexpected_quota_runtime_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_unexpectedly(*, live_path: Path | None = None) -> object:
        raise RuntimeError("unexpected quota resolver bug")

    monkeypatch.setattr(
        dispatcher_policy,
        "load_quota_spend_ledger_resolved",
        fail_unexpectedly,
    )

    with pytest.raises(RuntimeError, match="unexpected quota resolver bug"):
        dispatcher_policy.load_dispatch_policy_sources(registry_path=REGISTRY)
