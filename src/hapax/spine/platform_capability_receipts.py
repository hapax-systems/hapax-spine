"""Typed receipts for observed coding-platform capability state.

Receipts are local evidence artifacts. They may prove wrapper, CLI, config,
tool, provider-doc, and quota-observation state, but they do not grant task
authority by themselves.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    ValidationInfo,
    model_validator,
)

from hapax.spine.agentic_trust_boundary import is_syntactically_typed_policy_evidence_reference
from hapax.spine.quota_spend_ledger import _reject_private_or_identity_refs

DEFAULT_PLATFORM_CAPABILITY_RECEIPT_DIR = (
    Path.home() / ".cache" / "hapax" / "platform-capability-receipts"
)
PLATFORM_CAPABILITY_RECEIPT_DIR_ENV = "HAPAX_PLATFORM_CAPABILITY_RECEIPT_DIR"
RECEIPT_SCHEMA_VERSION = 1
_DURATION_RE = re.compile(r"^(?P<count>[1-9][0-9]*)(?P<unit>s|m|h|d)$")


class PlatformCapabilityReceiptError(ValueError):
    """Raised when platform capability receipts are malformed."""


class StrictReceiptModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceStatus(StrEnum):
    OBSERVED = "observed"
    BLOCKED = "blocked"
    MISSING = "missing"
    UNOBSERVABLE = "unobservable"
    ERROR = "error"


class CliEvidence(StrictReceiptModel):
    binary: str
    available: bool
    version: str | None = None
    error: str | None = None


class WrapperEvidence(StrictReceiptModel):
    path: str
    exists: bool
    executable: bool
    sha256: str | None = None


class ConfigEvidence(StrictReceiptModel):
    path: str
    exists: bool
    redacted: Literal[True] = True


class ToolEvidence(StrictReceiptModel):
    tool_id: str
    available: bool
    authority_use: list[str] = Field(default_factory=list)
    evidence_ref: str

    @model_validator(mode="after")
    def _evidence_reference_retains_its_type(self) -> Self:
        if not is_syntactically_typed_policy_evidence_reference(self.evidence_ref):
            raise ValueError(
                "tool evidence_ref must be a namespaced non-observation policy reference"
            )
        return self


class SurfaceEvidence(StrictReceiptModel):
    status: EvidenceStatus
    source: str
    observed_at: datetime
    stale_after: str
    evidence_refs: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _evidence_or_reason(self) -> Self:
        parse_duration_spec(self.stale_after)
        if self.status is EvidenceStatus.OBSERVED and not self.evidence_refs:
            raise ValueError("observed surface evidence requires evidence_refs")
        if any(
            not is_syntactically_typed_policy_evidence_reference(ref) for ref in self.evidence_refs
        ):
            raise ValueError(
                "surface evidence_refs must be namespaced non-observation policy references"
            )
        if self.status is not EvidenceStatus.OBSERVED and not self.reason_codes:
            raise ValueError("non-observed surface evidence requires reason_codes")
        return self


class ProviderDocsEvidence(StrictReceiptModel):
    refs: list[str] = Field(min_length=1)
    fetched_at: datetime
    stale_after: str
    fetch_status: EvidenceStatus = EvidenceStatus.OBSERVED

    @model_validator(mode="after")
    def _duration_is_valid(self) -> Self:
        parse_duration_spec(self.stale_after)
        if any(not is_syntactically_typed_policy_evidence_reference(ref) for ref in self.refs):
            raise ValueError(
                "provider-doc refs must be namespaced non-observation policy references"
            )
        return self


class BareHostCliProbeReceiptV1(StrictReceiptModel):
    """Evidence-only landing for one bare-host CLI observation.

    These receipts are not ``PlatformCapabilityReceipt`` rows and must not be
    written as top-level ``*.json`` in the route-overlay directory: that loader
    glob-parses every such file as a platform receipt.
    """

    receipt_schema: Literal[1] = RECEIPT_SCHEMA_VERSION
    receipt_class: Literal["BareHostCliProbeReceiptV1"] = "BareHostCliProbeReceiptV1"
    receipt_id: str
    host: str
    cli: str
    shape_id: str
    outcome: Literal["observed", "absent", "not_observable"]
    observed_at: datetime | None
    stale_after: str
    demand_eligible: Literal[False] = False
    evidence_refs: list[str] = Field(default_factory=list)
    blocked_reasons: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _not_supply_and_duration_is_valid(self) -> Self:
        parse_duration_spec(self.stale_after)
        if self.demand_eligible:
            raise ValueError("bare-host CLI probe receipts cannot be demand_eligible")
        if self.outcome == "observed" and self.observed_at is None:
            raise ValueError("observed bare-host receipts require observed_at")
        if self.outcome != "observed" and self.observed_at is not None:
            raise ValueError("unobserved bare-host receipts must not carry observed_at")
        if self.outcome == "absent" and not self.evidence_refs:
            raise ValueError("absent CLI receipts require a negative-probe evidence_ref")
        if self.outcome == "not_observable" and self.evidence_refs:
            raise ValueError("not-observable receipts must not cite a probe as evidence")
        return self


EntitlementLabel = Annotated[str, Field(strict=True, pattern=r"^[a-z][a-z0-9_.-]{0,95}$")]

class EntitlementMetadata(StrictReceiptModel):
    """Owner-exported account evidence; never authentication or admission by itself.

    The composition root establishes custody before supplying this metadata.
    Identity-bearing tenant names must be replaced upstream with opaque digests.
    """

    provider: EntitlementLabel
    product: EntitlementLabel
    auth_origin: EntitlementLabel
    tenant_ref: str = Field(strict=True, pattern=r"^tenant:[0-9a-f]{64}$")
    cohort: EntitlementLabel
    pool_id: EntitlementLabel
    policy_digest: str = Field(strict=True, pattern=r"^[0-9a-f]{64}$")
    observed_at: datetime
    fresh_until: datetime
    credit_expires_at: datetime | None = None
    supported_knobs: dict[EntitlementLabel, tuple[EntitlementLabel, ...]]
    included_only: bool
    payg_fallback_allowed: bool
    evidence_refs: tuple[Annotated[str, Field(strict=True)], ...] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _literal_policy(cls, value: Any) -> Any:
        if isinstance(value, dict) and (
            ("included_only" in value and value["included_only"] is not True)
            or ("payg_fallback_allowed" in value and value["payg_fallback_allowed"] is not False)
        ):
            raise ValueError(
                "entitlement policy must be included-only; next action: supply disabled PAYG evidence"
            )
        return value

    @model_validator(mode="after")
    def _metadata_contract(self, info: ValidationInfo) -> Self:
        now = (info.context or {}).get("now", datetime.now(UTC))
        times = [self.observed_at, self.fresh_until, now]
        if self.credit_expires_at is not None:
            times.append(self.credit_expires_at)
        if any(t.utcoffset() is None for t in times):
            raise ValueError("entitlement times must be aware; next action: retain source timezone")
        if self.observed_at > now or self.fresh_until <= self.observed_at:
            raise ValueError(
                "entitlement clock invalid; next action: obtain fresh account metadata"
            )
        _reject_private_or_identity_refs(list(self.evidence_refs), "entitlement")
        if any(not is_syntactically_typed_policy_evidence_reference(r) for r in self.evidence_refs):
            raise ValueError(
                "entitlement evidence must be typed; next action: supply source references"
            )
        return self

class DeltaResolution(StrictReceiptModel):
    """Evidence only; independent verification is a Python dependency, never a JSON flag."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    delta_id: str = Field(strict=True, min_length=1)
    surface_id: str = Field(strict=True, min_length=1)
    descriptor_signature: str = Field(strict=True, pattern=r"^[0-9a-f]{64}$")
    configuration_digest: str = Field(strict=True, pattern=r"^[0-9a-f]{64}$")
    route_id: str = Field(strict=True, min_length=1)
    disposition: Literal["admitted"]
    admission_refs: tuple[Annotated[str, Field(strict=True)], ...] = Field(min_length=1)
    observed_at: AwareDatetime
    fresh_until: AwareDatetime
    revoked: bool = Field(strict=True)

    @model_validator(mode="after")
    def _resolution_contract(self) -> Self:
        if (
            self.fresh_until <= self.observed_at
            or any(
                not value.strip() or value != value.strip()
                for value in (self.delta_id, self.surface_id, self.route_id)
            )
            or any(
                not is_syntactically_typed_policy_evidence_reference(r) for r in self.admission_refs
            )
        ):
            raise ValueError(
                "invalid resolution; next action: supply typed refs, identities and ordered times"
            )
        return self

    def is_current(self, now: datetime) -> bool:
        return not self.revoked and self.observed_at <= now < self.fresh_until


class PlatformCapabilityReceipt(StrictReceiptModel):
    receipt_schema: Literal[1] = RECEIPT_SCHEMA_VERSION
    receipt_id: str
    platform: str
    routes: list[str] = Field(min_length=1)
    observed_at: datetime
    stale_after: str
    cli: CliEvidence
    wrapper: WrapperEvidence
    route_wrappers: dict[str, WrapperEvidence] = Field(default_factory=dict)
    config_refs: list[ConfigEvidence] = Field(default_factory=list)
    # Support observations only; these never establish route eligibility or
    # semantic compliance. Native loading stays unobserved without loader receipts.
    load_sets: dict[str, dict[str, Any]] = Field(default_factory=dict)
    tool_state: list[ToolEvidence] = Field(default_factory=list)
    mcp_status: list[str] = Field(default_factory=list)
    capability: SurfaceEvidence
    resource: SurfaceEvidence
    quota: SurfaceEvidence
    provider_docs: ProviderDocsEvidence
    known_unknowns: list[str] = Field(default_factory=list)
    entitlement_metadata: EntitlementMetadata | None = None
    delta_resolution: DeltaResolution | None = None

    @model_validator(mode="after")
    def _duration_is_valid(self) -> Self:
        parse_duration_spec(self.stale_after)
        return self


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_duration_spec(spec: str) -> timedelta:
    match = _DURATION_RE.fullmatch(spec)
    if match is None:
        raise ValueError(f"invalid duration spec {spec!r}; use an integer plus s, m, h, or d")
    count = int(match.group("count"))
    unit = match.group("unit")
    if unit == "s":
        return timedelta(seconds=count)
    if unit == "m":
        return timedelta(minutes=count)
    if unit == "h":
        return timedelta(hours=count)
    return timedelta(days=count)


def receipt_reference(receipt: PlatformCapabilityReceipt) -> str:
    return f"platform-capability-receipt:{receipt.platform}:{receipt.receipt_id}"


def receipt_is_fresh(
    receipt: PlatformCapabilityReceipt,
    *,
    now: datetime | None = None,
) -> bool:
    checked_now = ensure_utc(now or datetime.now(UTC))
    observed_at = ensure_utc(receipt.observed_at)
    if observed_at > checked_now + timedelta(minutes=1):
        return False
    return checked_now - observed_at <= parse_duration_spec(receipt.stale_after)


def _load_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PlatformCapabilityReceiptError(f"{path} did not contain a JSON object")
    return payload


def load_platform_capability_receipt(path: Path) -> PlatformCapabilityReceipt:
    try:
        return PlatformCapabilityReceipt.model_validate(_load_json_object(path))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise PlatformCapabilityReceiptError(f"invalid platform receipt at {path}: {exc}") from exc


def load_platform_capability_receipts(
    receipt_dir: Path,
    *,
    now: datetime | None = None,
) -> dict[str, PlatformCapabilityReceipt]:
    """Load the newest fresh receipt per platform from a directory."""

    if not receipt_dir.exists():
        return {}
    receipts: dict[str, PlatformCapabilityReceipt] = {}
    for path in sorted(receipt_dir.glob("*.json")):
        receipt = load_platform_capability_receipt(path)
        if not receipt_is_fresh(receipt, now=now):
            continue
        prior = receipts.get(receipt.platform)
        if prior is None or ensure_utc(receipt.observed_at) > ensure_utc(prior.observed_at):
            receipts[receipt.platform] = receipt
    return receipts


_PYDANTIC_DYNAMIC_ENTRYPOINTS = (
    DeltaResolution._resolution_contract,
    EntitlementMetadata._literal_policy,
    EntitlementMetadata._metadata_contract,
    SurfaceEvidence._evidence_or_reason,
    ProviderDocsEvidence._duration_is_valid,
    PlatformCapabilityReceipt._duration_is_valid,
    BareHostCliProbeReceiptV1._not_supply_and_duration_is_valid,
)
