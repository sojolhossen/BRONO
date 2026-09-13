#!/usr/bin/env python3
"""
BRONO Automated Windows Executable Builder (.exe)
Uses PyInstaller to create a standalone, distribution-ready release.
"""
import os
import sys
import shutil
import subprocess
from pathlib import Path

# UTF-8 output on Windows
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist" / "BRONO"

def main():
    print("=" * 65)
    print("  🚀 BUILDING BRONO STANDALONE WINDOWS EXECUTABLE (.EXE)")
    print("=" * 65)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        "--name", "BRONO",
        "--icon", "icon.ico",
        "--add-data", "face.png;.",
        "--add-data", "icon.ico;.",
        "--add-data", "core/prompt.txt;core",
        "--hidden-import", "fastapi",
        "--hidden-import", "uvicorn",
        "--hidden-import", "cryptography",
        "--hidden-import", "duckduckgo_search",
        "--hidden-import", "config",
        "--hidden-import", "psutil",
        "--add-data", "config.py;.",
        "main.py"
    ]

    print("Running PyInstaller...")
    ret = subprocess.run(cmd, cwd=BASE_DIR)
    if ret.returncode != 0:
        print("\n❌ Build failed! Check PyInstaller output above.")
        sys.exit(ret.returncode)

    print("\n📦 Finalizing distribution package...")
    # Ensure face.png, icon.ico and version.json are at root of dist/BRONO as well
    if (BASE_DIR / "face.png").exists():
        shutil.copy2(BASE_DIR / "face.png", DIST_DIR / "face.png")
    if (BASE_DIR / "icon.ico").exists():
        shutil.copy2(BASE_DIR / "icon.ico", DIST_DIR / "icon.ico")
    if (BASE_DIR / "version.json").exists():
        shutil.copy2(BASE_DIR / "version.json", DIST_DIR / "version.json")

    # Copy config.py to dist root and _internal (needed by game_updater, youtube_video etc.)
    for cfg_dst in [DIST_DIR / "config.py", DIST_DIR / "_internal" / "config.py"]:
        shutil.copy2(BASE_DIR / "config.py", cfg_dst)

    # Copy dynamic actions, plugins, and core folders into dist package
    for folder in ["actions", "plugins", "core"]:
        src = BASE_DIR / folder
        if src.exists():
            for target_dir in [DIST_DIR / folder, DIST_DIR / "_internal" / folder]:
                if target_dir.exists():
                    shutil.rmtree(target_dir)
                shutil.copytree(src, target_dir, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    # Ensure config directory exists in dist
    dist_config = DIST_DIR / "config"
    dist_config.mkdir(parents=True, exist_ok=True)
    
    # Preserve license token if activated on this machine
    src_license = BASE_DIR / "config" / "license.dat"
    if src_license.exists():
        shutil.copy2(src_license, dist_config / "license.dat")

    import json
    dist_api_file = dist_config / "api_keys.json"
    clean_config = {
        "license_server_url": "https://brono.onrender.com",
        "assistant_name": "BRONO",
        "os_system": "windows"
    }
    src_api = BASE_DIR / "config" / "api_keys.json"
    if src_api.exists():
        try:
            cur = json.loads(src_api.read_text(encoding="utf-8"))
            if cur.get("gemini_api_key"):
                clean_config["gemini_api_key"] = cur["gemini_api_key"]
        except Exception:
            pass
    dist_api_file.write_text(json.dumps(clean_config, indent=4), encoding="utf-8")

    print("\n" + "=" * 65)
    print("  🎉 BRONO BUILD COMPLETE!")
    print("=" * 65)
    print(f"  📁 Output Directory: {DIST_DIR}")
    print(f"  ▶️  Executable:      {DIST_DIR / 'BRONO.exe'}")
    print("=" * 65)
    print("You can now ZIP the 'dist/BRONO' folder and sell/distribute it to customers!\n")

if __name__ == "__main__":
    main()
