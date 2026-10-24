"""S04 package cases; offline projections, never host observations or admission.

Provenance: Council cef55b5216574f7eb80fd42c887c58e83f7cace0:
* scripts/hapax-platform-capability-receipts:build_receipt and
  tests/shared/test_platform_capability_receipts.py:
  test_receipt_observes_selected_activation_project,
  test_claude_receipt_records_unusable_wrapper_per_route.
* shared/bare_host_capability_observer.py:receipts_for_observation.
The timestamp and /fixture paths below are synthetic bindings. No receipt producer
is executed, no live receipt read, and a parsed observation grants no authority.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta, timezone
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from hapax.spine import platform_capability_receipts as receipts

NOW = datetime(2026, 5, 17, 19, 55, tzinfo=UTC)
SOURCE_SHA = "48a4c42f8838759ec67220ad97f5f54c6bdb6c6b6986bf1444e4b7e59fea6b8e"
ALLOCATION = set("BareHostCliProbeReceiptV1 PlatformCapabilityReceipt ProviderDocsEvidence "
    "SurfaceEvidence ToolEvidence receipt_is_fresh _PYDANTIC_DYNAMIC_ENTRYPOINTS".split())
WRAPPER = dict(path="/fixture/hapax-claude-reviewer", exists=True,
               executable=False, sha256="a" * 64)
LOAD = dict(resolved_roots={"project": "/fixture/activation"}, files=[dict(
    root="project", path="AGENTS.md", observed_path="/fixture/activation/AGENTS.md",
    state="missing", sha256=None)], problems=["missing:project:AGENTS.md"],
    native_loading="unobserved", boundary="host_observation", may_authorize=False)


def surface(**changes):
    value = dict(status="observed", source="local_receipt_probe", observed_at=NOW,
        stale_after="24h", evidence_refs=["local:/fixture/wrapper:exists:true"], reason_codes=[])
    value.update(changes)
    return value


def payload(*, current=False):
    value = dict(receipt_schema=1, receipt_id="synthetic-s04", platform="claude",
        routes=["claude.review.opus"], observed_at=NOW, stale_after="24h",
        cli=dict(binary="claude", available=False), wrapper=copy.deepcopy(WRAPPER),
        capability=surface(status="blocked", reason_codes=["cli_missing_or_unusable"]),
        resource=surface(status="blocked", reason_codes=["wrapper_not_executable"]),
        quota=surface(status="unobservable", evidence_refs=[],
                      reason_codes=["quota_telemetry_unknown"]),
        provider_docs=dict(refs=["https://docs.anthropic.com/en/docs/claude-code/overview"],
                           fetched_at=NOW, stale_after="24h"),
        tool_state=[dict(tool_id="shell", available=False, authority_use=[],
                         evidence_ref="platform-capability-receipt:claude:synthetic-s04")])
    if current:
        value.update(route_wrappers={"claude.review.opus": copy.deepcopy(WRAPPER)},
                     load_sets={"claude.review.opus": copy.deepcopy(LOAD)})
    return value


def bare(outcome="observed", **changes):
    value = dict(receipt_id="synthetic-bare-host", host="podium", cli="claude",
        shape_id="bare-host.podium.claude", outcome=outcome,
        observed_at=NOW if outcome == "observed" else None, stale_after="24h",
        evidence_refs=[] if outcome == "not_observable" else [
            "local_probe:podium:command -v claude -> " + (
                "/usr/bin/claude" if outcome == "observed" else "not-found")],
        blocked_reasons=[] if outcome == "observed" else ["probe_not_supply"])
    value.update(changes)
    return value


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail("receipt schema attempted network, credential or subprocess action")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def test_current_receipt_projection_preserves_support_only_fields(tmp_path):
    value = payload(current=True)
    path = tmp_path / "claude.json"
    path.write_text(json.dumps(value, default=lambda t: t.isoformat()))
    parsed = receipts.load_platform_capability_receipt(path)
    assert parsed.route_wrappers["claude.review.opus"].model_dump() == WRAPPER
    assert parsed.load_sets == value["load_sets"]
    assert parsed.capability.status.value == "blocked"
    assert parsed.resource.reason_codes == ["wrapper_not_executable"]
    assert parsed.quota.status.value == "unobservable" and parsed.quota.evidence_refs == []
    assert parsed.tool_state[0].available is False
    assert parsed.tool_state[0].evidence_ref == value["tool_state"][0]["evidence_ref"]
    assert parsed.observed_at == parsed.provider_docs.fetched_at == NOW
    assert parsed.provider_docs.refs == value["provider_docs"]["refs"]
    assert receipts.receipt_reference(parsed) == "platform-capability-receipt:claude:synthetic-s04"
    assert receipts.load_platform_capability_receipts(tmp_path, now=NOW) == {"claude": parsed}
    restored = receipts.PlatformCapabilityReceipt.model_validate_json(parsed.model_dump_json())
    assert restored == parsed


def test_optional_observation_maps_default_independently():
    first = receipts.PlatformCapabilityReceipt.model_validate(payload())
    second = receipts.PlatformCapabilityReceipt.model_validate(payload())
    assert first.route_wrappers == first.load_sets == {}
    first.load_sets["test"] = {"native_loading": "unobserved"}
    first.route_wrappers["test"] = first.wrapper
    assert second.route_wrappers == second.load_sets == {}


BAD_REFS = ["", "plain-run-id", "a" * 64, "sha256:abc", "hash:abc", "digest:abc",
    "run:abc", "HASH:abc", ":subject", "test:", "bad namespace:x",
    "receipt:AgenticTrustEvidenceReceiptV1:run-1",
    "surface:local_compute/agentic_trust_evaluator_surface"]


@pytest.mark.parametrize("field", ["tool_state", "capability", "resource", "quota", "provider_docs"])
@pytest.mark.parametrize("reference", BAD_REFS)
def test_untyped_or_observation_evidence_refused_at_reader(field, reference, tmp_path):
    value = payload()  # Legacy shape isolates the new reference guard from new fields.
    if field == "tool_state":
        value[field][0]["evidence_ref"] = reference
    elif field == "provider_docs":
        value[field]["refs"] = ["test:valid", reference]
    else:
        value[field]["evidence_refs"] = ["test:valid", reference]
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(value, default=lambda t: t.isoformat()))
    with pytest.raises(receipts.PlatformCapabilityReceiptError, match="namespaced non-observation"):
        receipts.load_platform_capability_receipt(path)


@pytest.mark.parametrize("reference", ["local:/fixture:exists:false", "https://example.test/doc",
    "platform-capability-receipt:claude:receipt-1", "test:opaque-locator"])
def test_typed_references_preserve_exact_identity(reference):
    tool = receipts.ToolEvidence(tool_id="shell", available=False, evidence_ref=reference)
    state = receipts.SurfaceEvidence(**surface(evidence_refs=[reference]))
    docs = receipts.ProviderDocsEvidence(refs=[reference], fetched_at=NOW, stale_after="24h")
    assert tool.evidence_ref == state.evidence_refs[0] == docs.refs[0] == reference


@pytest.mark.parametrize("status", ["blocked", "missing", "unobservable", "error"])
def test_nonobserved_surface_requires_reason(status):
    with pytest.raises(ValidationError, match="requires reason_codes"):
        receipts.SurfaceEvidence(**surface(status=status))
    parsed = receipts.SurfaceEvidence(**surface(status=status, evidence_refs=[], reason_codes=["held"]))
    assert parsed.evidence_refs == [] and parsed.reason_codes == ["held"]


def test_observed_surface_requires_evidence():
    with pytest.raises(ValidationError, match="requires evidence_refs"):
        receipts.SurfaceEvidence(**surface(evidence_refs=[]))


@pytest.mark.parametrize("model", ["surface", "provider", "platform", "bare"])
@pytest.mark.parametrize("duration", ["0s", "-1m", "1.5h", "24H", "forever"])
def test_invalid_durations_refused(model, duration):
    models = {"surface": (receipts.SurfaceEvidence, surface()),
        "provider": (receipts.ProviderDocsEvidence, dict(refs=["test:docs"], fetched_at=NOW, stale_after="24h")),
        "platform": (receipts.PlatformCapabilityReceipt, payload()),
        "bare": (getattr(receipts, "BareHostCliProbeReceiptV1"), bare())}
    cls, value = models[model]
    value["stale_after"] = duration
    with pytest.raises(ValidationError, match="invalid duration spec"):
        cls.model_validate(value)


@pytest.mark.parametrize("outcome", ["observed", "absent", "not_observable"])
def test_bare_host_current_outcomes_preserve_evidence_only_identity(outcome):
    value = bare(outcome)
    parsed = receipts.BareHostCliProbeReceiptV1.model_validate(value)
    assert parsed.receipt_class == "BareHostCliProbeReceiptV1" and parsed.receipt_schema == 1
    assert parsed.shape_id == "bare-host.podium.claude"
    assert parsed.demand_eligible is False
    assert parsed.observed_at == value["observed_at"]
    assert parsed.evidence_refs == value["evidence_refs"]
    assert parsed.blocked_reasons == value["blocked_reasons"]
    assert receipts.BareHostCliProbeReceiptV1.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize("outcome,changes,message", [
    ("observed", {"observed_at": None}, "require observed_at"),
    ("absent", {"observed_at": NOW}, "must not carry observed_at"),
    ("not_observable", {"observed_at": NOW}, "must not carry observed_at"),
    ("absent", {"evidence_refs": []}, "negative-probe evidence_ref"),
    ("not_observable", {"evidence_refs": ["local_probe:unexpected"]}, "must not cite a probe"),
    ("observed", {"demand_eligible": True}, None),
    ("observed", {"receipt_schema": 2}, None),
    ("observed", {"receipt_class": "PlatformCapabilityReceipt"}, None),
    ("invented", {}, None),
])
def test_bare_host_refusals(outcome, changes, message):
    with pytest.raises(ValidationError, match=message):
        receipts.BareHostCliProbeReceiptV1.model_validate(bare(outcome, **changes))


def test_bare_host_receipt_never_enters_platform_overlay(tmp_path):
    parsed = receipts.BareHostCliProbeReceiptV1.model_validate(bare())
    subdir = tmp_path / "bare-host-cli"
    subdir.mkdir()
    (subdir / "probe.json").write_text(parsed.model_dump_json())
    assert receipts.load_platform_capability_receipts(tmp_path, now=NOW) == {}
    (tmp_path / "probe.json").write_text(parsed.model_dump_json())
    with pytest.raises(receipts.PlatformCapabilityReceiptError):
        receipts.load_platform_capability_receipts(tmp_path, now=NOW)


@pytest.mark.parametrize("changes", [
    {"receipt_schema": 2}, {"routes": []},
    {"route_wrappers": {"claude.review.opus": {"path": "missing-flags"}}},
    {"load_sets": {"claude.review.opus": "not-an-observation-map"}},
    {"provider_docs": dict(refs=[], fetched_at=NOW, stale_after="24h")},
])
def test_platform_field_constraints(changes):
    value = payload(current=True)
    value.update(changes)
    with pytest.raises(ValidationError):
        receipts.PlatformCapabilityReceipt.model_validate(value)


@pytest.mark.parametrize("offset_us,expected", [
    (-86400000001, False), (-86400000000, True), (-1, True), (0, True),
    (60000000, True), (60000001, False), (86400000000, False),
])
@pytest.mark.parametrize("clock", ["utc", "offset", "naive"])
def test_receipt_freshness_boundary(offset_us, expected, clock):
    value = payload()
    observed = NOW + timedelta(microseconds=offset_us)
    checked = NOW
    if clock == "offset":
        observed = observed.astimezone(timezone(timedelta(hours=-5)))
        checked = NOW.astimezone(timezone(timedelta(hours=3)))
    elif clock == "naive":
        observed, checked = observed.replace(tzinfo=None), NOW.replace(tzinfo=None)
    value["observed_at"] = observed
    parsed = receipts.PlatformCapabilityReceipt.model_validate(value)
    assert receipts.receipt_is_fresh(parsed, now=checked) is expected


def test_loader_excludes_expired_and_future_receipts(tmp_path):
    for name, offset in [("old", -timedelta(days=2)), ("future", timedelta(minutes=2))]:
        value = payload()
        value.update(receipt_id=name, observed_at=NOW + offset)
        (tmp_path / (name + ".json")).write_text(json.dumps(value, default=lambda t: t.isoformat()))
    assert receipts.load_platform_capability_receipts(tmp_path, now=NOW) == {}


def _parity(filename):
    """Compare allocated definitions against pinned input, including from a wheel."""
    import ast
    import hashlib
    raw = Path(filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA
    def definitions(text):
        result = {}
        for node in ast.parse(text).body:
            name = getattr(node, "name", None)
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            if name in ALLOCATION:
                result[name] = ast.get_source_segment(text, node)
        return result
    expected, actual = definitions(raw.decode()), definitions(Path(receipts.__file__).read_text())
    assert set(expected) == set(actual) == ALLOCATION
    assert expected == actual
    print(json.dumps({"exact_definition_parity": len(actual), "source_sha256": SOURCE_SHA,
                      "package": receipts.__file__}))


def _mutations():
    """Each control must admit an unsafe case; restore exact bytes and rerun green."""
    import ast
    import hashlib
    import os
    import subprocess
    import sys
    import tempfile
    path = Path(__file__).resolve().parents[1] / "src/hapax/spine/platform_capability_receipts.py"
    assert Path(receipts.__file__).resolve() == path.resolve()
    original = path.read_bytes(); source = original.decode(); tree = ast.parse(source)
    controls = []
    def change(label, node, code):
        lines = source.splitlines(keepends=True)
        lines[node.lineno - 1:node.end_lineno] = [" " * node.col_offset + code + "\n"]
        controls.append((label, "".join(lines).encode()))
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ALLOCATION):
        for node in ast.walk(cls):
            code = ast.get_source_segment(source, node)
            if isinstance(node, ast.Raise) and "cannot be demand_eligible" not in code:
                change(cls.name + ":raise:" + str(node.lineno), node, "pass")
            if isinstance(node, ast.Expr) and code == "parse_duration_spec(self.stale_after)":
                change(cls.name + ":duration", node, "pass")
            if isinstance(node, ast.AnnAssign):
                annotation = ast.get_source_segment(source, node.annotation)
                if annotation.startswith("Literal[") and node.target.id != "demand_eligible":
                    change(cls.name + ":literal:" + node.target.id, node,
                           code.replace(annotation, "Any", 1))
                if node.target.id in {"refs", "routes"} and "min_length=1" in code:
                    change(cls.name + ":nonempty:" + node.target.id, node,
                           code.replace("min_length=1", "min_length=0"))
                if node.target.id in {"route_wrappers", "load_sets"}:
                    change(cls.name + ":map:" + node.target.id, node,
                           code.replace(annotation, "dict[str, Any]", 1))
    # The literal and validator redundantly refuse demand: remove both as one control.
    controls.append(("bare-host-demand-boundary", source.replace(
        "demand_eligible: Literal[False]", "demand_eligible: bool").replace(
        'raise ValueError("bare-host CLI probe receipts cannot be demand_eligible")', "pass").encode()))
    controls.append(("future-clock", source.replace(
        "if observed_at > checked_now + timedelta(minutes=1):", "if False:").encode()))
    controls.append(("expired-clock", source.replace(
        "return checked_now - observed_at <= parse_duration_spec(receipt.stale_after)",
        "return True").encode()))
    # Break the loader boundary to show the evidence-only JSON cannot become a receipt.
    controls.append(("bare-host-overlay", source.replace(
        "return PlatformCapabilityReceipt.model_validate(_load_json_object(path))",
        'payload = _load_json_object(path)\n        if payload.get("receipt_class") == "BareHostCliProbeReceiptV1":\n'
        '            return PlatformCapabilityReceipt.model_construct(platform="bare", observed_at=payload["observed_at"], stale_after="24h")\n'
        '        return PlatformCapabilityReceipt.model_validate(payload)').replace(
        "if not receipt_is_fresh(receipt, now=now):", 'if receipt.platform != "bare" and not receipt_is_fresh(receipt, now=now):').encode()))
    def run(label):
        env = os.environ.copy(); env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory(prefix="s04-cache-") as cache:
            env["PYTHONPYCACHEPREFIX"] = cache
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(Path(__file__).resolve())],
                cwd=path.parents[3], env=env, capture_output=True, text=True)
        output = result.stdout + result.stderr
        print(json.dumps({"phase": label, "exit": result.returncode,
                          "output_sha256": hashlib.sha256(output.encode()).hexdigest()}), flush=True)
        print(output, flush=True)
        if label.endswith(":red"):
            assert "DID NOT RAISE" in output or "is False" in output, "must admit unsafe case"
        return result.returncode
    assert run("original-green") == 0
    for label, mutant in controls:
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
                      "restored_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}), flush=True)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--mutation-controls"]:
        _mutations()
    elif len(sys.argv) == 3 and sys.argv[1] == "--parity-source":
        _parity(sys.argv[2])
    else:
        raise SystemExit("use --mutation-controls or --parity-source FILE")
