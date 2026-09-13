"""
config.py — BRONO platform/OS detection helper
Used by actions that need to know the current OS.
"""
import sys
import platform
import json
from pathlib import Path


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


def _get_os_setting() -> str:
    try:
        cfg_path = _base_dir() / "config" / "api_keys.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return cfg.get("os_system", "").lower()
    except Exception:
        return ""


def get_os() -> str:
    """Return 'windows', 'mac', or 'linux'."""
    setting = _get_os_setting()
    if setting in ("windows", "mac", "linux"):
        return setting
    # Auto-detect
    s = platform.system().lower()
    if s == "windows":
        return "windows"
    elif s == "darwin":
        return "mac"
    return "linux"


def is_windows() -> bool:
    return get_os() == "windows"


def is_mac() -> bool:
    return get_os() == "mac"


def is_linux() -> bool:
    return get_os() == "linux"


# Allow both function call and direct bool usage
_OS = get_os()
IS_WINDOWS = _OS == "windows"
IS_MAC = _OS == "mac"
IS_LINUX = _OS == "linux"
