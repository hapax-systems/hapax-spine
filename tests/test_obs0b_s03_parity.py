"""S03 route/root and declared native-load/pool contracts.

LOAD and POOL are exact /routes[route_id=claude.review.opus] projections of
Council cef55b52 config/platform-capability-registry.json (hash below).
The legacy fixture route is a substrate for explicitly synthetic root/unsafe
cases, not a claim about actual current route state. --registry-source checks
ALL current records from the pinned blob, without importing Council.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError
from hapax.spine import platform_capability_registry as registry
from test_obs0b_s02b_parity import TRUST

REGISTRY_SHA = "7d7518c484b90dbb16728993a4c9b5a69b0ad402bb541d254c447470f16d73ca"
SOURCE_SHA = "bcb3065e0802bc3a294571f01d745d5e1f11ed15f6905442aa5df9d2c9365bb0"

LOAD = json.loads(r'''
{
  "native_home": ".claude-max-2",
  "home_env": "CLAUDE_CONFIG_DIR",
  "files": [
    {
      "root": "native_home",
      "path": "settings.json",
      "kind": "configuration",
      "sha256": null,
      "required": false
    }
  ],
  "memory_scope": "Intended blind review: --safe-mode requests auto-memory disabled; --no-session-persistence requested. Managed policy and effective native inputs remain unobserved.",
  "plugins": [],
  "skills": [],
  "hooks": null,
  "mcp": [],
  "loading_flags": [
    "--safe-mode",
    "--disable-slash-commands",
    "--no-session-persistence",
    "--strict-mcp-config"
  ],
  "source_refs": [
    "scripts/hapax-claude-reviewer",
    "docs/runbooks/agent-instruction-binding.md",
    "https://code.claude.com/docs/en/cli-reference",
    "task:capability-declared-load-set-20260919"
  ]
}
''')

POOL = json.loads(r'''
{
  "pool": "max-2",
  "config_home": ".claude-max-2",
  "receipt_dir": ".cache/hapax/relay/receipts-max-2",
  "headless_dir": ".cache/hapax/claude-headless-max-2",
  "pace_activation": ".cache/hapax/claude-pool-pace-max-2/activation.json",
  "durable_sink_root": ".cache/hapax/stage0-durable-sink-max-2"
}
''')

CURRENT_IDS = ['api.headless.api_frontier', 'api.headless.openrouter', 'api.headless.provider_gateway', 'claude.headless.full', 'claude.headless.haiku', 'claude.headless.opus', 'claude.headless.sonnet', 'claude.review.opus', 'claude.interactive.full', 'kimi.interactive.lane', 'codex.headless.full', 'codex.headless.spark', 'agy.review.direct', 'glmcp.review.direct', 'local_tool.local.worker', 'vibe.headless.full']


def route(route_id="claude.headless.full", **changes):
    """Synthetic route variants on an otherwise valid, existing test substrate."""
    fixture = json.loads((Path(__file__).parent / "fixtures/platform-capability-registry.json").read_text())
    value = copy.deepcopy(next(r for r in fixture["routes"] if r["route_id"] == "claude.headless.full"))
    platform, mode, profile = route_id.split(".")
    value.update(route_id=route_id, platform=platform, mode=mode, profile=profile)
    value.update(changes)
    return value


def bound(route_id="claude.review.opus", **changes):
    return route(route_id, native_load_set=copy.deepcopy(LOAD),
                 subscription_pool_binding=copy.deepcopy(POOL), **changes)


def root():
    return dict(registry_schema=1, registry_id="synthetic-s03-root",
        schema_ref="schemas/platform-capability-registry.schema.json",
        declared_at="2026-10-24T20:25:00Z", capacity_invariant=registry.CAPACITY_INVARIANT,
        generated_from=["test:synthetic-root"], required_route_ids=list(CURRENT_IDS),
        omitted_capability_shapes=[copy.deepcopy(TRUST)],
        routes=[bound(r) if r == "claude.review.opus" else route(r) for r in CURRENT_IDS])


def validate(payload):
    return registry.PlatformCapabilityRegistry.model_validate(payload)


@pytest.fixture(autouse=True)
def no_external_actions(monkeypatch):
    import socket
    import subprocess
    def forbidden(*args, **kwargs):
        pytest.fail("schema test attempted network, credential or subprocess action")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)


def test_current_load_pool_and_unobserved_distinctions():
    load = registry.NativeLoadSet.model_validate(LOAD)
    assert load.model_dump() == {**LOAD, "files": [{**LOAD["files"][0], "digest_description": None}]}
    assert load.files[0].sha256 is None and load.files[0].required is False
    assert load.plugins == [] and load.hooks is None and load.mcp == []
    assert registry.SubscriptionPoolBinding.model_validate(POOL).model_dump() == POOL
    parsed = registry.PlatformCapabilityRoute.model_validate(bound())
    assert parsed.subscription_pool_binding.model_dump() == POOL
    assert parsed.native_load_set == load
    unknown = registry.NativeLoadSet.model_validate({**LOAD, "plugins": None})
    assert unknown.plugins is None
    ordinary = registry.PlatformCapabilityRoute.model_validate(route())
    assert ordinary.native_load_set is None and ordinary.subscription_pool_binding is None


@pytest.mark.parametrize("changes", [
    {"path": "/etc/private"}, {"path": "../private"}, {"path": "nested/../../private"},
    {"path": ""}, {"root": "host"}, {"kind": "executable"}, {"sha256": "unknown"},
    {"sha256": "A" * 64}, {"sha256": "a" * 63},
])
def test_load_file_refusals(changes):
    with pytest.raises(ValidationError):
        registry.NativeLoadFile.model_validate({**LOAD["files"][0], **changes})


@pytest.mark.parametrize("path", ["AGENTS.md", "nested/./settings.json"])
def test_load_file_relative_paths_and_explicit_digest(path):
    value = registry.NativeLoadFile(root="project", path=path, kind="instructions", sha256="a" * 64)
    assert value.path == path and value.sha256 == "a" * 64 and value.required is True


@pytest.mark.parametrize("field,empty", [("native_home", ""), ("files", []),
    ("memory_scope", ""), ("source_refs", [])])
def test_load_set_required_fields(field, empty):
    with pytest.raises(ValidationError):
        registry.NativeLoadSet.model_validate({**LOAD, field: empty})


POOL_PATHS = ("config_home", "receipt_dir", "headless_dir", "pace_activation", "durable_sink_root")


@pytest.mark.parametrize("field", POOL_PATHS)
@pytest.mark.parametrize("value", ["", ".", "/absolute", "../escape", "nested/../../escape"])
def test_pool_paths_stay_inside_home(field, value):
    with pytest.raises(ValidationError):
        registry.SubscriptionPoolBinding.model_validate({**POOL, field: value})


@pytest.mark.parametrize("pool", ["a", "UPPER", "a" * 33, "max_account", "account-2", "max-billing-2",
    "max-customer-2", "max-invoice-2", "max-payment-2"])
def test_pool_names_are_pool_identifiers(pool):
    with pytest.raises(ValidationError):
        registry.SubscriptionPoolBinding.model_validate({**POOL, "pool": pool})


@pytest.mark.parametrize("changes,message", [
    ({"receipt_dir": ".claude-max-2/./"}, "must be distinct"),
    ({"config_home": "./.claude/"}, "non-default config home"),
    ({"receipt_dir": "./.cache/hapax/relay/receipts/"}, "outside the shared"),
])
def test_pool_default_and_alias_refusals(changes, message):
    with pytest.raises(ValidationError, match=message):
        registry.SubscriptionPoolBinding.model_validate({**POOL, **changes})


@pytest.mark.parametrize("change", ["platform", "auth", "capacity", "missing-load", "home-env", "home"])
def test_pool_route_binding_must_match(change):
    value = bound()
    if change == "platform":
        value.update(platform="codex", route_id="codex.review.opus")
    elif change == "auth":
        value["auth_surface"] = "oauth"
    elif change == "capacity":
        value["capacity_pool"] = "api_paid_spend"
    elif change == "missing-load":
        value["native_load_set"] = None
    else:
        value["native_load_set"]["home_env" if change == "home-env" else "native_home"] = "mismatch"
    with pytest.raises(ValidationError, match="subscription_pool_binding|pool-bound route"):
        registry.PlatformCapabilityRoute.model_validate(value)


def test_root_routes_and_persistent_evidence_shape():
    value = validate(root())
    assert set(value.route_map()) == set(CURRENT_IDS) == registry.REQUIRED_ROUTE_IDS
    assert len(value.omitted_capability_shapes) == 1
    assert value.omitted_capability_shapes[0].demand_eligible is False
    assert value.require("claude.review.opus").subscription_pool_binding.pool == "max-2"
    with pytest.raises(KeyError):
        value.require("claude.review.missing")


@pytest.mark.parametrize("change,message", [
    ("omitted-absent", "omitted_capability_shapes"), ("omitted-empty", "omitted_capability_shapes"),
    ("required-ids", "required platform route ids mismatch"),
    ("duplicate-route", "duplicate platform route ids"), ("missing-route", "missing required platform routes"),
    ("extra-route", "routes not declared"), ("invariant", "capacity invariant drifted"),
    ("duplicate-shape", "duplicate omitted"), ("no-permanent-shape", "permanent agentic-trust"),
    ("canonical-shape", "collide after canonicalization"), ("route-shape", "collide with admitted route"),
    ("unknown-provenance", "unknown route_id"),
])
def test_root_refusals(change, message):
    value = root()
    validate(value)
    if change == "omitted-absent":
        del value["omitted_capability_shapes"]
    elif change == "omitted-empty":
        value["omitted_capability_shapes"] = []
    elif change == "required-ids":
        value["required_route_ids"].remove(CURRENT_IDS[0])
        value["routes"].pop(0)  # Isolate the governed catalog, not a routes/list mismatch.
    elif change == "duplicate-route":
        value["routes"].append(copy.deepcopy(value["routes"][0]))
    elif change == "missing-route":
        value["routes"].pop()
    elif change == "extra-route":
        value["routes"].append(route("codex.interactive.full"))
    elif change == "invariant":
        value["capacity_invariant"] = "unrestricted"
    elif change == "duplicate-shape":
        value["omitted_capability_shapes"] *= 2
    elif change == "no-permanent-shape":
        value["omitted_capability_shapes"][0]["shape_id"] = "local_compute.other"
    elif change in {"canonical-shape", "route-shape"}:
        names = ["example.shape", "surface.example.shape"] if change == "canonical-shape" else ["surface.codex.headless.full"]
        for name in names:
            shape = copy.deepcopy(TRUST); shape["shape_id"] = name
            value["omitted_capability_shapes"].append(shape)
    else:
        value["routes"][0]["descriptor_variants"] = [{"variant_id": "synthetic", "blocked_reasons": ["held"],
                                                   "scores_inherited_from": "missing.route.full"}]
    with pytest.raises(ValidationError, match=message):
        validate(value)


@pytest.mark.parametrize("read", ["validate", "route_map", "require"])
@pytest.mark.parametrize("conflict", ["same-pool-different-paths", "equal", "nested", "parent"])
def test_registry_pool_paths_cannot_cross_pool_boundary(conflict, read):
    value = root()
    second = bound("claude.headless.full")
    value["routes"][CURRENT_IDS.index("claude.headless.full")] = second
    valid = validate(value)  # Several routes may share one identically declared pool.
    binding = second["subscription_pool_binding"]
    if conflict == "same-pool-different-paths":
        binding["receipt_dir"] += "-other"
    else:
        binding.update(pool="max-3", **{k: v.replace("max-2", "max-3") for k,v in POOL.items() if k != "pool"})
        second["native_load_set"]["native_home"] = binding["config_home"]
        valid = validate(value)  # Disjoint pools are valid.
        binding["receipt_dir"] = {"equal": POOL["receipt_dir"] + "/./",
            "nested": POOL["receipt_dir"] + "/nested", "parent": ".cache/hapax/relay"}[conflict]
    if read != "validate":
        valid.routes[CURRENT_IDS.index("claude.headless.full")].subscription_pool_binding.receipt_dir = binding["receipt_dir"]
        reader = valid.route_map if read == "route_map" else lambda: valid.require("claude.review.opus")
    else:
        reader = lambda: validate(value)
    with pytest.raises(ValidationError, match="different paths|share the path") as error:
        reader()
    assert "next action:" in str(error.value)


@pytest.mark.parametrize("field", ["route_id", "launcher", "sanctioned_wrapper", "model_or_engine",
                                   "paid_provider", "paid_profile", "source_refs"])
@pytest.mark.parametrize("marker", [TRUST["shape_id"], "AgenticTrustEvidenceReceiptV1:retained"])
def test_route_agentic_trust_refusals(field, marker):
    value = route(native_load_set=copy.deepcopy(LOAD))
    registry.PlatformCapabilityRoute.model_validate(value)
    if field == "source_refs":
        value["native_load_set"][field] = [marker]
        message = "agentic-trust observation evidence cannot carry a supply policy effect: native_load_set.source_refs"
    else:
        value[field] = marker
        message = ("route_id must equal platform.mode.profile: claude.headless.full" if field == "route_id"
                   else "agentic-trust evaluator observation identity cannot be an executable registry route")
    with pytest.raises(ValidationError) as error:
        registry.PlatformCapabilityRoute.model_validate(value)
    assert error.value.errors()[0]["msg"] == "Value error, " + message


def test_route_map_revalidates_modified_nested_routes():
    value = validate(root())
    value.routes[0].route_id = "wrong.identity.full"
    with pytest.raises(ValidationError, match="route_id must equal"):
        value.route_map()
    with pytest.raises(ValidationError, match="route_id must equal"):
        value.require("claude.review.opus")


def test_resolved_pool_is_frozen_metadata(tmp_path):
    from dataclasses import FrozenInstanceError
    value = registry.ResolvedSubscriptionPool(route_id="claude.review.opus", pool=POOL["pool"],
        config_dir=tmp_path / POOL["config_home"], receipt_dir=tmp_path / POOL["receipt_dir"],
        headless_dir=tmp_path / POOL["headless_dir"], pace_activation=tmp_path / POOL["pace_activation"],
        durable_sink_root=tmp_path / POOL["durable_sink_root"])
    assert value.config_dir == tmp_path / ".claude-max-2"
    assert not value.config_dir.exists()  # This record does not create or probe a binding.
    with pytest.raises(FrozenInstanceError):
        value.pool = "other"


ALLOCATION = set("NativeLoadFile NativeLoadSet PlatformCapabilityRegistry PlatformCapabilityRoute "
    "ResolvedSubscriptionPool SubscriptionPoolBinding CLAUDE_DEFAULT_CONFIG_HOME "
    "REQUIRED_ROUTE_IDS SHARED_RELAY_RECEIPT_HOME".split())
READ_VALIDATION = 'PlatformCapabilityRegistry.model_validate(self.model_dump(mode="python")).routes'


def _parity(filename):
    import ast
    import hashlib
    raw = Path(filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_SHA
    def definitions(text):
        result, lines = {}, text.splitlines()
        for node in ast.parse(text).body:
            name = getattr(node, "name", None)
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            if name in ALLOCATION:
                start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
                result[name] = "\n".join(lines[start - 1:node.end_lineno])
        return result
    expected = definitions(raw.decode())
    actual = definitions(Path(registry.__file__).read_text())
    assert set(expected) == set(actual) == ALLOCATION
    name = "PlatformCapabilityRegistry"
    assert actual[name].count(READ_VALIDATION) == 1
    actual[name] = actual[name].replace(READ_VALIDATION,
        '(PlatformCapabilityRoute.model_validate(route.model_dump(mode="python")) for route in self.routes)')
    # Preserve pre-existing statement formatting rather than spend patch budget on it.
    assert all(ast.dump(ast.parse(actual[k])) == ast.dump(ast.parse(expected[k])) for k in ALLOCATION)
    print(json.dumps({"ast_equal_after_authorized_read_repair": len(actual),
        "byte_equal_definitions": sum(actual[k] == expected[k] for k in ALLOCATION),
        "source_sha256": SOURCE_SHA}))


def _current_registry(filename):
    """Offline, hash-bound full-data integration; no receipt overlay or host contact."""
    import hashlib
    import os
    from unittest.mock import patch
    raw = Path(filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == REGISTRY_SHA
    payload = json.loads(raw)
    with patch.dict(os.environ, {registry.PLATFORM_CAPABILITY_RECEIPT_DIR_ENV: "none"}):
        parsed = registry.load_platform_capability_registry(Path(filename))
    assert set(parsed.route_map()) == set(CURRENT_IDS)
    assert len(parsed.routes) == 16 and len(parsed.omitted_capability_shapes) == 13
    assert all(not x.demand_eligible and not x.route_ids for x in parsed.omitted_capability_shapes)
    for before, after in zip(payload["routes"], parsed.routes, strict=True):
        assert (before["route_id"], before["route_state"], before["blocked_reasons"]) == (
            after.route_id, after.route_state.value, after.blocked_reasons)
        if before.get("native_load_set") is not None:
            assert registry.NativeLoadSet.model_validate(before["native_load_set"]) == after.native_load_set
        if before.get("subscription_pool_binding") is not None:
            assert after.subscription_pool_binding.model_dump() == before["subscription_pool_binding"]
    assert parsed.require("claude.review.opus").subscription_pool_binding.model_dump() == POOL
    print(json.dumps({"registry_sha256": REGISTRY_SHA, "routes": len(parsed.routes),
        "omitted_shapes": len(parsed.omitted_capability_shapes), "all_shapes_non_supply": True,
        "route_states_and_blockers_preserved": True, "package": registry.__file__}))


def _mutations():
    """Break each S03 refusal boundary, assert red, restore exact bytes, assert green."""
    import ast
    import hashlib
    import os
    import subprocess
    import sys
    import tempfile
    path = Path(__file__).resolve().parents[1] / "src/hapax/spine/platform_capability_registry.py"
    assert Path(registry.__file__).resolve() == path.resolve()
    original = path.read_bytes(); source = original.decode(); tree = ast.parse(source)
    controls = []
    duplicate_shape_guards = []
    def change(label, node, code):
        lines = source.splitlines(keepends=True)
        lines[node.lineno - 1:node.end_lineno] = [" " * node.col_offset + code + "\n"]
        controls.append((label, "".join(lines).encode()))
    new_classes = {"NativeLoadFile", "NativeLoadSet", "SubscriptionPoolBinding"}
    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ALLOCATION):
        for node in ast.walk(cls):
            if isinstance(node, ast.Raise):
                detail = ast.get_source_segment(source, node)
                if "duplicate omitted capability shape ids" in detail or "collide after canonicalization" in detail:
                    duplicate_shape_guards.append(node)
                    if "duplicate omitted capability shape ids" in detail:
                        continue  # The canonical duplicate guard also covers this case.
                if cls.name in new_classes | {"PlatformCapabilityRegistry"} or (
                    cls.name == "PlatformCapabilityRoute" and any(
                        x in detail for x in ("subscription_pool_binding", "pool-bound", "agentic-trust"))):
                    change(cls.name + ":raise:" + str(node.lineno), node, "pass")
            if isinstance(node, ast.AnnAssign) and cls.name in new_classes:
                annotation = ast.get_source_segment(source, node.annotation)
                if annotation.startswith("Literal["):
                    change(cls.name + ":literal:" + node.target.id, node,
                           ast.get_source_segment(source, node).replace(annotation, "str", 1))
                if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "Field":
                    keys = {k.arg for k in node.value.keywords}
                    if keys & {"min_length", "pattern"} and not (
                        cls.name == "SubscriptionPoolBinding" and node.target.id in POOL_PATHS
                    ):
                        default = "default=None" if "default" in keys else ""
                        change(cls.name + ":field:" + node.target.id, node,
                               node.target.id + ": " + annotation + " = Field(" + default + ")")
    assert len(duplicate_shape_guards) == 2
    lines = source.splitlines(keepends=True)
    for node in sorted(duplicate_shape_guards, key=lambda n: n.lineno, reverse=True):
        lines[node.lineno - 1:node.end_lineno] = [" " * node.col_offset + "pass\n"]
    controls.append(("raw-and-canonical-duplicate-guards", "".join(lines).encode()))
    old = 'omitted_capability_shapes: list[CapabilityShapeDescriptor] = Field(min_length=1)'
    relaxed = source.replace(old,
        'omitted_capability_shapes: list[CapabilityShapeDescriptor] = Field(default_factory=list)')
    # The permanent-shape check also refuses absence: break both to permit it.
    relaxed = relaxed.replace('raise ValueError(\n                "platform registry must retain the permanent agentic-trust evidence-only shape"\n            )', 'pass')
    controls.append(("required-omitted-shapes", relaxed.encode()))
    old = READ_VALIDATION
    assert source.count(old) == 1
    controls.append(("route-map-revalidation", source.replace(old, "self.routes").encode()))
    controls.append(("cross-route-read", source.replace(old,
        '[PlatformCapabilityRoute.model_validate(r.model_dump(mode="python")) for r in self.routes]').encode()))
    controls.append(("frozen-resolved-pool", source.replace('@dataclass(frozen=True)\nclass ResolvedSubscriptionPool',
                                                        '@dataclass\nclass ResolvedSubscriptionPool').encode()))
    def run(label):
        env = os.environ.copy(); env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory(prefix="s03-cache-") as cache:
            env["PYTHONPYCACHEPREFIX"] = cache
            result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(Path(__file__).resolve())],
                cwd=path.parents[3], env=env, capture_output=True, text=True)
        output = result.stdout + result.stderr
        print(json.dumps({"phase": label, "exit": result.returncode,
                          "output_sha256": hashlib.sha256(output.encode()).hexdigest()}), flush=True)
        print(output, flush=True)
        if label.endswith(":red"):
            assert "DID NOT RAISE" in output, "mutant must admit an unsafe case, not merely change its error text"
        return result.returncode
    assert run("original-green") == 0
    for label, mutant in controls:
        assert mutant != original
        try:
            assert path.read_bytes() == original
            path.write_bytes(mutant)
            print(json.dumps({"mutation": label, "original_sha256": hashlib.sha256(original).hexdigest(),
                              "mutant_sha256": hashlib.sha256(mutant).hexdigest()}), flush=True)
            assert run(label + ":red") == 1, "requires test failure, not collection error"
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
    elif len(sys.argv) == 3 and sys.argv[1] == "--registry-source":
        _current_registry(sys.argv[2])
    else:
        raise SystemExit("use --mutation-controls, --parity-source FILE or --registry-source FILE")
