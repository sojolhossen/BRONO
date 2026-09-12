# server/app.py
from __future__ import annotations

import os
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Response, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .models import init_db, get_db
from .crypto import (
    generate_license_key, hash_password, verify_password,
    sign_activation_payload, verify_activation_token,
    sign_admin_session, verify_admin_session
)

app = FastAPI(title="BRONO Enterprise Licensing Platform", version="1.0.0")

# Enable CORS so client requests or web dashboards can reach endpoints
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)
TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)

# ── Session & Auth Helper ───────────────────────────────────────────────────
def require_admin(request: Request):
    token = request.cookies.get("brono_admin_session")
    if not token or not verify_admin_session(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return token

# ── Request / Response Schemas ──────────────────────────────────────────────
class ActivateRequest(BaseModel):
    license_key: str
    hwid: str
    pc_name: Optional[str] = ""
    os_info: Optional[str] = ""
    customer_name: Optional[str] = ""
    app_version: Optional[str] = "1.0.0"

class HeartbeatRequest(BaseModel):
    license_key: str
    hwid: str
    app_version: Optional[str] = "1.0.0"

class CrashReportRequest(BaseModel):
    license_key: Optional[str] = "UNLICENSED"
    hwid: str
    app_version: Optional[str] = "1.0.0"
    error_message: str
    traceback: str

class CreateLicenseRequest(BaseModel):
    count: int = 1
    plan: str = "lifetime"   # trial, monthly, annual, lifetime, enterprise
    max_devices: int = 1
    duration_days: Optional[int] = None
    customer_name: Optional[str] = ""
    customer_email: Optional[str] = ""
    notes: Optional[str] = ""

class RemoteConfigUpdate(BaseModel):
    system_prompt_override: Optional[str] = ""
    broadcast_message: Optional[str] = ""
    broadcast_level: Optional[str] = "info"
    broadcast_active: Optional[bool] = False
    feature_vision: Optional[bool] = True
    feature_web_search: Optional[bool] = True
    feature_phone_dashboard: Optional[bool] = True
    feature_wake_word: Optional[bool] = True
    feature_plugins: Optional[bool] = True
    min_app_version: Optional[str] = "1.0.0"
    latest_app_version: Optional[str] = "1.0.0"
    download_url: Optional[str] = ""
    release_notes: Optional[str] = ""

class LoginRequest(BaseModel):
    username: str
    password: str

# ── Database Startup & Admin Seeding ────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    init_db()
    conn = get_db()
    c = conn.cursor()
    # Check if default admin user exists
    c.execute("SELECT id FROM admin_users WHERE username = 'admin'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("admin", hash_password("admin123"), datetime.utcnow().isoformat())
        )
        conn.commit()
    conn.close()

# ── Client Licensing APIs ───────────────────────────────────────────────────

@app.post("/api/v1/activate")
def activate_license(req: ActivateRequest):
    key = req.license_key.strip().upper()
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM licenses WHERE license_key = ?", (key,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Invalid license key.")

    lic = dict(row)
    if lic["status"] != "active":
        conn.close()
        raise HTTPException(status_code=403, detail=f"License is currently {lic['status'].upper()}. Contact support.")

    now = datetime.utcnow()
    # Check expiration
    if lic["expires_at"]:
        exp = datetime.fromisoformat(lic["expires_at"])
        if now > exp:
            c.execute("UPDATE licenses SET status = 'expired' WHERE id = ?", (lic["id"],))
            conn.commit()
            conn.close()
            raise HTTPException(status_code=403, detail="License has expired.")

    # Check devices
    c.execute("SELECT * FROM devices WHERE license_id = ?", (lic["id"],))
    devices = [dict(d) for d in c.fetchall()]
    existing_hwids = [d["hwid"] for d in devices]

    if req.hwid not in existing_hwids:
        if len(devices) >= lic["max_devices"]:
            conn.close()
            raise HTTPException(
                status_code=403,
                detail=f"Device limit reached ({lic['max_devices']}). Locked to other computer(s)."
            )
        # Register this device
        c.execute("""
        INSERT INTO devices (license_id, hwid, pc_name, os_info, app_version, first_activated, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (lic["id"], req.hwid, req.pc_name, req.os_info, req.app_version, now.isoformat(), now.isoformat()))
        existing_hwids.append(req.hwid)

        # Update customer name if provided
        if req.customer_name and not lic["customer_name"]:
            c.execute("UPDATE licenses SET customer_name = ? WHERE id = ?", (req.customer_name, lic["id"]))

    else:
        # Existing device — update last_seen and info
        c.execute("""
        UPDATE devices SET last_seen = ?, pc_name = ?, os_info = ?, app_version = ?
        WHERE license_id = ? AND hwid = ?
        """, (now.isoformat(), req.pc_name, req.os_info, req.app_version, lic["id"], req.hwid))

    conn.commit()

    # Generate cryptographically signed token
    payload = {
        "license_key": key,
        "customer_name": lic["customer_name"] or req.customer_name,
        "plan": lic["plan"],
        "expires_at": lic["expires_at"],
        "hwids": existing_hwids,
        "verified_at": now.isoformat(),
    }
    token = sign_activation_payload(payload)
    conn.close()

    return {
        "success": True,
        "message": "Activation successful.",
        "token": token,
        "license": {
            "key": key,
            "plan": lic["plan"].upper(),
            "customer_name": lic["customer_name"] or req.customer_name,
            "expires_at": lic["expires_at"],
            "max_devices": lic["max_devices"],
        }
    }


@app.post("/api/v1/heartbeat")
def client_heartbeat(req: HeartbeatRequest):
    key = req.license_key.strip().upper()
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT * FROM licenses WHERE license_key = ?", (key,))
    lic_row = c.fetchone()
    if not lic_row:
        conn.close()
        return {"revoked": True, "message": "License not found."}

    lic = dict(lic_row)
    if lic["status"] != "active":
        conn.close()
        return {"revoked": True, "message": f"License {lic['status']}."}

    now = datetime.utcnow()
    # Update device last_seen
    c.execute("""
    UPDATE devices SET last_seen = ?, app_version = ?
    WHERE license_id = ? AND hwid = ?
    """, (now.isoformat(), req.app_version, lic["id"], req.hwid))
    conn.commit()

    # Get remote fleet config
    c.execute("SELECT * FROM remote_config WHERE id = 1")
    cfg_row = c.fetchone()
    remote_cfg = dict(cfg_row) if cfg_row else {}

    # Refreshed signed token
    c.execute("SELECT hwid FROM devices WHERE license_id = ?", (lic["id"],))
    hwids = [r["hwid"] for r in c.fetchall()]
    payload = {
        "license_key": key,
        "customer_name": lic["customer_name"],
        "plan": lic["plan"],
        "expires_at": lic["expires_at"],
        "hwids": hwids,
        "verified_at": now.isoformat(),
    }
    token = sign_activation_payload(payload)
    conn.close()

    return {
        "revoked": False,
        "token": token,
        "remote_config": {
            "system_prompt_override": remote_cfg.get("system_prompt_override", ""),
            "broadcast_message": remote_cfg.get("broadcast_message", ""),
            "broadcast_level": remote_cfg.get("broadcast_level", "info"),
            "broadcast_active": bool(remote_cfg.get("broadcast_active", 0)),
            "feature_vision": bool(remote_cfg.get("feature_vision", 1)),
            "feature_web_search": bool(remote_cfg.get("feature_web_search", 1)),
            "feature_phone_dashboard": bool(remote_cfg.get("feature_phone_dashboard", 1)),
            "feature_wake_word": bool(remote_cfg.get("feature_wake_word", 1)),
            "feature_plugins": bool(remote_cfg.get("feature_plugins", 1)),
            "latest_app_version": remote_cfg.get("latest_app_version", "1.0.0"),
            "min_app_version": remote_cfg.get("min_app_version", "1.0.0"),
            "download_url": remote_cfg.get("download_url", ""),
            "release_notes": remote_cfg.get("release_notes", ""),
        }
    }


@app.get("/api/v1/update/check")
def check_update(version: str = "1.0.0"):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM remote_config WHERE id = 1")
    row = c.fetchone()
    conn.close()
    if not row:
        return {"has_update": False}

    cfg = dict(row)
    latest = cfg.get("latest_app_version", "1.0.0")
    min_ver = cfg.get("min_app_version", "1.0.0")

    # Simple semver check
    has_update = latest != version
    force_update = version < min_ver

    return {
        "has_update": has_update,
        "current_version": version,
        "latest_version": latest,
        "force_update": force_update,
        "download_url": cfg.get("download_url", ""),
        "release_notes": cfg.get("release_notes", ""),
    }


@app.post("/api/v1/telemetry/crash")
def report_crash(req: CrashReportRequest):
    conn = get_db()
    c = conn.cursor()
    c.execute("""
    INSERT INTO telemetry_crashes (license_key, hwid, app_version, error_message, traceback, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (req.license_key, req.hwid, req.app_version, req.error_message, req.traceback, datetime.utcnow().isoformat()))
    conn.commit()
    conn.close()
    return {"status": "recorded"}


# ── Admin Authentication & Web Routes ───────────────────────────────────────

@app.post("/api/admin/login")
def admin_login(req: LoginRequest, response: Response):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT password_hash FROM admin_users WHERE username = ?", (req.username.strip(),))
    row = c.fetchone()
    conn.close()

    if not row or not verify_password(req.password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Invalid username or password.")

    session_token = sign_admin_session(req.username.strip(), days=30)
    response.set_cookie(
        key="brono_admin_session",
        value=session_token,
        httponly=True,
        max_age=86400 * 30,  # 30 days
        samesite="lax",
    )
    return {"success": True, "message": "Login successful."}


@app.post("/api/admin/logout")
def admin_logout(response: Response):
    response.delete_cookie("brono_admin_session")
    return {"success": True}


@app.get("/api/admin/stats")
def get_stats(_: str = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT count(*) as total FROM licenses")
    total_licenses = c.fetchone()["total"]

    c.execute("SELECT count(*) as active FROM licenses WHERE status = 'active'")
    active_licenses = c.fetchone()["active"]

    c.execute("SELECT count(*) as devices FROM devices")
    total_devices = c.fetchone()["devices"]

    c.execute("SELECT count(*) as crashes FROM telemetry_crashes")
    total_crashes = c.fetchone()["crashes"]

    # Plan distribution
    c.execute("SELECT plan, count(*) as cnt FROM licenses GROUP BY plan")
    plan_dist = {r["plan"]: r["cnt"] for r in c.fetchall()}

    conn.close()
    return {
        "total_licenses": total_licenses,
        "active_licenses": active_licenses,
        "total_devices": total_devices,
        "total_crashes": total_crashes,
        "plan_distribution": plan_dist,
    }


@app.get("/api/admin/licenses")
def list_licenses(_: str = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM licenses ORDER BY id DESC")
    lic_rows = c.fetchall()

    results = []
    for row in lic_rows:
        item = dict(row)
        c.execute("SELECT hwid, pc_name, os_info, last_seen, first_activated FROM devices WHERE license_id = ?", (item["id"],))
        item["devices"] = [dict(d) for d in c.fetchall()]
        results.append(item)

    conn.close()
    return {"licenses": results}


@app.post("/api/admin/licenses/create")
def create_licenses(req: CreateLicenseRequest, _: str = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()

    now = datetime.utcnow()
    expires_at = None
    if req.plan == "trial":
        days = req.duration_days or 7
        expires_at = (now + timedelta(days=days)).isoformat()
    elif req.plan == "monthly":
        days = req.duration_days or 30
        expires_at = (now + timedelta(days=days)).isoformat()
    elif req.plan == "annual":
        days = req.duration_days or 365
        expires_at = (now + timedelta(days=days)).isoformat()
    elif req.duration_days:
        expires_at = (now + timedelta(days=req.duration_days)).isoformat()

    created_keys = []
    for _ in range(max(1, min(req.count, 100))):
        key = generate_license_key()
        c.execute("""
        INSERT INTO licenses (license_key, customer_name, customer_email, plan, max_devices, status, notes, expires_at, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)
        """, (key, req.customer_name, req.customer_email, req.plan, req.max_devices, req.notes, expires_at, now.isoformat(), now.isoformat()))
        created_keys.append(key)

    conn.commit()
    conn.close()
    return {"success": True, "created_keys": created_keys, "count": len(created_keys)}


@app.post("/api/admin/licenses/{license_id}/action")
def license_action(license_id: int, action: str, _: str = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()

    if action == "revoke":
        c.execute("UPDATE licenses SET status = 'revoked', updated_at = ? WHERE id = ?", (datetime.utcnow().isoformat(), license_id))
    elif action == "activate":
        c.execute("UPDATE licenses SET status = 'active', updated_at = ? WHERE id = ?", (datetime.utcnow().isoformat(), license_id))
    elif action == "reset_hwid":
        # Unbind all devices from this license so customer can bind to a new PC
        c.execute("DELETE FROM devices WHERE license_id = ?", (license_id,))
    elif action == "delete":
        c.execute("DELETE FROM devices WHERE license_id = ?", (license_id,))
        c.execute("DELETE FROM licenses WHERE id = ?", (license_id,))
    else:
        conn.close()
        raise HTTPException(status_code=400, detail="Unknown action")

    conn.commit()
    conn.close()
    return {"success": True, "action": action}


@app.get("/api/admin/config")
def get_remote_config(_: str = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM remote_config WHERE id = 1")
    row = c.fetchone()
    conn.close()
    return dict(row) if row else {}


@app.post("/api/admin/config")
def update_remote_config(req: RemoteConfigUpdate, _: str = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    now = datetime.utcnow().isoformat()
    c.execute("""
    UPDATE remote_config SET
        system_prompt_override = ?,
        broadcast_message = ?,
        broadcast_level = ?,
        broadcast_active = ?,
        feature_vision = ?,
        feature_web_search = ?,
        feature_phone_dashboard = ?,
        feature_wake_word = ?,
        feature_plugins = ?,
        min_app_version = ?,
        latest_app_version = ?,
        download_url = ?,
        release_notes = ?,
        updated_at = ?
    WHERE id = 1
    """, (
        req.system_prompt_override, req.broadcast_message, req.broadcast_level,
        int(req.broadcast_active or 0), int(req.feature_vision or 0), int(req.feature_web_search or 0),
        int(req.feature_phone_dashboard or 0), int(req.feature_wake_word or 0), int(req.feature_plugins or 0),
        req.min_app_version, req.latest_app_version, req.download_url, req.release_notes, now
    ))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Fleet configuration updated."}


@app.get("/api/admin/crashes")
def get_crash_reports(_: str = Depends(require_admin)):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM telemetry_crashes ORDER BY id DESC LIMIT 50")
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return {"crashes": rows}


# ── Web UI Pages ────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index_page(request: Request):
    token = request.cookies.get("brono_admin_session")
    if not token or token not in ADMIN_SESSIONS:
        return RedirectResponse("/login")
    dash_html = (TEMPLATES_DIR / "dashboard.html").read_text(encoding="utf-8")
    return HTMLResponse(content=dash_html)


@app.get("/login", response_class=HTMLResponse)
def login_page():
    login_html = (TEMPLATES_DIR / "login.html").read_text(encoding="utf-8")
    return HTMLResponse(content=login_html)
