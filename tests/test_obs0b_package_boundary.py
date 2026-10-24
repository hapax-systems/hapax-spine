"""Observe the installed package boundary in a fresh, unconfigured process."""
import os
from pathlib import Path
import subprocess
import sys


def test_package_import_is_inert_and_unconfigured_read_refuses(tmp_path):
    env = os.environ.copy()
    for key in ("PYTHONPATH", "HAPAX_SPINE_CONFIG_DIR", "HAPAX_SPINE_REPO_ROOT"):
        env.pop(key, None)
    code = '''
import builtins, importlib, socket, subprocess
original_import = builtins.__import__
def checked_import(name, *args, **kwargs):
    if name == "shared" or name.startswith("shared."):
        raise AssertionError("Council import: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = checked_import
def forbidden(*args, **kwargs):
    raise AssertionError("package import attempted network/subprocess")
socket.create_connection = forbidden
socket.socket.connect = forbidden
subprocess.Popen = forbidden
from hapax.spine.platform_capability_registry import load_platform_capability_registry
from hapax.spine import agentic_trust_boundary
from hapax.spine._config import default_config_path, resolve_config_path
assert str(default_config_path("platform-capability-registry.json")).startswith("/nonexistent/")
try:
    load_platform_capability_registry()
except RuntimeError as exc:
    assert "HAPAX_SPINE_CONFIG_DIR" in str(exc), str(exc)
else:
    raise AssertionError("unconfigured load silently succeeded")
'''
    result = subprocess.run([sys.executable, "-c", code], cwd=tmp_path, env=env,
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_explicit_data_path_wins_and_invalid_data_stays_error(tmp_path, monkeypatch):
    from hapax.spine._config import resolve_config_path
    from hapax.spine.platform_capability_registry import (
        PlatformCapabilityRegistryError, load_platform_capability_registry,
    )
    import pytest
    monkeypatch.setenv("HAPAX_SPINE_CONFIG_DIR", str(tmp_path / "not-a-checkout"))
    explicit = tmp_path / "invalid.json"
    explicit.write_text('{"registry_schema": 1}')
    assert resolve_config_path(explicit, "ignored.json") == explicit
    with pytest.raises(PlatformCapabilityRegistryError):
        load_platform_capability_registry(explicit)
