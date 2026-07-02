"""Import-safe config-DATA path resolution for hapax-spine.

The instance injects its config DATA dir (the platform-capability registry, quota fixtures, EDT knobs)
via ``HAPAX_SPINE_CONFIG_DIR`` — set it in the process env before import (council, reins, and the wheel's
own tests all do), or pass an explicit path to a loader.

INVARIANT (the extraction's verify-3 fix): module *import* NEVER raises — a module-level default is always
a real ``Path`` (a non-existent sentinel when unconfigured), so ``from hapax.spine.X import CONST`` stays
importable and typed. Only an actual *read* of an unconfigured path fails loud (the sentinel path literally
names the missing env var, so the error is self-describing).
"""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR_ENV = "HAPAX_SPINE_CONFIG_DIR"
REPO_ROOT_ENV = "HAPAX_SPINE_REPO_ROOT"

# A path under this root can never exist, so an unconfigured open() fails loud while import stays safe.
_UNCONFIGURED_ROOT = Path("/nonexistent/hapax-spine__set_HAPAX_SPINE_CONFIG_DIR")


def _injected_config_dir() -> Path | None:
    root = os.environ.get(CONFIG_DIR_ENV, "").strip()
    return Path(root).expanduser() if root else None


def default_config_path(filename: str) -> Path:
    """Eager module-constant value: the injected config dir joined to ``filename`` when the env is set at
    import, else a self-describing non-existent sentinel. NEVER raises."""
    d = _injected_config_dir()
    return (d / filename) if d is not None else (_UNCONFIGURED_ROOT / filename)


def resolve_config_path(path: Path | None, filename: str) -> Path:
    """Call-time loader resolver: an explicit ``path`` wins; else re-read the env FRESH (handles
    env-set-after-import); FAIL LOUD when neither is available."""
    if path is not None:
        return Path(path)
    d = _injected_config_dir()
    if d is None:
        raise RuntimeError(
            f"hapax-spine: cannot load {filename!r} — set {CONFIG_DIR_ENV} to the instance config dir "
            f"or pass an explicit path to the loader."
        )
    return d / filename


def repo_root() -> Path:
    """The instance repo root (``HAPAX_SPINE_REPO_ROOT``), else the config dir's parent, else a sentinel.
    Used only by relative-path resolvers that historically read council_root. Never raises."""
    root = os.environ.get(REPO_ROOT_ENV, "").strip()
    if root:
        return Path(root).expanduser()
    d = _injected_config_dir()
    return d.parent if d is not None else _UNCONFIGURED_ROOT
