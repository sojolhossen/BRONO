"""
BRONO Unified Persistent Paths Manager
Ensures that all user settings, memory, credentials, and licenses are stored
in the operating system's persistent user data directory (%APPDATA%\\BRONO on Windows).
This guarantees that updates, new .exe builds, or extracting to a new folder
NEVER erase user data, API keys, or conversation memories!
"""
import os
import sys
import platform
import shutil
from pathlib import Path

def get_install_dir() -> Path:
    """Returns the base application installation directory."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def get_user_data_dir() -> Path:
    """Returns the persistent user data directory (%APPDATA%\\BRONO on Windows)."""
    if platform.system() == "Windows":
        app_data = os.getenv("APPDATA")
        base = Path(app_data) if app_data else Path.home() / "AppData" / "Roaming"
        p = base / "BRONO"
    else:
        p = Path.home() / ".brono"
    p.mkdir(parents=True, exist_ok=True)
    return p

# ── Directory roots ──
INSTALL_DIR = get_install_dir()
DATA_DIR    = get_user_data_dir()

# ── Config Directory & Files ──
APPDATA_CONFIG_DIR  = DATA_DIR / "config"
APPDATA_CONFIG_FILE = APPDATA_CONFIG_DIR / "api_keys.json"
APPDATA_LICENSE_FILE= DATA_DIR / "license.dat"

LOCAL_CONFIG_DIR    = INSTALL_DIR / "config"
LOCAL_CONFIG_FILE   = LOCAL_CONFIG_DIR / "api_keys.json"
LOCAL_LICENSE_FILE  = LOCAL_CONFIG_DIR / "license.dat"

# ── Memory Directory & Files ──
APPDATA_MEMORY_DIR  = DATA_DIR / "memory"
APPDATA_MEMORY_FILE = APPDATA_MEMORY_DIR / "long_term.json"

LOCAL_MEMORY_DIR    = INSTALL_DIR / "memory"
LOCAL_MEMORY_FILE   = LOCAL_MEMORY_DIR / "long_term.json"

def get_config_path() -> Path:
    """Returns the active config path with automatic migration from install dir."""
    APPDATA_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not APPDATA_CONFIG_FILE.exists() and LOCAL_CONFIG_FILE.exists():
        try:
            shutil.copy2(LOCAL_CONFIG_FILE, APPDATA_CONFIG_FILE)
        except Exception:
            return LOCAL_CONFIG_FILE
    return APPDATA_CONFIG_FILE

def get_memory_path() -> Path:
    """Returns the active long_term.json memory path with automatic migration."""
    APPDATA_MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    if not APPDATA_MEMORY_FILE.exists() and LOCAL_MEMORY_FILE.exists():
        try:
            shutil.copy2(LOCAL_MEMORY_FILE, APPDATA_MEMORY_FILE)
        except Exception:
            return LOCAL_MEMORY_FILE
    return APPDATA_MEMORY_FILE
