"""S02a schema/read parity, pinned to Council cef55b5216574f7eb80fd42c887c58e83f7cace0.

PRODUCER is the exact _live_producer_payload() contract vector from
 tests/shared/test_capability_surface_delta.py, SHA256
 ab205e457fd1d93492ede5297aa6f8900e0ac43e71fd85465cddcd0b0665b93e.
It is a producer-format unit vector, not a runtime observation. Other cases
below are explicit adversarial variants. Reference strings are schema-typed,
not authenticated or required to belong to a newly invented namespace.
Run --mutation-controls explicitly in a source checkout to break/restore guards.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
import importlib
import json

import pytest
from pydantic import ValidationError

PRODUCER = {'schema_version': 1,
 'schema_ref': 'schemas/capability-surface-delta.schema.json',
 'generated_from': ['unit-test'],
 'declared_at': '2026-07-01T04:30:00Z',
 'descriptors': [{'descriptor_schema': 1,
                  'surface_id': 'route.codex.headless.full',
                  'descriptor_ref': 'platform-capability-registry:codex.headless.full',
                  'surface_kind': 'model_route',
                  'authority_ceiling': 'authoritative',
                  'observed_at': '2026-07-01T04:00:00Z',
                  'stale_after': '1h',
                  'evidence_refs': ['test:descriptor'],
                  'route_id': 'codex.headless.full',
                  'resource_pools': ['subscription_quota']}],
 'deltas': [{'delta_schema': 1,
             'delta_id': 'test:single-stale-codex',
             'source': 'unit-test',
             'observed_at': '2026-07-01T04:30:00Z',
             'detected_by': 'unit-test',
             'surface_id': 'route.codex.headless.full',
             'delta_kind': 'stale_determination',
             'prior_descriptor_ref': 'platform-capability-registry:codex.headless.full',
             'observed_descriptor_ref': 'platform-capability-receipt:codex:expired',
             'evidence_refs': ['test:expired'],
             'authority_ceiling': 'authoritative',
             'affected_resource_pools': ['subscription_quota'],
             'privacy_sensitive': True,
             'public_egress': False,
             'money_rail': False,
             'freshness_state': 'stale',
             'required_intake_action': 'refresh_receipt',
             'remediation_ref': 'cc-task-capability-freshness-remediation-and-discovery-automation-20260630',
             'summary': 'single live producer row'}]}


def api():
    # Import in the test body so the absent baseline is a retained test failure.
    return importlib.import_module("hapax.spine.capability_surface_delta")


def delta(kind="stale_determination", **overrides):
    value = copy.deepcopy(PRODUCER["deltas"][0])
    value["delta_kind"] = kind
    if kind == "new_capability":
        value.update(prior_descriptor_ref=None, freshness_state="delta_pending",
                     required_intake_action="mint_intake_item")
    elif kind == "absent_determination":
        value.update(observed_descriptor_ref=None, freshness_state="absent",
                     required_intake_action="quarantine_surface")
    elif kind != "stale_determination":
        value.update(freshness_state="delta_pending", required_intake_action="update_descriptor")
    value.update(overrides)
    return value


def test_current_producer_read_is_not_fixture_coverage_or_admission(tmp_path):
    m = api()
    path = tmp_path / "producer.json"
    path.write_text(json.dumps(PRODUCER))
    result = m.load_capability_surface_delta_file(path)
    assert result.fixture_set_id is None
    assert len(result.deltas) == 1
    assert result.deltas[0].delta_id == "test:single-stale-codex"
    assert result.deltas[0].freshness_state is m.FreshnessState.STALE
    assert not result.deltas[0].allows_demand_fulfillment()
    assert result.descriptors[0].route_id == "codex.headless.full"
    assert result.generated_from == ["unit-test"]


@pytest.mark.parametrize("kind", [
    "new_capability", "descriptor_changed", "authority_changed", "resource_pool_changed",
    "public_egress_changed", "money_rail_changed", "harness_boundary_changed",
    "orchestration_child_changed", "stale_determination", "absent_determination",
])
def test_actionable_delta_kinds_remain_nonfulfilling(kind):
    value = api().CapabilitySurfaceDelta.model_validate(delta(kind))
    assert value.delta_kind.value == kind
    assert not value.allows_demand_fulfillment()


# Each row breaks one guard on an otherwise valid delta. The mutation runner
# removes each of the twelve corresponding raises separately.
BAD_BINDINGS = [
    ("new_capability", "prior_descriptor_ref", "registered:prior", "prior_descriptor_ref=null"),
    ("new_capability", "required_intake_action", "update_descriptor", "mint_intake_item"),
    ("new_capability", "freshness_state", "fresh", "delta_pending"),
    ("stale_determination", "prior_descriptor_ref", None, "prior_descriptor_ref"),
    ("stale_determination", "observed_descriptor_ref", None, "observed_descriptor_ref"),
    ("authority_changed", "required_intake_action", "none", "descriptor update or intake"),
    ("authority_changed", "freshness_state", "fresh", "delta_pending"),
    ("stale_determination", "required_intake_action", "none", "refresh_receipt"),
    ("stale_determination", "freshness_state", "fresh", "stale freshness_state"),
    ("absent_determination", "required_intake_action", "none", "intake or quarantine"),
    ("absent_determination", "freshness_state", "fresh", "absent freshness_state"),
    ("stale_determination", "remediation_ref", None, "remediation_ref"),
]


@pytest.mark.parametrize("kind,field,value,message", BAD_BINDINGS)
def test_action_surface_bindings_refuse(kind, field, value, message):
    m = api()
    payload = delta(kind)
    m.CapabilitySurfaceDelta.model_validate(payload)
    payload[field] = value
    with pytest.raises(ValidationError, match=message):
        m.CapabilitySurfaceDelta.model_validate(payload)


@pytest.mark.parametrize("owner,field,value", [
    ("file", "schema_version", 2), ("file", "schema_ref", "schemas/unknown.json"),
    ("descriptor", "descriptor_schema", 2), ("delta", "delta_schema", 2),
    ("file", "generated_from", []), ("file", "generated_from", [""]),
    ("file", "descriptors", []), ("file", "deltas", []),
    ("descriptor", "evidence_refs", []), ("descriptor", "evidence_refs", [""]),
    ("descriptor", "evidence_refs", [{"claim": "untyped"}]),
    ("delta", "evidence_refs", []), ("delta", "evidence_refs", [""]),
    ("delta", "evidence_refs", [17]), ("delta", "affected_resource_pools", [""]),
    ("descriptor", "route_id", ""), ("descriptor", "model_id", ""),
    ("delta", "remediation_ref", ""), ("delta", "surface_id", ""),
])
def test_schema_and_evidence_refuse(tmp_path, owner, field, value):
    m = api()
    payload = copy.deepcopy(PRODUCER)
    target = payload if owner == "file" else payload[owner + "s"][0]
    target[field] = value
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(m.CapabilitySurfaceDeltaError, match=field):
        m.load_capability_surface_delta_file(path)


@pytest.mark.parametrize("owner", ["file", "descriptor", "delta"])
def test_unknown_fields_refuse(tmp_path, owner):
    m = api()
    payload = copy.deepcopy(PRODUCER)
    target = payload if owner == "file" else payload[owner + "s"][0]
    target["unreviewed_authority"] = "admitted"
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(m.CapabilitySurfaceDeltaError, match="unreviewed_authority"):
        m.load_capability_surface_delta_file(path)


@pytest.mark.parametrize("field", ["privacy_sensitive", "public_egress", "money_rail"])
def test_governance_flags_must_be_explicit(field):
    m = api()
    payload = delta()
    del payload[field]
    with pytest.raises(ValidationError, match=field):
        m.CapabilitySurfaceDelta.model_validate(payload)


@pytest.mark.parametrize("enum", ["SurfaceKind", "AuthorityCeiling", "FreshnessState",
                                 "DeltaKind", "RequiredIntakeAction"])
def test_unknown_enum_value_refuses(enum):
    with pytest.raises(ValueError):
        getattr(api(), enum)("invented")


@pytest.mark.parametrize("contents", [None, "{", "[]", "{}", "null"])
def test_missing_or_malformed_file_is_not_success(tmp_path, contents):
    m = api()
    path = tmp_path / "producer.json"
    if contents is not None:
        path.write_text(contents)
    with pytest.raises(m.CapabilitySurfaceDeltaError, match="next action: repair"):
        m.load_capability_surface_delta_file(path)


def test_json_reader_requires_object(tmp_path):
    m = api()
    path = tmp_path / "list.json"
    path.write_text("[]")
    with pytest.raises(m.CapabilitySurfaceDeltaError, match="JSON object"):
        m._load_json(path)


@pytest.mark.parametrize("duration", ["", "0h", "01h", "-1h", "forever", "1w"])
def test_invalid_descriptor_duration_refuses(duration):
    m = api()
    payload = {**PRODUCER["descriptors"][0], "stale_after": duration}
    with pytest.raises(ValidationError, match="next action: set stale_after"):
        m.CapabilitySurfaceDescriptor.model_validate(payload)


@pytest.mark.parametrize("duration", ["1000000000d", "24000000000h",
                                     "1440000000000m", "86400000000000s"])
def test_duration_overflow_refuses_typed(tmp_path, duration):
    m = api()
    payload = copy.deepcopy(PRODUCER)
    payload["descriptors"][0]["stale_after"] = duration
    path = tmp_path / "overflow.json"
    path.write_text(json.dumps(payload))
    with pytest.raises(m.CapabilitySurfaceDeltaError, match="next action: repair") as caught:
        m.load_capability_surface_delta_file(path)
    assert isinstance(caught.value.__cause__, OverflowError)


@pytest.mark.parametrize("duration", ["999999999d", "23999999976h",
                                     "1439999998560m", "86399999913600s"])
def test_representable_large_duration_still_reads(tmp_path, duration):
    m = api()
    payload = copy.deepcopy(PRODUCER)
    payload["descriptors"][0]["stale_after"] = duration
    path = tmp_path / "large.json"
    path.write_text(json.dumps(payload))
    result = m.load_capability_surface_delta_file(path)
    assert result.descriptors[0].stale_after == duration
    assert m.parse_duration_spec(duration) == timedelta(days=999999999)


def test_freshness_signature_and_time_normalization():
    m = api()
    value = m.CapabilitySurfaceDescriptor.model_validate(PRODUCER["descriptors"][0])
    assert value.freshness_state(now=datetime(2026, 7, 1, 5)) is m.FreshnessState.FRESH
    assert value.freshness_state(now=datetime(2026, 7, 1, 5, 0, 1)) is m.FreshnessState.STALE
    assert m.ensure_utc(datetime(2026, 7, 1)) == datetime(2026, 7, 1, tzinfo=UTC)
    assert [m.parse_duration_spec(s).total_seconds() for s in ("2s", "2m", "2h", "2d")] == [
        2, 120, 7200, 172800]
    assert m.stable_hash({"a": 1, "b": 2}) == m.stable_hash({"b": 2, "a": 1})
    assert value.significant_signature() == value.model_copy(update={
        "observed_at": value.observed_at + timedelta(hours=1)}).significant_signature()
    assert value.significant_signature() != value.model_copy(update={
        "authority_ceiling": m.AuthorityCeiling.UNKNOWN}).significant_signature()


def test_package_read_boundary_is_inert_and_has_no_task_writer(tmp_path):
    import os
    import subprocess
    import sys

    env = os.environ.copy()
    for key in ("PYTHONPATH", "HAPAX_SPINE_CONFIG_DIR", "HAPAX_SPINE_REPO_ROOT"):
        env.pop(key, None)
    path = tmp_path / "producer.json"
    path.write_text(json.dumps(PRODUCER))
    code = '''
import builtins, importlib, io, os, socket, subprocess, sys
from pathlib import Path
original_import, original_open, io_open = builtins.__import__, builtins.open, io.open
def checked_import(name, *args, **kwargs):
    if name == "shared" or name.startswith("shared."):
        raise AssertionError("Council import: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = checked_import
def forbidden(*args, **kwargs):
    raise AssertionError("passive reader attempted an action")
def checked_open(original, file, mode="r", *args, **kwargs):
    if any(flag in str(mode) for flag in "wax+"):
        forbidden()
    if any(token in str(file) for token in (".secrets", "FileStore", ".password-store")):
        forbidden()
    return original(file, mode, *args, **kwargs)
builtins.open = lambda *a, **kw: checked_open(original_open, *a, **kw)
io.open = lambda *a, **kw: checked_open(io_open, *a, **kw)
socket.create_connection = socket.socket.connect = subprocess.Popen = os.system = forbidden
module = importlib.import_module("hapax.spine.capability_surface_delta")
assert not any(name in vars(module) for name in (
    "write_capability_surface_delta_tasks", "render_capability_surface_delta_task",
    "task_id_for_delta", "detect_surface_deltas", "build_surface_delta",
    "DEFAULT_CAPABILITY_SURFACE_DELTA_TASK_ROOT", "load_capability_surface_delta_fixtures"))
result = module.load_capability_surface_delta_file(Path(sys.argv[1]))
assert result.deltas[0].delta_id == "test:single-stale-codex"
assert module.__file__
'''
    result = subprocess.run([sys.executable, "-B", "-c", code, str(path)], cwd=tmp_path,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def _mutation_controls():
    """Explicit checkout-only controls; never run during pytest collection."""
    import ast
    import hashlib
    import os
    from pathlib import Path
    import subprocess
    import sys
    import tempfile

    root = Path(__file__).resolve().parents[1]
    path = root / "src/hapax/spine/capability_surface_delta.py"
    assert Path(api().__file__).resolve() == path.resolve()
    original = path.read_bytes()
    source = original.decode()
    tree = ast.parse(source)
    controls = []

    def replace(label, old, new):
        assert source.count(old) == 1, (label, source.count(old))
        controls.append((label, source.replace(old, new).encode()))

    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef)
               and n.name == "CapabilitySurfaceDelta")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef)
                  and n.name == "_delta_contract_is_actionable")
    raises = sorted((n for n in ast.walk(method) if isinstance(n, ast.Raise)),
                    key=lambda n: n.lineno)
    assert len(raises) == len(BAD_BINDINGS)
    for i, node in enumerate(raises):
        lines = source.splitlines(keepends=True)
        lines[node.lineno - 1:node.end_lineno] = [" " * node.col_offset + "pass\n"]
        controls.append(("action-binding-" + str(i), "".join(lines).encode()))
    for name in ("descriptor_schema", "delta_schema", "schema_version"):
        replace(name, name + ": Literal[1] = 1", name + ": int = 1")
    replace("schema-ref", 'schema_ref: Literal["schemas/capability-surface-delta.schema.json"]',
            'schema_ref: str')
    replace("unknown-fields", 'ConfigDict(extra="forbid")', 'ConfigDict(extra="ignore")')
    replace("nonempty-tokens", 'NonEmptyString = Annotated[str, Field(min_length=1)]',
            'NonEmptyString = str')
    replace("untyped-evidence", 'NonEmptyString = Annotated[str, Field(min_length=1)]',
            'NonEmptyString = Any')
    controls.append(("empty-collections-and-identities",
                     source.replace("Field(min_length=1)", "Field()").encode()))
    for field in ("privacy_sensitive", "public_egress", "money_rail"):
        replace("explicit-" + field, "    " + field + ": bool\n",
                "    " + field + ": bool = False\n")
    for name in ("SurfaceKind", "AuthorityCeiling", "FreshnessState", "DeltaKind",
                 "RequiredIntakeAction"):
        replace("enum-" + name, "class " + name + "(StrEnum):\n",
                "class " + name + "(StrEnum):\n"
                "    @classmethod\n    def _missing_(cls, value):\n"
                "        return next(iter(cls))\n")
    replace("duration-check", "        parse_duration_spec(self.stale_after)\n",
            "        pass\n")
    replace("duration-overflow-untyped", "ValidationError, ValueError, OverflowError) as exc:",
            "ValidationError, ValueError) as exc:")
    replace("stale-cannot-fulfill", "    def allows_demand_fulfillment(self) -> bool:\n",
            "    def allows_demand_fulfillment(self) -> bool:\n        return True\n")
    replace("json-object", '        raise CapabilitySurfaceDeltaError(f"{path} did not contain a JSON object")',
            "        return {}")
    replace("loader-refusal", '        raise CapabilitySurfaceDeltaError(\n            "invalid capability-surface delta producer file;',
            '        return None\n        raise CapabilitySurfaceDeltaError(\n            "invalid capability-surface delta producer file;')
    controls.append(("writer-export", original + b"\ndef write_capability_surface_delta_tasks():\n    pass\n"))

    def run(label):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory(prefix="obs0b-s02a-cache-") as cache:
            env["PYTHONPYCACHEPREFIX"] = cache
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(Path(__file__).resolve())],
                                    cwd=root, env=env, capture_output=True, text=True)
        output = result.stdout + result.stderr
        print(json.dumps({"phase": label, "exit": result.returncode,
                          "output_sha256": hashlib.sha256(output.encode()).hexdigest()}), flush=True)
        print(output, flush=True)
        return result.returncode

    assert run("unmodified-green") == 0
    for label, broken in controls:
        try:
            assert path.read_bytes() == original
            path.write_bytes(broken)
            print(json.dumps({"mutation": label,
                              "before_sha256": hashlib.sha256(original).hexdigest(),
                              "broken_sha256": hashlib.sha256(broken).hexdigest()}), flush=True)
            assert run(label + ":red") == 1, "must fail tests, not collection"
        finally:
            path.write_bytes(original)
        assert path.read_bytes() == original
        assert run(label + ":restored-green") == 0
    print(json.dumps({"controls": len(controls), "all_killed_and_restored": True,
                      "restored_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}), flush=True)


def _verify_council_source(filename):
    """Reproduce the parity witness without importing Council or contacting hosts.

    Supply the bytes from:
      git show cef55b5216574f7eb80fd42c887c58e83f7cace0:shared/capability_surface_delta.py
    The full input hash binds the source cut. Fifteen definitions match exact
    text; the reader adds only the seat-authorized OverflowError catch. Run
    separately from guard mutations so parity cannot kill a behavioral survivor.
    """
    import ast
    import hashlib
    from pathlib import Path

    source = Path(filename).read_bytes()
    expected = "eea24d68f0fa80278fec7018b1ffcff620ca281b7f95ebaf4d1d2f0651496d4d"
    assert hashlib.sha256(source).hexdigest() == expected, "wrong Council source cut"
    allocation = set("CapabilitySurfaceDeltaError StrictModel NonEmptyString SurfaceKind "
        "AuthorityCeiling FreshnessState DeltaKind RequiredIntakeAction "
        "CapabilitySurfaceDescriptor CapabilitySurfaceDelta CapabilitySurfaceDeltaFile "
        "ensure_utc parse_duration_spec stable_hash _load_json "
        "load_capability_surface_delta_file".split())

    def definitions(text):
        result = {}
        for node in ast.parse(text).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                name = node.name
            elif isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            else:
                continue
            result[name] = ast.get_source_segment(text, node)
        return result

    pinned = definitions(source.decode())
    installed = definitions(Path(api().__file__).read_text())
    assert set(installed) == allocation, "allocation drift"
    reader = "load_capability_surface_delta_file"
    exact = allocation - {reader}
    assert all(pinned[name] == installed[name] for name in exact), "definition drift"
    old = "ValidationError, ValueError) as exc:"
    assert pinned[reader].count(old) == 1
    safer = pinned[reader].replace(old, "ValidationError, ValueError, OverflowError) as exc:")
    assert installed[reader] == safer, "reader deviation exceeds the overflow catch"
    print(json.dumps({"council_sha256": expected, "exact_definitions": sorted(exact),
                      "safer_deviation": {reader: "catch OverflowError as typed refusal"},
                      "package_module": api().__file__}), flush=True)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["--mutation-controls"]:
        _mutation_controls()
    elif len(sys.argv) == 3 and sys.argv[1] == "--parity-source":
        _verify_council_source(sys.argv[2])
    else:
        raise SystemExit("usage: test_obs0b_s02a_parity.py --mutation-controls | --parity-source FILE")
