#!/usr/bin/env python3
"""
BRONO Enterprise Licensing & Fleet Management Server
Run this script to launch the admin portal and licensing verification endpoints.
Default portal: http://localhost:8080
Default admin:  admin / admin123
"""
import sys
import uvicorn

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

def main():
    print("=" * 65)
    print("  🚀 BRONO ENTERPRISE LICENSING & FLEET CONTROL SERVER")
    print("=" * 65)
    print("  🌐 Admin Dashboard:  http://localhost:8080")
    print("  🔑 Default Admin:    admin")
    print("  🔒 Default Password: admin123")
    print("  🛡️  HWID Anti-Piracy & Cryptographic Engine: ACTIVE")
    print("=" * 65)
    print("Starting server on 0.0.0.0:8080 ... Press Ctrl+C to stop.\n")

    uvicorn.run(
        "server.app:app",
        host="0.0.0.0",
        port=8080,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
