<!-- hapax-sdlc:preamble:begin -->

# hapax-spine

`hapax-spine` is a source-available runtime mechanism from **Hapax Research Lab** ([hapaxresearch.com](https://hapaxresearch.com)). It exposes append-only event ledgers, policy-backed routing, capability receipts, quota arithmetic, EDT measurement, and projections as inspectable mechanisms behind [reins](https://github.com/hapax-systems/reins).

## Reader promise

Runtime mechanism package (`v0.1.3`) for append-only events, policy-backed routing, capability receipts, quota arithmetic, EDT measurement, and projections.

## Reader value

Separates the runtime mechanics behind Reins so dispatch, receipts, quotas, and projections can be inspected and tested independently without claiming to represent a complete multi-tenant platform.

## Claim ceiling

Mechanism layer only; not a general-purpose lifecycle kernel and not yet fully taxonomy-injected across arbitrary external instances.

## License and rights

Source-available under **Business Source License 1.1**; not open source until the Change Date converts the work to Apache-2.0. Self-hosted and non-competing production use is permitted by the Additional Use Grant; offering the licensed work as a competing hosted or managed service remains reserved. See [LICENSE](LICENSE).

## Public boundary

- Issues are redirect-only; no discussions and no unsolicited pull requests are accepted; see [CONTRIBUTING.md](CONTRIBUTING.md) and [SUPPORT.md](SUPPORT.md).
- Security disclosures and factual correction proposals: [hrl-han@hapaxresearch.com](mailto:hrl-han@hapaxresearch.com) (see [SECURITY.md](SECURITY.md) and [hapaxresearch.com/about/#contact](https://hapaxresearch.com/about/#contact)).
- Governance reference: [hapax-constitution](https://github.com/hapax-systems/hapax-constitution).

<!-- hapax-sdlc:preamble:end -->

# hapax-spine

`hapax-spine` (`0.1.3`) is the source-available runtime mechanism layer developed by **Hapax Research Lab** behind [reins](https://github.com/hapax-systems/reins) — turning an append-only stream of lifecycle events into scored, routable, receipted state.

## Mechanism Map

| Mechanism | What it does | Reader value |
|---|---|---|
| Append-only events | Records lifecycle and control-plane transitions as immutable JSONL events. | Lets auditors reconstruct execution history without relying on mutable snapshots. |
| Policy-backed routing | Evaluates route, capability, and authority constraints before dispatch. | Shows why a worker or tool route was permitted, refused, or held for fresh evidence. |
| Capability receipts | Binds state transitions and probes to structured, schema-checked proof records. | Gives reviewers concrete artifacts to inspect before accepting a capability claim. |
| Quota arithmetic | Tracks constrained provider, subscription, and transition-budget capacity. | Treats capacity and spend ceilings as explicit policy inputs rather than implicit assumptions. |
| EDT and projections | Folds event history into compact operational views. | Supplies Reins and downstream surfaces deterministic state views while keeping the ledger authoritative. |

The package is dependency-light (`pydantic`, `pyyaml`) and consumed by [reins](https://github.com/hapax-systems/reins) and Hapax Research Lab's internal research runtime.

## Install

```sh
uv add hapax-spine        # or: pip install hapax-spine
```

Current release: `v0.1.3` ([GitHub Releases](https://github.com/hapax-systems/hapax-spine/releases)).

## Use

```python
import hapax.spine.dispatcher_policy as dp
import hapax.spine.platform_capability_registry as reg

# Supply your instance configuration directory via HAPAX_SPINE_CONFIG_DIR
# or pass an explicit path. Package import is side-effect-free; an unconfigured
# load fails explicitly.
registry = reg.load_platform_capability_registry()
sources = dp.load_dispatch_policy_sources(registry_path=my_registry_json)
```

Set `HAPAX_SPINE_CONFIG_DIR` (and `HAPAX_SPINE_REPO_ROOT` when applicable) to your instance's configuration directory.

## Scope & Limitations

`hapax-spine` ships the **mechanism** (15 pure-Python modules importing only `pydantic` and `pyyaml`). In `v0.1.x`, the default routing-class keyspace, requirement-vector dimensions, and provider/payment-rail identifiers reflect Hapax Research Lab's default vocabulary; full external taxonomy injection is planned for a future milestone rather than claimed today.

## Related Hapax Research Lab Surfaces

- **Portal & commitments register:** [hapaxresearch.com](https://hapaxresearch.com)
- **Cockpit interface:** [reins](https://github.com/hapax-systems/reins)
- **Governance specification:** [hapax-constitution](https://github.com/hapax-systems/hapax-constitution)
- **Numeric evidence ledger:** [hapax-research-ledger](https://github.com/hapax-systems/hapax-research-ledger)

## License

Source-available under the **Business Source License 1.1** (see [LICENSE](LICENSE)): free for self-hosted and non-competing production use under the Additional Use Grant, converting to Apache-2.0 on the Change Date (`2030-07-03`). Offering the work to third parties as a competing hosted or managed service is reserved.
