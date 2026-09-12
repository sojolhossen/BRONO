# server/crypto.py
import secrets
import string
import hashlib
import hmac
import json
import base64
from datetime import datetime, timedelta

# Master Secret used to sign activation tokens (generated once or read from file)
SECRET_KEY = b"BRONO_ENTERPRISE_SECRET_KEY_99218_SECURE_HMAC"

def generate_license_key(prefix: str = "BRONO") -> str:
    """Generate a high-entropy format: BRONO-A7B2-99F1-4C3D-88E2"""
    charset = string.ascii_uppercase + string.digits
    # Exclude ambiguous characters (0, O, 1, I)
    clean_charset = "".join(c for c in charset if c not in "0O1I")
    parts = [prefix]
    for _ in range(4):
        parts.append("".join(secrets.choice(clean_charset) for _ in range(4)))
    return "-".join(parts)

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
    return f"{salt}${key.hex()}"

def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt, key_hex = stored_hash.split("$")
        key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000)
        return hmac.compare_digest(key.hex(), key_hex)
    except Exception:
        return False

def sign_activation_payload(payload: dict) -> str:
    """
    Creates a cryptographically signed token containing license details.
    The client can store this and verify offline that the server signed it.
    """
    payload_json = json.dumps(payload, separators=(',', ':'), sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode('utf-8')).decode('utf-8')
    sig = hmac.new(SECRET_KEY, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{sig}"

def verify_activation_token(token: str) -> dict | None:
    """Verify HMAC signature and decode payload."""
    try:
        payload_b64, sig = token.strip().split(".")
        expected_sig = hmac.new(SECRET_KEY, payload_b64.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload_json = base64.urlsafe_b64decode(payload_b64.encode('utf-8')).decode('utf-8')
        return json.loads(payload_json)
    except Exception:
        return None

def sign_admin_session(username: str, days: int = 30) -> str:
    """Creates a cryptographic stateless admin session token valid for `days` days."""
    payload = {
        "user": username,
        "exp": (datetime.utcnow() + timedelta(days=days)).isoformat()
    }
    return sign_activation_payload(payload)

def verify_admin_session(token: str) -> str | None:
    """Verifies HMAC signature of admin session token and returns username if valid."""
    data = verify_activation_token(token)
    if not data:
        return None
    exp = data.get("exp")
    if exp:
        try:
            if datetime.utcnow() > datetime.fromisoformat(exp):
                return None
        except Exception:
            return None
    return data.get("user")

