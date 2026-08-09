<!-- hapax-sdlc:preamble:begin -->

# hapax-spine

`hapax-spine` is a source-available runtime mechanism in the Hapax Systems portfolio. It exposes dispatch, receipt, quota, and projection machinery without claiming to be the whole Hapax estate.

## Reader promise

Runtime mechanism package for append-only events, policy-backed routing, receipts, quotas, EDT, and projections.

## Reader value

Separates the commercial runtime mechanics behind Reins so dispatch, receipts, quotas, and projections can be inspected as mechanisms without treating them as a full estate.

## Claim ceiling

Mechanism only; not the whole Hapax estate and not fully instance-agnostic until configuration injection is complete.

## License and rights

Source-available under Business Source License 1.1; not open source until the change license/date applies. Self-hosted and non-competing production use is permitted by the Additional Use Grant; offering the licensed work as a competing hosted or managed service remains reserved.

Rendered summary: Business Source License 1.1 (source-available; not Open Source until the change license/date applies). See `LICENSE` for the authority surfaces.

## Public boundary

- Issues are redirect-only; no discussions, no pull requests accepted; see `CONTRIBUTING.md` and `SUPPORT.md`
- Public copy must use `hapax-systems` organization links for first-party Hapax repositories.
- README text is orientation, not a freshness witness; current public claims require surface-specific release, reconcile, or publication receipts.
- Publication, weblog, RSS, social, DOI/archive, and other public fanout paths must route through the governed publication bus or a documented guarded legacy surface.
- Governance reference: https://github.com/hapax-systems/hapax-constitution

## Portfolio position

Source-visible commercial core consumed by Reins and extracted from the council runtime. Not a general-purpose lifecycle kernel.

<!-- hapax-sdlc:preamble:end -->

# hapax-spine

`hapax-spine` is the source-available mechanism layer behind Reins and the
Hapax Systems governance runtime — the governed core that turns a stream of
work events into scored, routable, auditable state. It is published so
dispatch, receipts, quotas, EDT state, and projections can be inspected as
separate mechanisms rather than presented as a vague agent platform claim.

## Mechanism Map

| Mechanism | What it does | Reader value |
|---|---|---|
| Append-only events | Records lifecycle and control-plane facts as events. | Lets auditors reconstruct what happened without trusting a dashboard snapshot. |
| Policy-backed routing | Carries route, capability, and authority inputs into dispatch decisions. | Shows why a worker or tool path was allowed, refused, or held for evidence. |
| Receipts | Binds important state transitions to explicit proof records. | Gives reviewers concrete artifacts to inspect before accepting a claim. |
| Quota arithmetic | Tracks constrained provider, route, and spend capacity. | Makes capacity a governed input rather than an invisible runtime assumption. |
| EDT and projections | Folds event state into operational views. | Gives Reins and downstream surfaces compact state without making the projection itself authoritative. |

It is dependency-light (`pydantic`, `pyyaml`) and consumed by
[reins](https://github.com/hapax-systems/reins) (the cockpit) and, internally,
by hapax-council.

## Install

```sh
uv add hapax-spine        # or: pip install hapax-spine
```

## Use

```python
import hapax.spine.dispatcher_policy as dp
import hapax.spine.platform_capability_registry as reg

# The instance supplies its config-DATA dir (the registry, quota fixtures, EDT knobs)
# via HAPAX_SPINE_CONFIG_DIR (or pass an explicit path). Import is always safe; only an
# unconfigured *load* fails loud.
registry = reg.load_platform_capability_registry()          # env-injected path
sources  = dp.load_dispatch_policy_sources(registry_path=my_registry_json)  # or explicit
```

Set `HAPAX_SPINE_CONFIG_DIR` (and `HAPAX_SPINE_REPO_ROOT`) to your instance's config directory.

## Honest scope

hapax-spine ships the **mechanism**. In v0.1.x the instance **taxonomy** — the routing-class keyspace,
the reqvec dimensions, the provider/payment rails — ships as *council-default vocabulary*, not yet fully
injected (see the v1.1 instance-free milestone). So a second instance runs the same engine but currently
inherits those defaults; making the taxonomy (and the governance axioms) fully injectable is on the
roadmap. We don't claim capability-/axiom-agnosticism the code doesn't yet deliver.

The 15 modules were extracted history-preserving from hapax-council; the wheel is agents/logos-free and
imports only `pydantic` + `pyyaml`.

## Boundary

This repository is a mechanism extraction, not the whole Hapax estate and not
a general lifecycle kernel. Instance-agnostic configuration remains a claim
ceiling until the relevant configuration-injection work is complete and
released.

## License

Source-available under the **Business Source License 1.1** (see
[LICENSE](LICENSE)): free for all non-competing use — self-host, build on it,
run your own instance — converting to Apache-2.0 on the change date. Only
offering it as a competing hosted service is reserved.
