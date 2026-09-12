import os
import sys
import subprocess
from pathlib import Path

target_exe = Path(r"d:\xampp\htdocs\Mark\dist\BRONO\BRONO.exe").resolve()
start_menu_lnk = Path(os.getenv("APPDATA")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "BRONO.lnk"
desktop_lnk = Path(os.getenv("USERPROFILE")) / "Desktop" / "BRONO.lnk"

def create_shortcut(lnk_path, target, work_dir, icon_path):
    vbs = f"""
Set ws = CreateObject("WScript.Shell")
Set sc = ws.CreateShortcut("{lnk_path}")
sc.TargetPath = "{target}"
sc.WorkingDirectory = "{work_dir}"
sc.Description = "BRONO Enterprise AI Assistant"
sc.IconLocation = "{icon_path}"
sc.Save
"""
    vbs_file = Path("temp_shortcut.vbs")
    vbs_file.write_text(vbs, encoding="utf-8")
    subprocess.run(["wscript.exe", "/nologo", str(vbs_file)], check=True)
    vbs_file.unlink(missing_ok=True)
    print("Created shortcut at:", lnk_path)

if __name__ == "__main__":
    create_shortcut(start_menu_lnk, target_exe, target_exe.parent, f"{target_exe},0")
    create_shortcut(desktop_lnk, target_exe, target_exe.parent, f"{target_exe},0")
    print("Done!")
