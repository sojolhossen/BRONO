import sys
import os
import json
from pathlib import Path

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Setup paths
sys.path.insert(0, str(Path(__file__).resolve().parent))

from server.models import init_db, get_db
from server.crypto import generate_license_key, hash_password, verify_password
from fastapi.testclient import TestClient
from server.app import app
import core.licensing as licensing

def run_tests():
    print("==================================================================")
    print("  🚀 BRONO ENTERPRISE LICENSING & HWID VERIFICATION SUITE")
    print("==================================================================")

    init_db()
    client = TestClient(app)

    # 1. Test Admin Login
    print("\n[1] Testing Admin Authentication...")
    login_resp = client.post("/api/admin/login", json={"username": "admin", "password": "admin123"})
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    print("   ✓ Admin login successful with session cookie.")

    # 2. Test License Generation
    print("\n[2] Testing License Generation (Single & Bulk)...")
    gen_resp = client.post(
        "/api/admin/licenses/create",
        json={
            "count": 2,
            "plan": "lifetime",
            "max_devices": 1,
            "customer_name": "Rahim Chowdhury",
            "customer_email": "rahim@example.com",
            "notes": "Order #BRONO-101"
        }
    )
    assert gen_resp.status_code == 200, f"License creation failed: {gen_resp.text}"
    data = gen_resp.json()
    keys = data["created_keys"]
    print(f"   ✓ Generated {len(keys)} keys: {keys}")
    test_key = keys[0]

    # 3. Test Client Activation
    print("\n[3] Testing Client Activation & HWID Lock...")
    hwid_1 = "HWID-TEST-AAAA-1111-9999"
    act_resp = client.post(
        "/api/v1/activate",
        json={
            "license_key": test_key,
            "hwid": hwid_1,
            "pc_name": "DESKTOP-RAHIM-PC",
            "os_info": "Windows 11 Pro",
            "customer_name": "Rahim Chowdhury",
            "app_version": "1.0.0"
        }
    )
    assert act_resp.status_code == 200, f"Activation failed: {act_resp.text}"
    act_data = act_resp.json()
    token = act_data["token"]
    assert token, "Token missing from activation response"
    print(f"   ✓ Machine 1 activated & received HMAC token: {token[:25]}...")

    # 4. Anti-Piracy Test: Machine 2 attempts to use same single-PC key
    print("\n[4] Testing Anti-Piracy Multi-Device Prevention (Device Limit = 1)...")
    hwid_2 = "HWID-PIRATE-BBBB-2222-8888"
    pirate_resp = client.post(
        "/api/v1/activate",
        json={
            "license_key": test_key,
            "hwid": hwid_2,
            "pc_name": "UNAUTHORIZED-PC",
            "os_info": "Windows 10",
            "customer_name": "Stranger",
            "app_version": "1.0.0"
        }
    )
    assert pirate_resp.status_code == 403, f"Expected 403 Forbidden, got {pirate_resp.status_code}"
    print(f"   ✓ Anti-Piracy Blocked 2nd PC: {pirate_resp.json()['detail']}")

    # 5. Test Token Cryptographic Verification
    print("\n[5] Testing Offline Token Cryptographic Integrity...")
    verified_data = licensing.verify_token(token)
    assert verified_data is not None, "Cryptographic token verification failed"
    assert verified_data["license_key"] == test_key
    assert hwid_1 in verified_data["hwids"]
    print(f"   ✓ Offline Token cryptographically verified with HWID: {hwid_1}")

    # Tamper test
    tampered_token = token[:-5] + "XXXXX"
    assert licensing.verify_token(tampered_token) is None, "Tampered token was not rejected!"
    print("   ✓ Anti-Tamper: Modified token rejected immediately.")

    # 6. Test Heartbeat & Fleet Remote Broadcast
    print("\n[6] Testing Remote Fleet Control & Broadcast...")
    # Admin updates broadcast
    cfg_resp = client.post(
        "/api/admin/config",
        json={
            "broadcast_active": True,
            "broadcast_message": "⚡ BRONO update v1.0.1 is live with enhanced Bangladesh news!",
            "broadcast_level": "info",
            "feature_vision": True,
            "system_prompt_override": "REMOTE PROMPT TEST"
        }
    )
    assert cfg_resp.status_code == 200

    # Client sends heartbeat
    hb_resp = client.post(
        "/api/v1/heartbeat",
        json={"license_key": test_key, "hwid": hwid_1, "app_version": "1.0.0"}
    )
    assert hb_resp.status_code == 200
    hb_data = hb_resp.json()
    assert hb_data["revoked"] is False
    assert hb_data["remote_config"]["broadcast_active"] is True
    print(f"   ✓ Heartbeat received remote broadcast: '{hb_data['remote_config']['broadcast_message']}'")

    # 7. Test Remote Kill-Switch (Revocation)
    print("\n[7] Testing Remote Kill-Switch (Revoke License)...")
    # Get license id
    lics = client.get("/api/admin/licenses").json()["licenses"]
    target_lic = next(l for l in lics if l["license_key"] == test_key)
    revoke_resp = client.post(f"/api/admin/licenses/{target_lic['id']}/action?action=revoke")
    assert revoke_resp.status_code == 200

    # Client sends heartbeat after revoke
    hb_revoked = client.post(
        "/api/v1/heartbeat",
        json={"license_key": test_key, "hwid": hwid_1, "app_version": "1.0.0"}
    )
    assert hb_revoked.json()["revoked"] is True, "Heartbeat failed to report revoked status"
    print("   ✓ Kill-switch active: Client was immediately notified of revocation!")

    # 8. Test HWID Reset (allow customer to transfer license to new machine)
    print("\n[8] Testing HWID Reset / Device Transfer...")
    client.post(f"/api/admin/licenses/{target_lic['id']}/action?action=activate")
    reset_resp = client.post(f"/api/admin/licenses/{target_lic['id']}/action?action=reset_hwid")
    assert reset_resp.status_code == 200

    # Machine 2 now activates successfully
    act2_resp = client.post(
        "/api/v1/activate",
        json={
            "license_key": test_key,
            "hwid": hwid_2,
            "pc_name": "NEW-LAPTOP-PC",
            "os_info": "Windows 11",
            "customer_name": "Rahim Chowdhury",
            "app_version": "1.0.0"
        }
    )
    assert act2_resp.status_code == 200, f"Activation on new PC failed: {act2_resp.text}"
    print("   ✓ Machine 2 successfully activated after admin HWID reset!")

    print("\n==================================================================")
    print("  🎉 ALL ENTERPRISE LICENSING & HWID TESTS PASSED 100%!")
    print("==================================================================")

if __name__ == "__main__":
    run_tests()
