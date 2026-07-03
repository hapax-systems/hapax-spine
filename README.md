# hapax-spine

**The SDLC-runtime mechanism behind the Hapax n-DLC automation system, as a small Python wheel.** It is
the governed core that turns a stream of work events into scored, routable, auditable state:

- an **append-only coordination event ledger** (+ its projection engine),
- a **capability registry + receipts** (capabilities identified by attested, measured behavior),
- a **dispatch-policy evaluator** (fail-closed, receipt-backed),
- **quota / spend arithmetic**, an **EDT** (equal-depth-of-treatment) fairness measurement engine, and a
  **gate-event producer** (the observational evidence stream).

It is dependency-light (`pydantic`, `pyyaml`) and consumed by [reins](https://github.com/hapax-systems/reins)
(the cockpit) and, internally, by hapax-council.

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

## License

Source-available under the **Business Source License 1.1** (see `LICENSE`): free for all non-competing
use — self-host, build on it, run your own instance — converting to Apache-2.0 on the change date. Only
offering it as a competing hosted service is reserved.
