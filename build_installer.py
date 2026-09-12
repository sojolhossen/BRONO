#!/usr/bin/env python3
"""
BRONO Automated Windows Installer (.exe Setup) Builder
Compresses the dist/BRONO build and wraps it into a single-file BRONO_Setup.exe
with Start Menu search indexing, Desktop shortcut, and Windows Registry integration.
"""
import os
import sys
import shutil
import zipfile
import subprocess
from pathlib import Path

# UTF-8 output on Windows
for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist" / "BRONO"
SETUP_OUTPUT = BASE_DIR / "dist"

def main():
    print("=" * 65)
    print("  🚀 BUILDING BRONO WINDOWS SETUP INSTALLER (BRONO_Setup.exe)")
    print("=" * 65)

    if not (DIST_DIR / "BRONO.exe").exists():
        print("📦 BRONO.exe not found in dist/BRONO! Building it first via build_exe.py...")
        ret = subprocess.run([sys.executable, "build_exe.py"], cwd=BASE_DIR)
        if ret.returncode != 0:
            print("❌ build_exe.py failed! Cannot build installer.")
            sys.exit(ret.returncode)

    # 1. Compress dist/BRONO into payload.zip
    payload_zip = BASE_DIR / "payload.zip"
    print("\n📦 Packaging application payload into payload.zip...")
    if payload_zip.exists():
        payload_zip.unlink()

    with zipfile.ZipFile(payload_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for root, dirs, files in os.walk(DIST_DIR):
            for file in files:
                abs_file = Path(root) / file
                rel_path = abs_file.relative_to(DIST_DIR)
                zf.write(abs_file, rel_path)
    print(f"✅ Payload archive created ({payload_zip.stat().st_size / (1024*1024):.1f} MB)")

    # 2. PyInstaller build for installer_gui.py -> BRONO_Setup.exe
    print("\n🔨 Compiling standalone BRONO_Setup.exe...")
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",
        "--name", "BRONO_Setup",
        "--icon", "icon.ico",
        "--add-data", f"payload.zip;.",
        "--add-data", f"face.png;.",
        "--add-data", f"icon.ico;.",
        "installer_gui.py"
    ]
    ret = subprocess.run(cmd, cwd=BASE_DIR)
    if ret.returncode != 0:
        print("❌ Installer build failed!")
        sys.exit(ret.returncode)

    # Clean up temporary payload.zip
    if payload_zip.exists():
        payload_zip.unlink()

    setup_exe = SETUP_OUTPUT / "BRONO_Setup.exe"
    print("\n" + "=" * 65)
    print("  🎉 BRONO WINDOWS INSTALLER BUILD COMPLETE!")
    print("=" * 65)
    print(f"  ▶️  Installer Exe: {setup_exe}")
    print("=" * 65)
    print("When users double-click 'BRONO_Setup.exe':")
    print("  1. It installs BRONO into %LOCALAPPDATA%/Programs/BRONO")
    print("  2. It creates Start Menu shortcut (search 'BRONO' in Windows Start menu!)")
    print("  3. It creates Desktop shortcut")
    print("  4. It preserves all memory, settings, and license permanently!")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
