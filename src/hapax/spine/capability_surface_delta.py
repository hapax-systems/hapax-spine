"""Passive capability-surface delta schemas and explicit-path file reader.

Extracted from Council cef55b5216574f7eb80fd42c887c58e83f7cace0, S02a.
No intake writer, detector, host binding or provider action is included.
"""
from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class CapabilitySurfaceDeltaError(ValueError):
    """Raised when capability-surface delta fixtures fail closed."""


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


NonEmptyString = Annotated[str, Field(min_length=1)]


class SurfaceKind(StrEnum):
    MODEL_ROUTE = "model_route"
    LOCAL_TOOL = "local_tool"
    MCP_TOOL = "mcp_tool"
    ORCHESTRATOR = "orchestrator"
    REVIEW_SEAT = "review_seat"
    CCTV = "cctv"
    PUBLICATION_BUS = "publication_bus"
    MONEY_RAIL = "money_rail"
    REINS_PROJECTION = "reins_projection"


class AuthorityCeiling(StrEnum):
    AUTHORITATIVE = "authoritative"
    FRONTIER_REVIEW_REQUIRED = "frontier_review_required"
    READ_ONLY = "read_only"
    SUPPORT_ONLY = "support_only"
    UNKNOWN = "unknown"


class FreshnessState(StrEnum):
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    ABSENT = "absent"
    DARK = "dark"
    HELD = "held"
    DELTA_PENDING = "delta_pending"
    UNKNOWN = "unknown"


class DeltaKind(StrEnum):
    NEW_CAPABILITY = "new_capability"
    DESCRIPTOR_CHANGED = "descriptor_changed"
    AUTHORITY_CHANGED = "authority_changed"
    RESOURCE_POOL_CHANGED = "resource_pool_changed"
    PUBLIC_EGRESS_CHANGED = "public_egress_changed"
    MONEY_RAIL_CHANGED = "money_rail_changed"
    HARNESS_BOUNDARY_CHANGED = "harness_boundary_changed"
    ORCHESTRATION_CHILD_CHANGED = "orchestration_child_changed"
    STALE_DETERMINATION = "stale_determination"
    ABSENT_DETERMINATION = "absent_determination"


class RequiredIntakeAction(StrEnum):
    NONE = "none"
    UPDATE_DESCRIPTOR = "update_descriptor"
    MINT_INTAKE_ITEM = "mint_intake_item"
    REFRESH_RECEIPT = "refresh_receipt"
    QUARANTINE_SURFACE = "quarantine_surface"
    DEPRECATE_SURFACE = "deprecate_surface"


class CapabilitySurfaceDescriptor(StrictModel):
    descriptor_schema: Literal[1] = 1
    surface_id: str = Field(min_length=1)
    descriptor_ref: str = Field(min_length=1)
    surface_kind: SurfaceKind
    authority_ceiling: AuthorityCeiling
    observed_at: datetime
    stale_after: str
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    route_id: NonEmptyString | None = None
    supply_leaf_id: NonEmptyString | None = None
    carrier_platform: NonEmptyString | None = None
    model_id: NonEmptyString | None = None
    provider_id: NonEmptyString | None = None
    effort: NonEmptyString | None = None
    context_window: NonEmptyString | None = None
    resource_pools: list[NonEmptyString] = Field(default_factory=list)
    tool_refs: list[NonEmptyString] = Field(default_factory=list)
    harness_refs: list[NonEmptyString] = Field(default_factory=list)
    orchestration_child_refs: list[NonEmptyString] = Field(default_factory=list)
    privacy_sensitive: bool = False
    public_egress: bool = False
    money_rail: bool = False

    @model_validator(mode="after")
    def _duration_is_valid(self) -> Self:
        parse_duration_spec(self.stale_after)
        return self

    def freshness_state(self, *, now: datetime | None = None) -> FreshnessState:
        checked_now = ensure_utc(now or datetime.now(UTC))
        observed = ensure_utc(self.observed_at)
        if checked_now - observed > parse_duration_spec(self.stale_after):
            return FreshnessState.STALE
        return FreshnessState.FRESH

    def significant_signature(self) -> str:
        payload = {
            "surface_kind": self.surface_kind.value,
            "authority_ceiling": self.authority_ceiling.value,
            "route_id": self.route_id,
            "supply_leaf_id": self.supply_leaf_id,
            "carrier_platform": self.carrier_platform,
            "model_id": self.model_id,
            "provider_id": self.provider_id,
            "effort": self.effort,
            "context_window": self.context_window,
            "resource_pools": sorted(self.resource_pools),
            "tool_refs": sorted(self.tool_refs),
            "harness_refs": sorted(self.harness_refs),
            "orchestration_child_refs": sorted(self.orchestration_child_refs),
            "privacy_sensitive": self.privacy_sensitive,
            "public_egress": self.public_egress,
            "money_rail": self.money_rail,
        }
        return stable_hash(payload)


class CapabilitySurfaceDelta(StrictModel):
    delta_schema: Literal[1] = 1
    delta_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    observed_at: datetime
    detected_by: str = Field(min_length=1)
    surface_id: str = Field(min_length=1)
    delta_kind: DeltaKind
    prior_descriptor_ref: str | None = Field(default=None, min_length=1)
    observed_descriptor_ref: str | None = Field(default=None, min_length=1)
    evidence_refs: list[NonEmptyString] = Field(min_length=1)
    authority_ceiling: AuthorityCeiling
    affected_resource_pools: list[NonEmptyString]
    privacy_sensitive: bool
    public_egress: bool
    money_rail: bool
    freshness_state: FreshnessState
    required_intake_action: RequiredIntakeAction
    remediation_ref: NonEmptyString | None = None
    summary: str = Field(min_length=1)

    @model_validator(mode="after")
    def _delta_contract_is_actionable(self) -> Self:
        if self.delta_kind is DeltaKind.NEW_CAPABILITY:
            if self.prior_descriptor_ref is not None:
                raise ValueError(
                    "new capabilities require prior_descriptor_ref=null; next "
                    "action: preserve the observed descriptor ref and leave "
                    "prior_descriptor_ref null until the capability is registered"
                )
            if self.required_intake_action is not RequiredIntakeAction.MINT_INTAKE_ITEM:
                raise ValueError(
                    "new capabilities require mint_intake_item; next action: set "
                    "required_intake_action=mint_intake_item so intake owns the "
                    "descriptor admission"
                )
            if self.freshness_state is not FreshnessState.DELTA_PENDING:
                raise ValueError(
                    "new capabilities require delta_pending freshness_state; next "
                    "action: keep freshness_state=delta_pending until governed "
                    "intake admits or quarantines the descriptor"
                )
        if self.delta_kind is not DeltaKind.NEW_CAPABILITY and self.prior_descriptor_ref is None:
            raise ValueError(
                "non-new deltas require prior_descriptor_ref; next action: set it "
                "to the registered descriptor/evidence ref that is being refreshed, "
                "quarantined, or reconciled"
            )
        if (
            self.delta_kind is not DeltaKind.ABSENT_DETERMINATION
            and self.observed_descriptor_ref is None
        ):
            raise ValueError(
                "non-absent deltas require observed_descriptor_ref; next action: "
                "set it to the observed descriptor or receipt ref, or use "
                "absent_determination when no surface was observed"
            )
        if self.delta_kind in {
            DeltaKind.DESCRIPTOR_CHANGED,
            DeltaKind.AUTHORITY_CHANGED,
            DeltaKind.RESOURCE_POOL_CHANGED,
            DeltaKind.PUBLIC_EGRESS_CHANGED,
            DeltaKind.MONEY_RAIL_CHANGED,
            DeltaKind.HARNESS_BOUNDARY_CHANGED,
            DeltaKind.ORCHESTRATION_CHILD_CHANGED,
        }:
            if self.required_intake_action not in {
                RequiredIntakeAction.MINT_INTAKE_ITEM,
                RequiredIntakeAction.UPDATE_DESCRIPTOR,
                RequiredIntakeAction.QUARANTINE_SURFACE,
            }:
                raise ValueError(
                    "surface deltas require descriptor update or intake action; "
                    "next action: set required_intake_action to update_descriptor, "
                    "mint_intake_item, or quarantine_surface"
                )
            if self.freshness_state is not FreshnessState.DELTA_PENDING:
                raise ValueError(
                    "surface deltas must be delta_pending until reconciled; next "
                    "action: keep freshness_state=delta_pending until the descriptor "
                    "or intake remediation lands"
                )
        if self.delta_kind is DeltaKind.STALE_DETERMINATION:
            if self.required_intake_action is not RequiredIntakeAction.REFRESH_RECEIPT:
                raise ValueError(
                    "stale determinations require refresh_receipt; next action: "
                    "set required_intake_action=refresh_receipt and preserve the "
                    "stale witness refs"
                )
            if self.freshness_state is not FreshnessState.STALE:
                raise ValueError(
                    "stale determinations require stale freshness_state; next "
                    "action: set freshness_state=stale until a fresh receipt exists"
                )
        if self.delta_kind is DeltaKind.ABSENT_DETERMINATION:
            if self.required_intake_action not in {
                RequiredIntakeAction.MINT_INTAKE_ITEM,
                RequiredIntakeAction.QUARANTINE_SURFACE,
            }:
                raise ValueError(
                    "absent determinations require intake or quarantine; next "
                    "action: set required_intake_action to mint_intake_item or "
                    "quarantine_surface"
                )
            if self.freshness_state is not FreshnessState.ABSENT:
                raise ValueError(
                    "absent determinations require absent freshness_state; next "
                    "action: set freshness_state=absent until observation recovers"
                )
        if (
            self.required_intake_action is not RequiredIntakeAction.NONE
            and not self.remediation_ref
        ):
            raise ValueError(
                "actionable deltas require remediation_ref; next action: link the "
                "cc-task or receipt that will update, refresh, quarantine, or mint "
                "the capability surface"
            )
        return self

    def allows_demand_fulfillment(self) -> bool:
        return (
            self.delta_kind not in {DeltaKind.STALE_DETERMINATION, DeltaKind.ABSENT_DETERMINATION}
            and self.freshness_state is FreshnessState.FRESH
            and self.required_intake_action is RequiredIntakeAction.NONE
        )


class CapabilitySurfaceDeltaFile(StrictModel):
    schema_version: Literal[1] = 1
    fixture_set_id: str | None = Field(default=None, min_length=1)
    schema_ref: Literal["schemas/capability-surface-delta.schema.json"]
    generated_from: list[NonEmptyString] = Field(min_length=1)
    declared_at: datetime
    descriptors: list[CapabilitySurfaceDescriptor] = Field(min_length=1)
    deltas: list[CapabilitySurfaceDelta] = Field(min_length=1)


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def parse_duration_spec(spec: str) -> timedelta:
    count_text = spec[:-1]
    unit = spec[-1:]
    if not count_text.isdigit() or count_text.startswith("0") or unit not in {"s", "m", "h", "d"}:
        raise ValueError(
            f"invalid duration spec {spec!r}; use an integer plus s, m, h, or d; "
            "next action: set stale_after to a positive duration such as 1h or 30m"
        )
    count = int(count_text)
    if unit == "s":
        return timedelta(seconds=count)
    if unit == "m":
        return timedelta(minutes=count)
    if unit == "h":
        return timedelta(hours=count)
    return timedelta(days=count)


def stable_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise CapabilitySurfaceDeltaError(f"{path} did not contain a JSON object")
    return payload


def load_capability_surface_delta_file(path: Path) -> CapabilitySurfaceDeltaFile:
    try:
        return CapabilitySurfaceDeltaFile.model_validate(_load_json(path))
    except (OSError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        raise CapabilitySurfaceDeltaError(
            "invalid capability-surface delta producer file; repair JSON/schema "
            "or remove the configured producer path before routing can trust it; "
            f"next action: repair or unset the producer path: {exc}"
        ) from exc
