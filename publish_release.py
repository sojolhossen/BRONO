#!/usr/bin/env python3
"""
BRONO Automated Release Publisher
Usage:
    python publish_release.py 1.0.1 "Bug fixes & new features"
"""
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

def main():
    if len(sys.argv) < 2:
        print("Usage: python publish_release.py <version> [changelog]")
        print("Example: python publish_release.py 1.0.1 'Added voice customization & speed improvements'")
        sys.exit(1)

    new_version = sys.argv[1].strip().lstrip("v")
    changelog = sys.argv[2].strip() if len(sys.argv) > 2 else f"BRONO Enterprise v{new_version} update."

    print("=" * 65)
    print(f"  🚀 PREPARING BRONO ENTERPRISE RELEASE v{new_version}")
    print("=" * 65)

    # 1. Update version.json
    v_file = BASE_DIR / "version.json"
    v_data = {
        "app_name": "BRONO",
        "version": new_version,
        "release_date": datetime.now().strftime("%Y-%m-%d"),
        "download_url": f"https://github.com/sojolhossen/BRONO-Releases/releases/tag/v{new_version}",
        "release_notes": changelog,
        "mandatory": False
    }
    v_file.write_text(json.dumps(v_data, indent=2), encoding="utf-8")
    print(f"✅ Updated version.json -> v{new_version}")

    # 2. Update core/licensing.py CURRENT_APP_VERSION
    lic_file = BASE_DIR / "core" / "licensing.py"
    if lic_file.exists():
        txt = lic_file.read_text(encoding="utf-8")
        txt = re.sub(r'CURRENT_APP_VERSION\s*=\s*"[^"]+"', f'CURRENT_APP_VERSION = "{new_version}"', txt)
        lic_file.write_text(txt, encoding="utf-8")
        print(f"✅ Updated core/licensing.py -> CURRENT_APP_VERSION = '{new_version}'")

    # 3. Build executable
    print("\n🔨 Building standalone BRONO.exe via build_exe.py...")
    ret = subprocess.run([sys.executable, "build_exe.py"], cwd=BASE_DIR)
    if ret.returncode != 0:
        print("❌ Build failed! Aborting release.")
        sys.exit(ret.returncode)

    # 4. Create ZIP package & Setup Installer for distribution
    dist_folder = BASE_DIR / "dist" / "BRONO"
    zip_output = BASE_DIR / "dist" / f"BRONO-v{new_version}"
    print(f"\n📦 Creating distribution zip: {zip_output}.zip ...")
    shutil.make_archive(str(zip_output), "zip", root_dir=dist_folder)
    print(f"✅ Portable Package ready: {zip_output}.zip")

    print("\n🔨 Building standalone BRONO_Setup.exe installer...")
    ret_inst = subprocess.run([sys.executable, "build_installer.py"], cwd=BASE_DIR)
    if ret_inst.returncode == 0:
        setup_file = BASE_DIR / "dist" / "BRONO_Setup.exe"
        versioned_setup = BASE_DIR / "dist" / f"BRONO_Setup_v{new_version}.exe"
        if setup_file.exists():
            shutil.copy2(setup_file, versioned_setup)
            print(f"✅ Windows Setup Installer ready: {versioned_setup}")

    # 5. Push version.json to BRONO-Releases GitHub repo
    print("\n🌐 Publishing version metadata to GitHub (sojolhossen/BRONO-Releases)...")
    try:
        temp_dir = BASE_DIR / "temp_releases_sync"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(v_file, temp_dir / "version.json")
        readme = f"""# 🚀 BRONO Enterprise - Official Releases

Official distribution repository for **BRONO Enterprise AI Assistant**.

## 📥 Latest Download
Download the latest pre-built standalone executable package from [Releases](https://github.com/sojolhossen/BRONO-Releases/releases/latest).

- **Current Version:** v{new_version}
- **Release Date:** {datetime.now().strftime("%Y-%m-%d")}
- **Notes:** {changelog}

### How to Install / Update
1. Download `BRONO-v{new_version}.zip` (or `BRONO.zip`)
2. Extract to any folder
3. Run `START_BRONO.bat` or `BRONO.exe`
*All conversation memory, settings, and license will automatically stay intact!*
"""
        (temp_dir / "README.md").write_text(readme, encoding="utf-8")

        subprocess.run(["git", "init"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "sojolhossen"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "sojoldev30@gmail.com"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "add", "."], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"release: v{new_version} metadata and changelog"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "branch", "-M", "main"], cwd=temp_dir, check=True, capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", "https://github.com/sojolhossen/BRONO-Releases.git"], cwd=temp_dir, check=True, capture_output=True)
        push_res = subprocess.run(["git", "push", "-f", "origin", "main"], cwd=temp_dir)
        if push_res.returncode == 0:
            print("✅ Successfully published metadata to sojolhossen/BRONO-Releases!")
        else:
            print("⚠️ Git push failed, please check your network connection.")
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as e:
        print(f"⚠️ Metadata push skipped: {e}")

    print("\n" + "=" * 65)
    print("  🎉 RELEASE v" + new_version + " READY TO SHIP!")
    print("=" * 65)
    print(f"  📁 Upload File: {zip_output}.zip")
    print(f"  🔗 GitHub Release URL: https://github.com/sojolhossen/BRONO-Releases/releases/new?tag=v{new_version}")
    print("=" * 65)
    print("Simply upload the ZIP file to the GitHub Release page above.")
    print("Existing users will immediately get the automatic update banner!\n")

if __name__ == "__main__":
    main()
