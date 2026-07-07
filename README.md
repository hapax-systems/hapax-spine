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

Source-available under Business Source License 1.1; not open source until the change license/date applies. Commercial/hosted-service rights remain reserved by the BSL grant.

Rendered summary: Business Source License 1.1 (source-available; not Open Source until the change license/date applies). See `LICENSE` for the authority surfaces.

## Public boundary

- Issues are redirect-only; no discussions, no pull requests accepted; see `CONTRIBUTING.md` and `SUPPORT.md`
- Public copy must use `hapax-systems` organization links for first-party Hapax repositories.
- Publication, weblog, RSS, social, DOI/archive, and other public fanout paths must route through the governed publication bus or a documented guarded legacy surface.
- Governance reference: https://github.com/hapax-systems/hapax-constitution

## Portfolio position

Source-visible commercial core consumed by Reins and extracted from the council runtime. Not a general-purpose lifecycle kernel.

<!-- hapax-sdlc:preamble:end -->

# hapax-spine

`hapax-spine` is the source-available mechanism layer behind Reins and the
Hapax Systems governance runtime. It is published so dispatch, receipts,
quotas, EDT state, and projections can be inspected as separate mechanisms
rather than presented as a vague agent platform claim.

## Mechanism Map

| Mechanism | What it does | Reader value |
|---|---|---|
| Append-only events | Records lifecycle and control-plane facts as events. | Lets auditors reconstruct what happened without trusting a dashboard snapshot. |
| Policy-backed routing | Carries route, capability, and authority inputs into dispatch decisions. | Shows why a worker or tool path was allowed, refused, or held for evidence. |
| Receipts | Binds important state transitions to explicit proof records. | Gives reviewers concrete artifacts to inspect before accepting a claim. |
| Quota arithmetic | Tracks constrained provider, route, and spend capacity. | Makes capacity a governed input rather than an invisible runtime assumption. |
| EDT and projections | Folds event state into operational views. | Gives Reins and downstream surfaces compact state without making the projection itself authoritative. |

## Boundary

This repository is a mechanism extraction, not the whole Hapax estate and not
a general lifecycle kernel. Instance-agnostic configuration remains a claim
ceiling until the relevant configuration-injection work is complete and
released.

## License

Business Source License 1.1. Commercial and hosted-service rights remain
reserved by the license grant until the change license/date applies. See
[LICENSE](LICENSE).
