"""S02b declaration contracts; no endpoint evaluator or host/provider action.

Seeds are exact /omitted_capability_shapes records keyed by shape_id from
Council cef55b5216574f7eb80fd42c887c58e83f7cace0 config/platform-capability-registry.json,
SHA256 7d7518c484b90dbb16728993a4c9b5a69b0ad402bb541d254c447470f16d73ca.
Other inputs are explicitly adversarial or hypothetical facts, not observations.
"""
from __future__ import annotations

import copy
from datetime import UTC, datetime
import json

import pytest
from pydantic import ValidationError
from hapax.spine import platform_capability_registry as registry

RESEARCH = json.loads(r'''
{
  "descriptor_schema": 1,
  "shape_id": "research.external_primary_source_fetch",
  "shape_class": "research",
  "carrier_family": "declared_lane_tool_access",
  "summary": "Read-only retrieval and close reading of external primary sources (papers, official docs, repositories) for estate research programmes; outputs are evidence with BACKED/UNBACKED disposition, never outward contact.",
  "harness_shape": "bounded-fetch-plus-source-ledger-plus-evidence-disposition",
  "authority_ceiling": "read_only",
  "shape_state": "intake_required",
  "demand_eligible": false,
  "route_ids": [],
  "candidate_binding": {
    "state": "candidate_only",
    "carrier_route_id": "codex.headless.full",
    "fetch_path": "scripts/hapax-primary-source-fetch",
    "fetch_path_state": "implemented_unexposed",
    "receipt_binding_state": "implemented_unexposed",
    "authority_contract_ref": "shared/dispatcher_policy.py:RouteAuthorityReceipt",
    "observation_contract_ref": "shared/platform_capability_receipts.py:PlatformCapabilityReceipt",
    "method": "GET",
    "allowed_domains": [
      "arxiv.org",
      "github.com",
      "raw.githubusercontent.com",
      "deepmind.google",
      "openreview.net",
      "proceedings.mlr.press"
    ],
    "max_documents": 12,
    "max_gets": 30,
    "max_download_bytes": 104857600,
    "max_incremental_cost_usd": 0,
    "billing_basis": "subscription_quota_only_no_paid_search",
    "stop_conditions": [
      "bound_exhausted",
      "unexpected_authentication",
      "unknown_billing",
      "unsafe_endpoint",
      "failed_admission"
    ],
    "admission_requirements": [
      "fresh_route_quota_admission",
      "task_bound_read_only_egress_receipt",
      "measured_fetch_path",
      "independent_review",
      "seat_first_exposure_ruling"
    ]
  },
  "resource_semantics": [
    "read-only-egress",
    "no-posting",
    "no-outward-contact",
    "no-credentials-in-requests",
    "primary-source-preferred"
  ],
  "spend_semantics": [
    "token-cost",
    "provider-search-cost-if-any-must-be-declared"
  ],
  "observability": [
    "fetched-url-ledger",
    "source-tier-label",
    "evidence-disposition"
  ],
  "failure_classes": [
    "secondary_source_treated_as_primary",
    "fetch_without_ledger",
    "outward_contact_attempted",
    "search_billing_undeclared"
  ],
  "measurement_plan_refs": [
    "task:acceleration-programme-act-2b-external-prior-art-model-externals-20261016"
  ],
  "remediation_refs": [
    "require:route-binding-with-quota-admission",
    "require:read-only-egress-receipt",
    "require:source-ledger"
  ],
  "surface_delta_signal": "capability_surface_delta:research",
  "observation_receipt_class": null,
  "observed_at": "2026-10-16T15:41:39Z",
  "stale_after": "30d",
  "freshness_state": "asserted_only",
  "evidence_refs": [
    "lanebus:dev47/20261016T152000Z-dev1-acceleration-2b-route.md"
  ],
  "blocked_reasons": [
    "measured_supply_leaf_absent",
    "route_binding_absent",
    "read_only_egress_receipt_absent"
  ]
}
''')

TRUST = json.loads(r'''
{
  "descriptor_schema": 1,
  "shape_id": "local_compute.agentic_trust_evaluator_surface",
  "shape_class": "local_compute",
  "carrier_family": "agentic_trust_evidence",
  "summary": "Read-only verification of externally anchored agentic-trust terminal evidence; this is an evidence surface, not execution capacity.",
  "harness_shape": "explicit-terminal-evidence-import-plus-held-fd-verification",
  "authority_ceiling": "read_only",
  "shape_state": "evidence_only",
  "demand_eligible": false,
  "route_ids": [],
  "resource_semantics": [
    "local-read-only-verification",
    "caller-held-three-pin-anchors",
    "no-execution-capacity"
  ],
  "spend_semantics": [
    "no-provider-spend",
    "local-energy-technical-telemetry-only",
    "no-economic-payback-effect"
  ],
  "observability": [
    "AgenticTrustEvidenceReceiptV1",
    "integer-only-summary-facts",
    "custody-and-anchor-status"
  ],
  "failure_classes": [
    "terminal_custody_invalid",
    "external_anchors_incomplete",
    "semantic_claim_ceiling_exceeded",
    "production_evidence_absent",
    "runtime_authority_leak"
  ],
  "measurement_plan_refs": [
    "cc-task-agentic-trust-evidence-only-onboarding-20260804"
  ],
  "remediation_refs": [
    "require:production-evidence-import",
    "require:application-bound-admission-tuple",
    "forbid:route-adapter-launcher-registration"
  ],
  "surface_delta_signal": null,
  "observation_receipt_class": "AgenticTrustEvidenceReceiptV1",
  "observed_at": null,
  "stale_after": "30d",
  "freshness_state": "missing",
  "evidence_refs": [],
  "blocked_reasons": [
    "production_evidence_absent",
    "application_bound_admission_tuple_absent",
    "external_three_pin_custody_not_established"
  ]
}
''')


def shape(seed="research", **changes):
    value = copy.deepcopy(TRUST if seed in ("trust", "evidence") else RESEARCH)
    if seed == "evidence":
        value["shape_id"] = "local_compute.other_evidence"
    value.update(changes)
    return value


def facts(**changes):
    value = dict(url="https://arxiv.org/abs/example", documents_used=0, gets_used=0,
                 downloaded_bytes=0, request_byte_limit=4096, authentication="none",
                 billing="declared_zero_incremental", endpoint_public=True,
                 admission_passed=True, quota_fresh=True)
    value.update(changes)
    return value


@pytest.mark.parametrize("seed", ["research", "trust"])
def test_current_shape_records_remain_non_supply(seed):
    payload = shape(seed)
    result = registry.CapabilityShapeDescriptor.model_validate(payload)
    assert result.shape_id == payload["shape_id"]
    assert result.demand_eligible is False and result.route_ids == []
    if seed == "research":
        assert result.candidate_binding.model_dump() == RESEARCH["candidate_binding"]
        assert result.candidate_binding.state == "candidate_only"
    else:
        assert result.shape_state is registry.CapabilityShapeState.EVIDENCE_ONLY
        assert "candidate_binding" not in result.model_dump()


SHAPE_BAD = [
    ("research", {"demand_eligible": True}, "demand_eligible"),
    ("research", {"route_ids": ["codex.headless.full"]}, "route_ids"),
    ("research", {"surface_delta_signal": " "}, "non-empty"),
    ("research", {"observation_receipt_class": " "}, "non-empty"),
    ("evidence", {"authority_ceiling": "support_only"}, "read_only"),
    ("evidence", {"surface_delta_signal": "capability_surface_delta:local"}, "cannot emit"),
    ("evidence", {"observation_receipt_class": None}, "require an observation"),
    ("research", {"surface_delta_signal": None}, "require a surface_delta_signal"),
    ("trust", {"shape_state": "intake_required", "surface_delta_signal": "delta:local"}, "permanently"),
    ("trust", {"observation_receipt_class": "OtherReceipt"}, "AgenticTrustEvidenceReceiptV1"),
    ("research", {"shape_state": "deprecated", "blocked_reasons": ["unmeasured"]}, "retired blocker"),
    ("research", {"observed_at": None, "blocked_reasons": []}, "blocked_reasons"),
    ("research", {"evidence_refs": []}, "evidence_refs"),
    ("research", {"shape_id": "research.other"}, "only to its read-only"),
    ("research", {"authority_ceiling": "support_only"}, "only to its read-only"),
    ("research", {"shape_state": "admitted"}, "shape_state"),
    ("research", {"freshness_state": "available"}, "freshness_state"),
    ("research", {"descriptor_schema": 2}, "descriptor_schema"),
    ("research", {"shape_id": "RESEARCH Invalid"}, "shape_id"),
    ("evidence", {"shape_id": "INVALID shape"}, "shape_id"),
]


@pytest.mark.parametrize("seed,changes,message", SHAPE_BAD)
def test_shape_refusals(seed, changes, message):
    registry.CapabilityShapeDescriptor.model_validate(shape(seed))
    with pytest.raises(ValidationError, match=message):
        registry.CapabilityShapeDescriptor.model_validate(shape(seed, **changes))


@pytest.mark.parametrize("field", ["resource_semantics", "spend_semantics", "observability",
    "failure_classes", "measurement_plan_refs", "remediation_refs"])
def test_required_shape_evidence_collections_refuse_empty(field):
    with pytest.raises(ValidationError, match=field):
        registry.CapabilityShapeDescriptor.model_validate(shape(**{field: []}))


@pytest.mark.parametrize("duration", ["", "0h", "01h", "-1h", "1w"])
def test_shape_duration_syntax_refuses(duration):
    with pytest.raises(ValidationError, match="duration"):
        registry.CapabilityShapeDescriptor.model_validate(shape(stale_after=duration))


@pytest.mark.parametrize("duration", ["1000000000d", "24000000000h",
                                     "1440000000000m", "86400000000000s"])
def test_shape_duration_overflow_refuses_typed(duration):
    with pytest.raises(ValidationError, match="next action: set stale_after"):
        registry.CapabilityShapeDescriptor.model_validate(shape(stale_after=duration))


def test_valid_boundary_states():
    assert registry.CapabilityShapeDescriptor.model_validate(
        shape(stale_after="999999999d")).stale_after == "999999999d"
    for reason in ("deprecated_by_seat", "retired_surface"):
        result = registry.CapabilityShapeDescriptor.model_validate(shape(
            shape_state="deprecated", blocked_reasons=[reason]))
        assert result.shape_state is registry.CapabilityShapeState.DEPRECATED
    assert registry.CapabilityShapeDescriptor.model_validate(shape(
        observed_at=None, evidence_refs=[], blocked_reasons=["absent"])).observed_at is None


@pytest.mark.parametrize("field,value", [
    ("state", "admitted"), ("carrier_route_id", "arbitrary.route"), ("method", "POST"),
    ("fetch_path", "scripts/arbitrary"), ("fetch_path_state", "exposed"),
    ("receipt_binding_state", "exposed"), ("authority_contract_ref", "invented"),
    ("observation_contract_ref", "invented"), ("billing_basis", "paid_search"),
    ("max_documents", 0), ("max_documents", 13), ("max_documents", True),
    ("max_gets", 0), ("max_gets", 31), ("max_gets", 1.0),
    ("max_download_bytes", 0), ("max_download_bytes", 104857601),
    ("max_download_bytes", "1024"), ("max_incremental_cost_usd", -1),
    ("max_incremental_cost_usd", 1), ("max_incremental_cost_usd", False),
    ("allowed_domains", []), ("allowed_domains", ["arxiv.org", "arxiv.org"]),
    ("allowed_domains", ["*.arxiv.org"]), ("allowed_domains", ["https://arxiv.org"]),
    ("allowed_domains", ["ARXIV.ORG"]),
])
def test_binding_refuses_widening(field, value):
    payload = copy.deepcopy(RESEARCH["candidate_binding"])
    payload[field] = value
    with pytest.raises(ValidationError):
        registry.PrimarySourceCandidateBinding.model_validate(payload)


@pytest.mark.parametrize("field", ["stop_conditions", "admission_requirements"])
@pytest.mark.parametrize("change", ["missing", "duplicate", "unknown"])
def test_binding_requires_each_condition_exactly_once(field, change):
    payload = copy.deepcopy(RESEARCH["candidate_binding"])
    if change == "missing":
        payload[field].pop()
    else:
        payload[field][-1] = payload[field][0] if change == "duplicate" else "unknown"
    with pytest.raises(ValidationError, match="restore every declared"):
        registry.PrimarySourceCandidateBinding.model_validate(payload)


@pytest.mark.parametrize("field,value", [
    ("documents_used", -1), ("gets_used", -1), ("downloaded_bytes", -1),
    ("request_byte_limit", 0), ("authentication", "bearer"), ("billing", "free"),
    ("quota_fresh", "true"), ("admission_passed", 1), ("endpoint_public", "true"),
    ("gets_used", False), ("url", 17),
])
def test_request_facts_schema_refuses(field, value):
    registry.PrimarySourceRequestFacts.model_validate(facts())
    with pytest.raises(ValidationError, match=field):
        registry.PrimarySourceRequestFacts.model_validate(facts(**{field: value}))


def test_hypothetical_facts_and_checks_never_mint_authority():
    # Unsafe-but-well-typed facts are representable. S09 evaluates them; S02b
    # does not claim to observe endpoints or enforce network admission.
    value = registry.PrimarySourceRequestFacts.model_validate(facts(
        authentication="unknown", billing="unknown", endpoint_public=None,
        quota_fresh=False, admission_passed=False))
    assert value.endpoint_public is None and value.quota_fresh is False
    for stops in ((), ("unsafe_endpoint",)):
        check = registry.PrimarySourceCandidateCheck(stops)
        assert check.within_declared_constraints == (not stops)
        assert check.execution_authorized is False
    disposition = registry.CapabilitySurfaceDisposition(
        surface_id=TRUST["shape_id"], action="known_evidence_only_observe",
        reason_codes=("evidence_only",), remediation_refs=())
    assert disposition.demand_eligible is False
    with pytest.raises(ValidationError, match="demand_eligible"):
        registry.CapabilitySurfaceDisposition.model_validate({
            **disposition.model_dump(), "demand_eligible": True})


def test_freshness_reports_serialize_every_field():
    check = registry.OmittedShapeFreshnessCheck(
        TRUST["shape_id"], False, registry.CapabilityShapeFreshnessState.MISSING,
        ("absent",), ("held",), ("receipt:missing",))
    expected = dict(shape_id=TRUST["shape_id"], ok=False, freshness_state="missing",
                    errors=["absent"], blocked_reasons=["held"], evidence_refs=["receipt:missing"])
    assert check.to_dict() == expected
    report = registry.OmittedShapeFreshnessReport(
        False, datetime(2026, 10, 24, tzinfo=UTC), 1, (check,))
    assert report.to_dict() == dict(ok=False, checked_at="2026-10-24T00:00:00Z",
                                    shape_count=1, shapes=[expected])


def test_surface_identity_and_signal_helpers():
    normalize = registry.normalize_capability_surface_identity
    for value in (TRUST["shape_id"], " SURFACE/" + TRUST["shape_id"].upper() + " "):
        assert normalize(value) == TRUST["shape_id"]
    assert normalize(TRUST["shape_id"] + ".child") != TRUST["shape_id"]
    assert normalize("surface.surface.x") == "surface.x"
    for invalid in (None, 17):
        with pytest.raises(TypeError, match="exact text"):
            normalize(invalid)
    class TextSubclass(str):
        pass
    with pytest.raises(TypeError):
        normalize(TextSubclass("surface.x"))
    assert registry._normalize_surface_token(" A/B C ") == "a.b_c"
    for signal, expected in ((None, None), ("unknown:x", None),
                             (" CAPABILITY_SURFACE_DELTA:A/B C ", "a.b_c")):
        value = registry.CapabilityShapeDescriptor.model_validate(shape())
        value = value.model_copy(update={"surface_delta_signal": signal})
        assert registry._shape_signal_token(value) == expected


@pytest.mark.parametrize("enum", ["CapabilityShapeClass", "CapabilityShapeState",
    "CapabilitySurfaceDeltaAction", "CapabilityShapeFreshnessState"])
def test_unknown_shape_enums_refuse(enum):
    with pytest.raises(ValueError):
        getattr(registry, enum)("invented")


def test_extra_fields_refuse():
    for name, payload in (("CapabilityShapeDescriptor", shape()),
                          ("PrimarySourceCandidateBinding", RESEARCH["candidate_binding"]),
                          ("PrimarySourceRequestFacts", facts())):
        with pytest.raises(ValidationError, match="execution_grant"):
            getattr(registry, name).model_validate({**payload, "execution_grant": True})


ALLOCATION = set("CapabilityShapeClass CapabilityShapeDescriptor CapabilityShapeFreshnessState "
    "CapabilityShapeState CapabilitySurfaceDeltaAction CapabilitySurfaceDisposition "
    "OmittedShapeFreshnessCheck OmittedShapeFreshnessReport PrimarySourceCandidateBinding "
    "PrimarySourceCandidateCheck PrimarySourceRequestFacts _normalize_surface_token "
    "_shape_signal_token normalize_capability_surface_identity PRIMARY_SOURCE_ADMISSION_REQUIREMENTS "
    "PRIMARY_SOURCE_STOP_CONDITIONS _PRIMARY_SOURCE_DOMAIN_RE".split())
SAFE_DURATION = '''        try:
            parse_duration_spec(self.stale_after)
        except OverflowError as exc:
            raise ValueError(
                "duration exceeds timedelta range; next action: set stale_after "
                "to a representable positive duration such as 1h"
            ) from exc'''


def _parity(filename):
    """Read a hash-bound cef55b52 blob; no Council import. Separate from mutants."""
    import ast
    import hashlib
    from pathlib import Path

    raw = Path(filename).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "bcb3065e0802bc3a294571f01d745d5e1f11ed15f6905442aa5df9d2c9365bb0"

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

    original = definitions(raw.decode())
    actual = definitions(Path(registry.__file__).read_text())
    assert set(original) == set(actual) == ALLOCATION
    name = "CapabilityShapeDescriptor"
    assert actual[name].count(SAFE_DURATION) == 1
    actual[name] = actual[name].replace(SAFE_DURATION, "        parse_duration_spec(self.stale_after)")
    assert actual == original, "scope/parity drift outside the typed overflow normalization"
    print(json.dumps({"allocated_definitions": 17, "exact_definitions": 16,
                      "safer_deviation": "shape validator normalizes duration overflow"}), flush=True)


def _mutations():
    """Explicit source-only breaks; restore exact bytes after every assertion-red run."""
    import ast
    import hashlib
    import os
    from pathlib import Path
    import subprocess
    import sys
    import tempfile

    root = Path(__file__).resolve().parents[1]
    path = root / "src/hapax/spine/platform_capability_registry.py"
    assert Path(registry.__file__).resolve() == path.resolve()
    original = path.read_bytes(); source = original.decode(); tree = ast.parse(source)
    controls = []

    def change_node(label, node, code):
        lines = source.splitlines(keepends=True)
        lines[node.lineno - 1:node.end_lineno] = [" " * node.col_offset + code + "\n"]
        controls.append((label, "".join(lines).encode()))

    for cls in (n for n in tree.body if isinstance(n, ast.ClassDef) and n.name in ALLOCATION):
        for node in ast.walk(cls):
            if isinstance(node, ast.Raise):
                change_node(cls.name + ":raise:" + str(node.lineno), node, "pass")
            if isinstance(node, ast.AnnAssign):
                annotation = ast.get_source_segment(source, node.annotation)
                if annotation.startswith("Literal["):
                    line = ast.get_source_segment(source, node).replace(annotation, "Any", 1)
                    change_node(cls.name + ":literal:" + node.target.id, node, line)
                if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
                    if node.value.func.id == "Field" and any(
                        k.arg in {"ge", "gt", "le", "min_length", "pattern"} for k in node.value.keywords):
                        change_node(cls.name + ":bounds:" + node.target.id, node,
                                    node.target.id + ": " + annotation + " = Field()")
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                if isinstance(node.value.func, ast.Name) and node.value.func.id == "parse_duration_spec":
                    change_node("shape-duration-check", node, "pass")
            if cls.name == "PrimarySourceCandidateCheck" and isinstance(node, ast.Return):
                change_node("candidate-check:" + str(node.lineno), node, "return True")
        if cls.bases and isinstance(cls.bases[0], ast.Name) and cls.bases[0].id == "StrEnum":
            old = "class " + cls.name + "(StrEnum):\n"
            controls.append((cls.name + ":unknown", source.replace(old, old +
                "    @classmethod\n    def _missing_(cls, value):\n        return next(iter(cls))\n").encode()))
    for old, new, label in (
        ('ConfigDict(extra="forbid")', 'ConfigDict(extra="ignore")', "unknown-fields"),
        ('ConfigDict(extra="forbid", strict=True)', 'ConfigDict(extra="forbid")', "strict-facts"),
        ('.removeprefix("surface.")', '.replace("surface.", "")', "one-prefix-only"),
    ):
        assert source.count(old) == 1
        controls.append((label, source.replace(old, new).encode()))
    for fn in (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in
               {"normalize_capability_surface_identity", "_shape_signal_token"}):
        for node in ast.walk(fn):
            if isinstance(node, ast.Raise):
                change_node(fn.name + ":exact-text", node, "pass")
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Constant) and node.value.value is None:
                change_node(fn.name + ":none:" + str(node.lineno), node, 'return "invalid"')

    def run(label):
        env = os.environ.copy(); env.pop("PYTHONPATH", None)
        with tempfile.TemporaryDirectory(prefix="s02b-cache-") as cache:
            env["PYTHONPYCACHEPREFIX"] = cache
            r = subprocess.run([sys.executable, "-m", "pytest", "-q", str(Path(__file__).resolve())],
                               cwd=root, env=env, capture_output=True, text=True)
        output = r.stdout + r.stderr
        print(json.dumps({"phase": label, "exit": r.returncode,
                          "output_sha256": hashlib.sha256(output.encode()).hexdigest()}), flush=True)
        print(output, flush=True)
        return r.returncode

    assert run("original-green") == 0
    for label, mutant in controls:
        try:
            assert path.read_bytes() == original
            path.write_bytes(mutant)
            print(json.dumps({"mutation": label, "before_sha256": hashlib.sha256(original).hexdigest(),
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
    else:
        raise SystemExit("use --mutation-controls or --parity-source FILE")
