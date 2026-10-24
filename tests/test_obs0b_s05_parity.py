"""S05 offline schema projections and their existing package consumer boundaries.

Council cef55b5216574f7eb80fd42c887c58e83f7cace0 provenance:
shared/quota_headroom.py:enrich_ledger adds route-less measurement-only rows;
tests/shared/test_quota_headroom.py:test_schema_v1_migration_and_old_reader_projection
pins the explicit downgrade. Names, quantities and timestamps here are synthetic.
No live ledger, credential, host probe or provider API is used.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hapax.spine import quota_spend_ledger as ledger

NOW = datetime(2026, 9, 19, 8, tzinfo=UTC)
ALLOCATION = set("ModelId PaidRouteRequest QuotaMeasurement QuotaSnapshot QuotaSpendLedger".split())
SOURCE_SHA = "af36db38998389b26445bf05733b42752e7e57e16d838fe1cb6811a0e26e912e"
FIXTURE_SHA = "81b0ee8c9799d5e5a6a69602f5b0f13b5a8fb40b9ae3a56b597e496b696830fd"


def measurement(**changes):
    value = dict(capacity_id="codex.subscription.weekly", quantity=40, unit="percent_used",
        window="10080m", resets_at=NOW + timedelta(days=1), label="observed",
        source="fixture:token_count", observed_at=NOW,
        measurement_fresh_until=NOW + timedelta(minutes=5))
    value.update(changes)
    return value


def snapshot(*, current=False, **changes):
    value = dict(snapshot_id="quota-test", captured_at=NOW,
        fresh_until=NOW + timedelta(minutes=5), route_id="codex.headless.full",
        provider="codex", capacity_pool="subscription_quota", subscription_quota_state="fresh",
        evidence_refs=["fixture:quota"], operator_visible_reason="Synthetic quota observation")
    if current:
        value.update(measurement(), quota_snapshot_schema=2, family="codex",
                     stage="declared-measured", admission_compatible=False,
                     measurements=[measurement(label="wall-signal", quantity=None)])
    value.update(changes)
    return value


def payload(**changes):
    value = dict(schema_version=1, ledger_id="synthetic-s05", captured_at=NOW,
        authority_source="isap:quota-spend-ledger-20260509", generated_from=["fixture:s05"],
        consumer_permission_after="private_capacity_routing_tests_only",
        evidence_refs=["fixture:s05"], quota_snapshots=[])
    value.update(changes)
    return value


def paid(**changes):
    value = dict(route_id="api.headless.api_frontier", task_id="task-a", provider="example",
        profile="review", task_class="independent-review", quality_floor="frontier_review_required",
        estimated_cost_usd="0.05", capacity_pool="api_paid_spend")
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail("ledger schema attempted network, credential or subprocess action")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def test_current_schema2_projection_roundtrips_without_admission(tmp_path):
    unknown = snapshot(current=True, snapshot_id="quota-grok-measurement", family="grok",
        route_id=None, provider="grok", stage="usable-undeclared",
        subscription_quota_state="unknown", quantity=None, label="unobserved",
        observed_at=None, reason_code="no_local_quantity_reader")
    report = measurement(label="operator-reported", quantity=None, source="operator:report",
                         details={"reset_as_reported": "time zone unspecified"})
    raw = payload(schema_version=2, quota_snapshots=[snapshot(current=True), unknown],
        freeze={"frozen": True, "families": ["codex"]}, operator_reports=[report])
    path = tmp_path / "ledger.json"
    path.write_text(json.dumps(raw, default=lambda t: t.isoformat()))
    parsed = ledger.load_quota_spend_ledger(path)
    assert parsed.schema_version == 2 and parsed.freeze == raw["freeze"]
    assert parsed.quota_snapshots[0].quantity == 40
    assert parsed.quota_snapshots[0].measurements[0].label == "wall-signal"
    assert all(not s.admission_compatible for s in parsed.quota_snapshots)
    assert parsed.quota_snapshots[1].route_id is None
    assert parsed.quota_snapshots[1].stage == "usable-undeclared"
    assert parsed.operator_reports[0].details == report["details"]
    assert parsed.operator_reports[0].quantity is None
    assert parsed.operator_reports[0].observed_at == NOW
    assert ledger.QuotaSpendLedger.model_validate_json(parsed.model_dump_json()) == parsed


def test_legacy_snapshot_defaults_remain_explicitly_unmeasured():
    value = ledger.QuotaSnapshot.model_validate(snapshot())
    assert value.capacity_id == "legacy.unmeasured"
    assert value.reason_code == "legacy_binary_snapshot" and value.label == "unobserved"
    assert value.admission_compatible and value.quantity is None
    assert value.measurements == ()
    assert not value.measurement_is_fresh(NOW)


@pytest.mark.parametrize("label,quantity", [
    ("observed", 0), ("derived", 0.5), ("wall-signal", None),
    ("operator-reported", None), ("unobserved", None),
])
def test_measurement_labels_retain_quantity_and_source(label, quantity):
    raw = measurement(label=label, quantity=quantity, reason_code="no_local_quantity_reader")
    parsed = ledger.QuotaMeasurement.model_validate(raw)
    assert parsed.label == label and parsed.quantity == quantity
    assert parsed.source == raw["source"] and parsed.observed_at == NOW


@pytest.mark.parametrize("changes,message", [
    ({"label": "observed", "quantity": None}, "require a quantity"),
    ({"label": "derived", "quantity": None}, "require a quantity"),
    ({"label": "wall-signal", "quantity": 0}, "cannot become a fraction"),
    ({"label": "unobserved", "quantity": 1}, "cannot become a fraction"),
    ({"observed_at": None}, "source time"),
    ({"label": "operator-reported", "observed_at": None}, "source time"),
    ({"label": "unobserved", "quantity": None, "reason_code": None}, "reason_code"),
    ({"label": "unobserved", "quantity": None, "reason_code": ""}, "reason_code"),
])
def test_measurement_semantic_refusals(changes, message):
    with pytest.raises(ValidationError, match=message):
        ledger.QuotaMeasurement.model_validate(measurement(**changes))


@pytest.mark.parametrize("field", ["resets_at", "observed_at", "measurement_fresh_until"])
def test_measurement_clock_requires_timezone(field):
    with pytest.raises(ValidationError, match="timezone-aware"):
        ledger.QuotaMeasurement.model_validate(measurement(**{field: NOW.replace(tzinfo=None)}))


@pytest.mark.parametrize("changes", [
    {"capacity_id": ""}, {"label": "invented"}, {"quantity": float("nan")},
    {"quantity": float("inf")}, {"quantity": -float("inf")},
])
def test_measurement_field_constraints(changes):
    with pytest.raises(ValidationError):
        ledger.QuotaMeasurement.model_validate(measurement(**changes))


def test_measurement_identity_is_required():
    raw = measurement(); del raw["capacity_id"]
    with pytest.raises(ValidationError):
        ledger.QuotaMeasurement.model_validate(raw)


@pytest.mark.parametrize("offset_us,fresh", [(-1, False), (0, True), (299999999, True), (300000000, False)])
def test_measurement_freshness_interval(offset_us, fresh):
    parsed = ledger.QuotaMeasurement.model_validate(measurement())
    assert parsed.measurement_is_fresh(NOW + timedelta(microseconds=offset_us)) is fresh


@pytest.mark.parametrize("field", ["observed_at", "measurement_fresh_until"])
def test_missing_measurement_clock_cannot_be_fresh(field):
    parsed = ledger.QuotaMeasurement.model_validate(measurement(
        label="unobserved", quantity=None, reason_code="absent", **{field: None}))
    assert parsed.measurement_is_fresh(NOW) is False


@pytest.mark.parametrize("changes,message", [
    ({"route_id": None, "admission_compatible": True}, "cannot carry route admission"),
    ({"captured_at": NOW.replace(tzinfo=None), "fresh_until": None}, "timezone-aware"),
    ({"fresh_until": NOW.replace(tzinfo=None)}, "timezone-aware"),
    ({"fresh_until": NOW}, "after captured_at"),
])
def test_snapshot_refusals(changes, message):
    with pytest.raises(ValidationError, match=message):
        ledger.QuotaSnapshot.model_validate(snapshot(current=True, **changes))


@pytest.mark.parametrize("field,value", [
    ("quota_snapshot_schema", 3), ("stage", "admitted-by-observation"), ("owner", "caller"),
    ("route_id", ""), ("evidence_refs", []), ("snapshot_id", "bad"),
])
def test_snapshot_field_constraints(field, value):
    with pytest.raises(ValidationError):
        ledger.QuotaSnapshot.model_validate(snapshot(current=True, **{field: value}))


@pytest.mark.parametrize("field", ["route_id", "provider", "profile", "task_class", "quality_floor"])
@pytest.mark.parametrize("marker", ["local_compute.agentic_trust_evaluator_surface",
    "receipt:AgenticTrustEvidenceReceiptV1:test"])
def test_observation_identity_cannot_define_paid_eligibility(field, marker):
    with pytest.raises(ValidationError, match="agentic-trust observation evidence"):
        ledger.PaidRouteRequest.model_validate(paid(**{field: marker}))


@pytest.mark.parametrize("missing", [True, False])
def test_paid_request_requires_task_identity(missing):
    raw = paid(); raw.pop("task_id")
    if not missing:
        raw["task_id"] = ""
    with pytest.raises(ValidationError):
        ledger.PaidRouteRequest.model_validate(raw)


@pytest.mark.parametrize("field", ["task_id", "quality_floor"])
@pytest.mark.parametrize("value", ["/private/path", "~/private/path", "test@example.invalid"])
def test_paid_new_reference_fields_refuse_private_identity(field, value):
    with pytest.raises(ValidationError, match="repo-relative|email addresses"):
        ledger.PaidRouteRequest.model_validate(paid(**{field: value}))


@pytest.mark.parametrize("changes", [{"capacity_pool": "subscription_quota"}, {"estimated_cost_usd": "0"}])
def test_paid_request_still_refuses_wrong_pool_or_zero_cost(changes):
    with pytest.raises(ValidationError):
        ledger.PaidRouteRequest.model_validate(paid(**changes))


def test_model_id_value_set_tracks_admitted_registry():
    from hapax.spine.platform_capability_registry import ModelId
    assert {x.value for x in ledger.ModelId} == {x.value for x in ModelId}
    assert ledger.PaidRouteRequest.model_validate(paid()).task_id == "task-a"


def test_schema_v1_projection_drops_only_measurement_rows_and_extensions():
    compatible = snapshot(snapshot_id="quota-compatible")
    measured = snapshot(current=True, snapshot_id="quota-measured")
    undeclared = snapshot(current=True, snapshot_id="quota-undeclared", route_id=None)
    parsed = ledger.QuotaSpendLedger.model_validate(payload(schema_version=2,
        quota_snapshots=[compatible, measured, undeclared], freeze={"frozen": True},
        operator_reports=[measurement()]))
    old = parsed.schema_v1_payload()
    assert old["schema_version"] == 1 and "freeze" not in old and "operator_reports" not in old
    assert len(old["quota_snapshots"]) == 1
    expected = {"quota_snapshot_schema": 1, **compatible}
    assert old["quota_snapshots"][0] == json.loads(json.dumps(expected, default=lambda t: t.isoformat().replace('+00:00', 'Z')))
    assert parsed.schema_version == 2 and len(parsed.quota_snapshots) == 3
    assert parsed.freeze == {"frozen": True} and len(parsed.operator_reports) == 1
    restored = ledger.QuotaSpendLedger.model_validate(old)
    assert restored.quota_snapshots[0].route_id == compatible["route_id"]


@pytest.mark.parametrize("schema", [0, 3])
def test_unknown_ledger_schema_refuses(schema):
    with pytest.raises(ValidationError):
        ledger.QuotaSpendLedger.model_validate(payload(schema_version=schema))


def test_ledger_nested_measurement_refuses_bad_identity():
    with pytest.raises(ValidationError):
        ledger.QuotaSpendLedger.model_validate(payload(schema_version=2,
            operator_reports=[measurement(capacity_id="")]))


def test_duplicate_snapshot_ids_still_refuse():
    with pytest.raises(ValidationError, match="must be unique"):
        ledger.QuotaSpendLedger.model_validate(payload(quota_snapshots=[snapshot(), snapshot()]))


def test_task_spend_is_exactly_scoped_by_budget_and_task():
    fixture = json.loads((Path(__file__).parent / "fixtures/quota-spend-ledger-fixtures.json").read_text())
    first = fixture["transition_budgets"][0]
    other = {**first, "budget_id": "tb-20260919-other"}
    spends = []
    for index, (budget, task, cost) in enumerate([
        (first, "task-a", "0.01"), (first, "task-a", "0.02"),
        (first, "task-aa", "10.00"), (other, "task-a", "20.00"),
    ]):
        value = copy.deepcopy(fixture["spend_receipts"][0])
        value.update(spend_id=f"spend-20260919T080000Z-{index}", budget_id=budget["budget_id"],
                     task_id=task, estimated_cost_usd=cost)
        spends.append(value)
    parsed = ledger.QuotaSpendLedger.model_validate(payload(
        transition_budgets=[first, other], spend_receipts=spends))
    budget = parsed.budget_by_id(first["budget_id"])
    assert parsed._budget_spent_for_task_usd(budget, "task-a") == Decimal("0.03")
    assert parsed._budget_spent_for_task_usd(budget, "task-aa") == Decimal("10.00")
    assert parsed._budget_spent_for_task_usd(budget, "missing") == Decimal("0")


def test_integration_measurement_only_row_cannot_supply_aggregate_quota():
    parsed = ledger.QuotaSpendLedger.model_validate(payload(schema_version=2,
        quota_snapshots=[snapshot(current=True)]))
    assert ledger.build_dashboard(parsed, now=NOW).subscription_quota_state.value == "unknown"


@pytest.mark.parametrize("route_id", [None, "codex.headless.full"])
def test_integration_measurement_only_row_cannot_supply_route_quota(route_id):
    parsed = ledger.QuotaSpendLedger.model_validate(payload(schema_version=2,
        quota_snapshots=[snapshot(current=True, route_id=route_id)]))
    state, refs = ledger.subscription_quota_state_for_route(parsed, "codex.headless.full", now=NOW)
    assert state.value == "unknown"
    assert refs == ("quota-snapshot:codex.headless.full:missing",)


def test_integration_dispatcher_retains_paid_task_identity(monkeypatch):
    from hapax.spine import dispatcher_policy as dispatcher
    seen = []
    real_request = ledger.PaidRouteRequest
    def capture(**kwargs):
        parsed = real_request(**kwargs); seen.append(parsed); return parsed
    monkeypatch.setattr(dispatcher, "PaidRouteRequest", capture)
    result = dispatcher._quota_state(ledger.QuotaSpendLedger.model_validate(payload()), None,
        capability=dispatcher.RouteCapabilityState(route_id="api.headless.api_frontier",
            supported=True, capacity_pool="api_paid_spend", paid_provider="example"),
        metadata=dispatcher.assess_route_metadata({}), task_id="task-a", authority_case=None, now=NOW)
    assert seen[0].task_id == "task-a"
    assert result.available and result.paid_route_eligibility_state == "refused_no_matching_budget"


def _parity(filename):
    import ast
    import hashlib
    raw = Path(filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA
    def definitions(text):
        return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body
                if isinstance(n, ast.ClassDef) and n.name in ALLOCATION}
    expected, actual = definitions(raw.decode()), definitions(Path(ledger.__file__).read_text())
    assert set(expected) == set(actual) == ALLOCATION
    assert all(ast.dump(ast.parse(expected[k])) == ast.dump(ast.parse(actual[k])) for k in ALLOCATION)
    print(json.dumps({"ast_definition_parity": len(actual),
                      "byte_equal_definitions": sum(expected[k] == actual[k] for k in ALLOCATION), "source_sha256": SOURCE_SHA,
                      "package": ledger.__file__}))


def _current_fixture(filename):
    import hashlib
    raw = Path(filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == FIXTURE_SHA
    original = json.loads(raw)
    parsed = ledger.load_quota_spend_ledger(Path(filename))
    assert parsed.schema_version == 1
    for key in ("quota_snapshots", "transition_budgets", "spend_receipts", "spend_gate_decisions",
                "provider_dependencies", "artifact_provenance", "renewal_records"):
        assert len(getattr(parsed, key)) == len(original.get(key, []))
    for before, after in zip(original["quota_snapshots"], parsed.quota_snapshots, strict=True):
        assert (after.route_id, after.subscription_quota_state.value) == (
            before["route_id"], before["subscription_quota_state"])
        assert after.capacity_id == "legacy.unmeasured" and after.quantity is None
        assert after.admission_compatible and not after.measurement_is_fresh(NOW)
    print(json.dumps({"fixture_sha256": FIXTURE_SHA,
        "snapshots": len(parsed.quota_snapshots), "budgets": len(parsed.transition_budgets),
        "spends": len(parsed.spend_receipts), "no_measurements_fabricated": True,
        "package": ledger.__file__}))


def _mutations():
    """Schema and admitted consumer closure: unsafe mutation red, exact restore green."""
    import ast
    import hashlib
    import os
    import subprocess
    import sys
    import tempfile
    path = Path(__file__).resolve().parents[1] / "src/hapax/spine/quota_spend_ledger.py"
    assert Path(ledger.__file__).resolve() == path.resolve()
    original = path.read_bytes(); source = original.decode(); tree = ast.parse(source)
    controls = []
    def change(label, node, code):
        lines = source.splitlines(keepends=True)
        lines[node.lineno - 1:node.end_lineno] = [" " * node.col_offset + code + "\n"]
        controls.append((label, "".join(lines).encode()))
    selected = {"QuotaMeasurement", "QuotaSnapshot", "PaidRouteRequest"}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ALLOCATION):
        for node in ast.walk(cls):
            code = ast.get_source_segment(source, node)
            if isinstance(node, ast.Raise) and cls.name in selected:
                change(cls.name + ":raise:" + str(node.lineno), node, "pass")
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                name = getattr(node.value.func, "id", "")
                if (cls.name in selected and name in {"_require_aware", "_reject_private_or_identity_refs"}
                    and (name != "_reject_private_or_identity_refs" or cls.name == "PaidRouteRequest")):
                    # Simply dropping this clock check hits Python's mixed-zone comparison;
                    # the unsafe alternative is silently interpreting a naive expiry as UTC.
                    broken = ('object.__setattr__(self, "fresh_until", self.fresh_until.replace(tzinfo=UTC))'
                              if code == '_require_aware(self.fresh_until, "fresh_until")' else "pass")
                    change(cls.name + ":call:" + str(node.lineno), node, broken)
                if name == "_require_unique" and '"quota snapshot_id"' in code:
                    change("duplicate-snapshot-id", node, "pass")
            if isinstance(node, ast.AnnAssign):
                field = node.target.id
                annotation = ast.get_source_segment(source, node.annotation)
                if field in {"label", "stage", "owner", "schema_version", "quota_snapshot_schema"}:
                    change(cls.name + ":literal:" + field, node, code.replace(annotation, "Any", 1))
                if (cls.name, field) in {("QuotaMeasurement", "capacity_id"),
                    ("PaidRouteRequest", "task_id"), ("QuotaSnapshot", "route_id"),
                    ("QuotaSnapshot", "evidence_refs")}:
                    change(cls.name + ":nonempty:" + field, node, code.replace("min_length=1", "min_length=0"))
                if (cls.name, field) in {("QuotaMeasurement", "capacity_id"), ("PaidRouteRequest", "task_id")}:
                    change(cls.name + ":required:" + field, node,
                           code.replace("Field(", 'Field(default="synthetic", ', 1))
                if cls.name == "QuotaMeasurement" and field == "quantity":
                    change("finite-quantity", node, code.replace("allow_inf_nan=False", "allow_inf_nan=True"))
                if cls.name == "PaidRouteRequest" and field == "estimated_cost_usd":
                    change("positive-cost", node, code.replace("gt=", "ge="))
                if cls.name == "QuotaSnapshot" and field == "snapshot_id":
                    change("snapshot-id-pattern", node, 'snapshot_id: str')
    def replace(label, old, new):
        assert source.count(old) == 1, label
        controls.append((label, source.replace(old, new).encode()))
    replace("measurement-window-start", "self.observed_at <= now < self.measurement_fresh_until",
            "now < self.measurement_fresh_until")
    replace("measurement-window-end", "self.observed_at <= now < self.measurement_fresh_until",
            "self.observed_at <= now <= self.measurement_fresh_until")
    start = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "measurement_is_fresh")
    return_node = next(n for n in ast.walk(start) if isinstance(n, ast.Return))
    change("missing-measurement-clocks", return_node, "return True")
    replace("downgrade-excludes-measurements", 'if row["admission_compatible"] and row["route_id"] is not None',
            'if row["route_id"] is not None')
    replace("downgrade-ledger-version", 'payload["schema_version"] = 1', 'payload["schema_version"] = 2')
    replace("downgrade-snapshot-version", '{"quota_snapshot_schema": 1, **{key: row[key] for key in fields}}',
            '{"quota_snapshot_schema": 2, **{key: row[key] for key in fields}}')
    replace("downgrade-snapshot-fields", '**{key: row[key] for key in fields}', '**row')
    for field in ("freeze", "operator_reports"):
        replace("downgrade-" + field, 'payload.pop("' + field + '")', "pass")
    replace("task-scoped-spend", "if receipt.task_id == task_id", "if True")
    replace("budget-scoped-spend", "if receipt.budget_id == budget.budget_id", "if True")
    for name in ("_subscription_quota_state", "subscription_quota_state_for_route"):
        node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
        code = ast.get_source_segment(source, node)
        replace(name + ":admission", code,
                code.replace("if snapshot.admission_compatible\n        and ", "if ", 1))
    controls = [(label, path, mutant) for label, mutant in controls]
    caller = path.with_name("dispatcher_policy.py")
    caller_bytes = caller.read_bytes()
    caller_source = caller_bytes.decode()
    before = "route_id=capability.route_id,\n            task_id=task_id,"
    assert caller_source.count(before) == 1
    controls.append(("caller-task-identity", caller,
        caller_source.replace(before, before.replace("task_id=task_id", 'task_id="wrong-task"')).encode()))
    originals = {path: original, caller: caller_bytes}
    def run(label):
        env = os.environ.copy(); env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory(prefix="s05-cache-") as cache:
            env["PYTHONPYCACHEPREFIX"] = cache
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(Path(__file__).resolve())],
                cwd=path.parents[3], env=env, capture_output=True, text=True)
        output = result.stdout + result.stderr
        print(json.dumps({"phase": label, "exit": result.returncode,
                          "output_sha256": hashlib.sha256(output.encode()).hexdigest()}), flush=True)
        print(output, flush=True)
        if label.endswith(":red"):
            assert "DID NOT RAISE" in output or "AssertionError" in output, "requires unsafe admission or wrong value"
        return result.returncode
    assert run("original-green") == 0
    for label, path, mutant in controls:
        original = originals[path]
        assert mutant != original
        try:
            assert path.read_bytes() == original
            path.write_bytes(mutant)
            print(json.dumps({"mutation": label, "original_sha256": hashlib.sha256(original).hexdigest(),
                              "mutant_sha256": hashlib.sha256(mutant).hexdigest()}), flush=True)
            assert run(label + ":red") == 1, "requires assertion failure, not collection error"
        finally:
            path.write_bytes(original)
        assert path.read_bytes() == original
        assert run(label + ":restored-green") == 0
    print(json.dumps({"controls": len(controls), "all_killed_and_restored": True,
        "restored_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}}), flush=True)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--mutation-controls"]:
        _mutations()
    elif len(sys.argv) == 3 and sys.argv[1] == "--parity-source":
        _parity(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "--fixture-source":
        _current_fixture(sys.argv[2])
    else:
        raise SystemExit("use --mutation-controls, --parity-source FILE or --fixture-source FILE")
