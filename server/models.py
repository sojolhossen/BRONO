# server/models.py
import os
import sqlite3
from pathlib import Path
from datetime import datetime

_DEFAULT_DB = Path(__file__).resolve().parent / "licenses.db"
DB_PATH = Path(os.getenv("DB_PATH", str(_DEFAULT_DB)))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # Licenses table
    c.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT UNIQUE NOT NULL,
        customer_name TEXT,
        customer_email TEXT,
        plan TEXT DEFAULT 'lifetime',
        max_devices INTEGER DEFAULT 1,
        status TEXT DEFAULT 'active',
        notes TEXT,
        expires_at TEXT,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    # Devices table (bound to licenses)
    c.execute("""
    CREATE TABLE IF NOT EXISTS devices (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_id INTEGER NOT NULL,
        hwid TEXT NOT NULL,
        pc_name TEXT,
        os_info TEXT,
        app_version TEXT,
        first_activated TEXT,
        last_seen TEXT,
        FOREIGN KEY (license_id) REFERENCES licenses(id) ON DELETE CASCADE,
        UNIQUE(license_id, hwid)
    )
    """)

    # Remote Configuration & Fleet Control
    c.execute("""
    CREATE TABLE IF NOT EXISTS remote_config (
        id INTEGER PRIMARY KEY,
        system_prompt_override TEXT DEFAULT '',
        broadcast_message TEXT DEFAULT '',
        broadcast_level TEXT DEFAULT 'info',
        broadcast_active INTEGER DEFAULT 0,
        feature_vision INTEGER DEFAULT 1,
        feature_web_search INTEGER DEFAULT 1,
        feature_phone_dashboard INTEGER DEFAULT 1,
        feature_wake_word INTEGER DEFAULT 1,
        feature_plugins INTEGER DEFAULT 1,
        min_app_version TEXT DEFAULT '1.0.0',
        latest_app_version TEXT DEFAULT '1.0.0',
        download_url TEXT DEFAULT '',
        release_notes TEXT DEFAULT '',
        updated_at TEXT
    )
    """)

    # Telemetry and Crash Reports
    c.execute("""
    CREATE TABLE IF NOT EXISTS telemetry_crashes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT,
        hwid TEXT,
        app_version TEXT,
        error_message TEXT,
        traceback TEXT,
        created_at TEXT
    )
    """)

    # Admin Credentials
    c.execute("""
    CREATE TABLE IF NOT EXISTS admin_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TEXT
    )
    """)

    # Seed default remote_config row if not present
    c.execute("SELECT id FROM remote_config WHERE id = 1")
    if not c.fetchone():
        now = datetime.utcnow().isoformat()
        c.execute("""
        INSERT INTO remote_config (id, system_prompt_override, broadcast_message, broadcast_level, broadcast_active, updated_at)
        VALUES (1, '', '', 'info', 0, ?)
        """, (now,))

    # Seed default admin user (admin / admin123)
    c.execute("SELECT id FROM admin_users WHERE username = 'admin'")
    if not c.fetchone():
        from .crypto import hash_password
        now = datetime.utcnow().isoformat()
        c.execute(
            "INSERT INTO admin_users (username, password_hash, created_at) VALUES (?, ?, ?)",
            ("admin", hash_password("admin123"), now)
        )

    conn.commit()
    conn.close()
