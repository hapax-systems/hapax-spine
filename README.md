<!-- hapax-sdlc:preamble:begin -->
<!-- hapax-public:surface=github.repo.hapax-spine.readme.preamble:begin -->

# hapax-spine

`hapax-spine` is a source-available runtime mechanism in the **Hapax Research Lab** portfolio ([hapaxresearch.com](https://hapaxresearch.com)). It exposes dispatch, receipt, quota, and projection machinery without claiming to be the whole Hapax estate.

## Reader promise

Runtime mechanism package for append-only events, policy-backed routing, capability receipts, quota arithmetic, EDT measurement, and projections.

## Reader value

Separates the runtime mechanics behind Reins so dispatch, receipts, quotas, and projections can be inspected and tested independently without claiming to represent a complete multi-tenant platform.

## Claim ceiling

Mechanism layer only; not the whole Hapax Research Lab estate and not yet fully taxonomy-injected across arbitrary external instances.

## License and rights

Source-available under Business Source License 1.1; not open source until the Change Date converts the work to Apache-2.0. Self-hosted and non-competing production use is permitted by the Additional Use Grant; offering the licensed work as a competing hosted or managed service remains reserved.

Rendered summary: Business Source License 1.1 (source-available; not Open Source until the Change Date converts the work to Apache-2.0). See `LICENSE`, `NOTICE.md`, `CITATION.cff`, and `.zenodo.json` for the authority surfaces.

## Public boundary

- Issues are redirect-only; no discussions, no pull requests accepted; see `CONTRIBUTING.md` and `SUPPORT.md`
- Published by **Hapax Research Lab** (`hrl-han`, [hapaxresearch.com](https://hapaxresearch.com)). Legal entity (as filed): Hapax Research LLC, organized in Wyoming on 2026-05-10, filing ID 2026-001973400.
- Security disclosures and factual correction proposals: `hrl-han@hapaxresearch.com` (see `SECURITY.md` and [hapaxresearch.com/about/#contact](https://hapaxresearch.com/about/#contact)). The network commits to receipt, retention and published correction. It promises no response time.
- Public copy uses `hapax-systems` organization links for first-party repositories; README text is orientation rather than a live runtime receipt.
- Governance reference: https://github.com/hapax-systems/hapax-constitution

## Portfolio position

Source-available runtime mechanism consumed by Reins and Hapax Research Lab's internal research runtime. Not a general-purpose lifecycle kernel.

<!-- hapax-public:surface=github.repo.hapax-spine.readme.preamble:end -->
<!-- hapax-sdlc:preamble:end -->

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

Install directly from a pinned GitHub Release tag or download source/wheel archives from [GitHub Releases (`v0.1.3`)](https://github.com/hapax-systems/hapax-spine/releases):

```sh
uv add "git+https://github.com/hapax-systems/hapax-spine.git@v0.1.3"
```

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

---

*HACA-C v0.3.15, the lab's draft rule for labelling machine-made text, not an external certification. No request to a natural person to approve the final wording, and no such approval, was found in hrl-han's sending, review and coordination records when the text was released. hrl-han releases a text once its checking is complete, under a standing rule that hrl-han's principal, who is not named in this text, adopted before the text was drafted. Review record: https://hapaxresearch.com/review-record/ (open to anyone). This label records how the text was made; it does not certify that the text is true. An unaltered record can contain false claims or miss relevant events.*
