"""hapax-spine — the SDLC-runtime MECHANISM, extracted history-preserving from hapax-council.

The append-only coord event ledger, the projection engine, the capability registry + receipts,
quota arithmetic, the dispatch-policy evaluator, the gate-event producer, and the EDT measurement
engine — the ~9.6k-LOC agents/logos-free cluster reins consumes.

v1 note (honest): the routing-class keyspace (frozen-11), reqvec dims, and provider/payment rails
ship as council-DEFAULT vocabulary, not yet fully injected — see the v1.1 instance-free milestone.
Config-DATA paths ARE injected: set HAPAX_SPINE_CONFIG_DIR (and HAPAX_SPINE_REPO_ROOT) or pass an
explicit path to the loaders; an unconfigured *load* fails loud, while *import* never raises.
"""

from hapax.spine.edt_measure import NUM_ROUTING_CLASSES, ROUTING_CLASSES

__all__ = ["ROUTING_CLASSES", "NUM_ROUTING_CLASSES"]
