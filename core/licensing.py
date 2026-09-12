# core/licensing.py
"""
BRONO Enterprise Licensing & Fleet Management Client Engine.
Handles hardware identification (HWID), offline license token caching,
cryptographic verification, server activation, heartbeats, and feature flags.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import platform
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
LICENSE_FILE = CONFIG_DIR / "license.dat"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"

# Default Licensing Server URL — Live on Render.com (24/7 Cloud)
DEFAULT_SERVER_URL = "https://brono.onrender.com"
# Client HMAC key matching server
CLIENT_VERIFY_KEY = b"BRONO_ENTERPRISE_SECRET_KEY_99218_SECURE_HMAC"

_CACHED_HWID: str | None = None
_CACHED_LICENSE: dict | None = None
_REMOTE_CONFIG: dict = {
    "system_prompt_override": "",
    "broadcast_message": "",
    "broadcast_level": "info",
    "broadcast_active": False,
    "feature_vision": True,
    "feature_web_search": True,
    "feature_phone_dashboard": True,
    "feature_wake_word": True,
    "feature_plugins": True,
}

def get_server_url() -> str:
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
            return cfg.get("license_server_url", DEFAULT_SERVER_URL).rstrip("/")
        except Exception:
            pass
    return DEFAULT_SERVER_URL

def get_hardware_id() -> str:
    """Generate a stable, unique Hardware ID (HWID) locked to this machine."""
    global _CACHED_HWID
    if _CACHED_HWID:
        return _CACHED_HWID

    raw_id = ""
    os_name = platform.system().lower()

    if os_name == "windows":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            raw_id = str(guid).strip()
        except Exception:
            raw_id = platform.node() + "-" + platform.processor()
    elif os_name == "darwin":
        try:
            import subprocess
            out = subprocess.check_output(["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], text=True)
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    raw_id = line.split("=")[-1].strip().replace('"', '')
                    break
        except Exception:
            raw_id = platform.node()
    else:  # Linux
        for p in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
            if os.path.exists(p):
                try:
                    raw_id = Path(p).read_text().strip()
                    break
                except Exception:
                    pass
        if not raw_id:
            raw_id = platform.node()

    if not raw_id:
        import uuid
        raw_id = str(uuid.getnode())

    h = hashlib.sha256(raw_id.encode("utf-8")).hexdigest()[:20].upper()
    _CACHED_HWID = f"HWID-{h[:4]}-{h[4:8]}-{h[8:12]}-{h[12:16]}"
    return _CACHED_HWID

get_hwid = get_hardware_id

def verify_token(token: str) -> dict | None:
    """Verify cryptographically signed license token."""
    try:
        payload_b64, sig = token.strip().split(".")
        expected_sig = hmac.new(CLIENT_VERIFY_KEY, payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload_json = base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8")
        return json.loads(payload_json)
    except Exception:
        return None

def _get_appdata_file() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        p = Path(appdata) / "BRONO"
        try:
            p.mkdir(parents=True, exist_ok=True)
            return p / "license.dat"
        except Exception:
            pass
    return LICENSE_FILE

def _get_registry_token() -> str | None:
    if platform.system().lower() == "windows":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\BRONO") as key:
                val, _ = winreg.QueryValueEx(key, "LicenseToken")
                return str(val).strip()
        except Exception:
            pass
    return None

def _set_registry_token(token: str) -> None:
    if platform.system().lower() == "windows":
        try:
            import winreg
            with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\BRONO") as key:
                winreg.SetValueEx(key, "LicenseToken", 0, winreg.REG_SZ, token.strip())
        except Exception:
            pass

def check_local_license() -> tuple[bool, str, dict]:
    """
    Validates the local cached license token without needing constant internet.
    Checks local config file, AppData directory, and Windows Registry.
    Returns: (is_valid, status_or_reason, license_data)
    """
    global _CACHED_LICENSE

    token = ""
    # Tier 1: Local CONFIG_DIR / license.dat
    if LICENSE_FILE.exists():
        try:
            token = LICENSE_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    # Tier 2: %APPDATA%/BRONO/license.dat
    if not token:
        af = _get_appdata_file()
        if af.exists():
            try:
                token = af.read_text(encoding="utf-8").strip()
            except Exception:
                pass

    # Tier 3: Windows Registry HKCU\Software\BRONO\LicenseToken
    if not token:
        reg_tok = _get_registry_token()
        if reg_tok:
            token = reg_tok

    if not token:
        return False, "NO_LICENSE", {}

    try:
        data = verify_token(token)
        if not data:
            return False, "INVALID_TOKEN", {}

        # Check HWID lock
        my_hwid = get_hardware_id()
        allowed_hwids = data.get("hwids", [])
        if allowed_hwids and my_hwid not in allowed_hwids:
            return False, "HWID_MISMATCH", data

        # Check expiration date
        expires_at = data.get("expires_at")
        if expires_at:
            exp_date = datetime.fromisoformat(expires_at)
            if datetime.utcnow() > exp_date:
                return False, "EXPIRED", data

        # Check offline grace period (7 days max from last check-in)
        last_verified = data.get("verified_at")
        if last_verified:
            last_date = datetime.fromisoformat(last_verified)
            if datetime.utcnow() - last_date > timedelta(days=7):
                return False, "GRACE_EXPIRED", data

        # Keep all storage locations in sync so one-time activation is permanent
        if not LICENSE_FILE.exists():
            try:
                CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                LICENSE_FILE.write_text(token, encoding="utf-8")
            except Exception:
                pass

        _CACHED_LICENSE = data
        return True, "ACTIVE", data
    except Exception as e:
        return False, f"ERROR_{e}", {}

def save_license_token(token: str) -> bool:
    """Save valid signed token to local file, AppData, and Windows Registry."""
    token = token.strip()
    saved = False

    # 1. Local CONFIG_DIR
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        LICENSE_FILE.write_text(token, encoding="utf-8")
        saved = True
    except Exception:
        pass

    # 2. Windows AppData
    try:
        af = _get_appdata_file()
        af.write_text(token, encoding="utf-8")
        saved = True
    except Exception:
        pass

    # 3. Windows Registry
    _set_registry_token(token)
    return saved

def activate_license(license_key: str, customer_name: str = "") -> tuple[bool, str, dict]:
    """
    Sends activation request to the licensing server.
    Binds the key to this machine's HWID.
    """
    server_url = get_server_url()
    hwid = get_hardware_id()
    payload = {
        "license_key": license_key.strip().upper(),
        "hwid": hwid,
        "pc_name": platform.node(),
        "os_info": f"{platform.system()} {platform.release()}",
        "customer_name": customer_name.strip(),
        "app_version": "1.0.0",
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{server_url}/api/v1/activate",
            data=data_bytes,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "BRONO-Client/1.0",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=35) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        if resp_data.get("success"):
            token = resp_data.get("token")
            if token and save_license_token(token):
                check_local_license()
                return True, "ACTIVATION_SUCCESS", resp_data.get("license", {})
            return False, "TOKEN_SAVE_FAILED", {}
        else:
            msg = resp_data.get("message", "Activation failed.")
            return False, msg, {}

    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            return False, err_body.get("detail") or err_body.get("message") or f"Server Error {e.code}", {}
        except Exception:
            return False, f"Server Error {e.code}", {}
    except urllib.error.URLError as e:
        # Server cannot be reached — check if existing local token is still within grace period
        valid, status, data = check_local_license()
        if valid:
            return True, "OFFLINE_MODE", data
        return False, "Cannot connect to license server. Check internet.", {}
    except Exception as e:
        return False, f"Activation error: {e}", {}

def heartbeat() -> dict:
    """
    Periodic background heartbeat to sync status, fetch remote broadcasts,
    check feature flags, and detect if license was revoked remotely.
    """
    global _REMOTE_CONFIG
    valid, _, data = check_local_license()
    if not valid:
        return {}

    server_url = get_server_url()
    hwid = get_hardware_id()
    key = data.get("license_key")

    payload = {
        "license_key": key,
        "hwid": hwid,
        "app_version": "1.0.0",
    }

    try:
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{server_url}/api/v1/heartbeat",
            data=data_bytes,
            headers={"Content-Type": "application/json", "User-Agent": "BRONO-Client/1.0"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))

        if resp_data.get("revoked"):
            # License revoked remotely by admin — invalidate local license!
            if LICENSE_FILE.exists():
                try:
                    LICENSE_FILE.unlink()
                except Exception:
                    pass
            return {"revoked": True}

        # Update signed token with latest verified timestamp
        if resp_data.get("token"):
            save_license_token(resp_data["token"])

        # Update remote fleet configuration
        if "remote_config" in resp_data:
            _REMOTE_CONFIG.update(resp_data["remote_config"])

        return resp_data

    except Exception:
        return {}

def report_crash(error_msg: str, tb_str: str) -> None:
    """Silently send crash report to admin server."""
    try:
        server_url = get_server_url()
        hwid = get_hardware_id()
        data = _CACHED_LICENSE or {}
        payload = {
            "license_key": data.get("license_key", "UNLICENSED"),
            "hwid": hwid,
            "app_version": "1.0.0",
            "error_message": error_msg[:500],
            "traceback": tb_str[:4000],
        }
        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{server_url}/api/v1/telemetry/crash",
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=4)
    except Exception:
        pass

def get_license_info() -> dict:
    return _CACHED_LICENSE or {}

def get_remote_broadcast() -> dict:
    if _REMOTE_CONFIG.get("broadcast_active") and _REMOTE_CONFIG.get("broadcast_message"):
        return {
            "message": _REMOTE_CONFIG["broadcast_message"],
            "level": _REMOTE_CONFIG.get("broadcast_level", "info"),
        }
    return {}

def is_feature_enabled(name: str) -> bool:
    key = f"feature_{name}"
    return bool(_REMOTE_CONFIG.get(key, True))

def check_for_updates(current_version: str = "1.0.0") -> dict | None:
    """
    Checks both Render Fleet server and GitHub Releases API for new updates.
    Returns update info dict if a newer version exists, else None.
    """
    def _is_newer(v_latest: str, v_cur: str) -> bool:
        try:
            p_latest = [int(x) for x in v_latest.lstrip("v").split(".")]
            p_cur = [int(x) for x in v_cur.lstrip("v").split(".")]
            return p_latest > p_cur
        except Exception:
            return v_latest != v_cur and bool(v_latest)

    # 1. Check Fleet server remote_config (set by admin via Render dashboard)
    latest_ver = _REMOTE_CONFIG.get("latest_app_version", "").strip()
    download_url = _REMOTE_CONFIG.get("download_url", "").strip()
    release_notes = _REMOTE_CONFIG.get("release_notes", "").strip()

    if latest_ver and _is_newer(latest_ver, current_version):
        return {
            "has_update": True,
            "latest_version": latest_ver,
            "download_url": download_url or "https://github.com/sojolhossen/BRONO/releases",
            "release_notes": release_notes,
            "source": "fleet",
        }

    # 2. Check GitHub Releases API directly as automatic fallback
    try:
        gh_req = urllib.request.Request(
            "https://api.github.com/repos/sojolhossen/BRONO/releases/latest",
            headers={"User-Agent": "BRONO-Client/1.0", "Accept": "application/vnd.github.v3+json"}
        )
        with urllib.request.urlopen(gh_req, timeout=6) as resp:
            gh_data = json.loads(resp.read().decode("utf-8"))
            tag = gh_data.get("tag_name", "").lstrip("v").strip()
            if tag and _is_newer(tag, current_version):
                assets = gh_data.get("assets", [])
                d_url = assets[0]["browser_download_url"] if assets else gh_data.get("html_url", "")
                return {
                    "has_update": True,
                    "latest_version": tag,
                    "download_url": d_url,
                    "release_notes": gh_data.get("body", ""),
                    "source": "github",
                }
    except Exception:
        pass

    return None
