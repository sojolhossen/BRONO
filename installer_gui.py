#!/usr/bin/env python3
"""
BRONO Enterprise - Official Windows Setup Installer
Installs BRONO to %LOCALAPPDATA%/Programs/BRONO, registers Start Menu & Desktop shortcuts,
and adds Windows Add/Remove Programs registry entries.
"""
import os
import sys
import time
import zipfile
import shutil
import subprocess
import winreg
from pathlib import Path
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont, QPixmap, QColor, QPainter, QPainterPath
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QFrame
)

APP_NAME = "BRONO Enterprise"
EXE_NAME = "BRONO.exe"
APP_VERSION = "1.0.0"

def get_install_target_dir() -> Path:
    local_app_data = os.getenv("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "Programs" / "BRONO"
    return Path.home() / "AppData" / "Local" / "Programs" / "BRONO"

def get_start_menu_lnk() -> Path:
    app_data = os.getenv("APPDATA")
    if app_data:
        return Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "BRONO.lnk"
    return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "BRONO.lnk"

def get_desktop_lnk() -> Path:
    user_prof = os.getenv("USERPROFILE")
    if user_prof:
        return Path(user_prof) / "Desktop" / "BRONO.lnk"
    return Path.home() / "Desktop" / "BRONO.lnk"

def create_windows_shortcut(lnk_path: Path, target_exe: Path, work_dir: Path, icon_path: str):
    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    vbs_content = f"""
Set ws = CreateObject("WScript.Shell")
Set sc = ws.CreateShortcut("{lnk_path}")
sc.TargetPath = "{target_exe}"
sc.WorkingDirectory = "{work_dir}"
sc.Description = "BRONO Enterprise AI Assistant"
sc.IconLocation = "{icon_path}"
sc.Save
"""
    tmp_vbs = Path(os.getenv("TEMP", ".")) / f"shortcut_{int(time.time()*1000)}.vbs"
    try:
        tmp_vbs.write_text(vbs_content, encoding="utf-8")
        subprocess.run(["wscript.exe", "/nologo", str(tmp_vbs)], check=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "Windows" else 0)
    finally:
        tmp_vbs.unlink(missing_ok=True)

def register_uninstall_entry(install_dir: Path, exe_path: Path):
    try:
        reg_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\BRONO"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "BRONO Enterprise")
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, "BRONO AI")
            winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, f"{exe_path},0")
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{install_dir / "uninstall.bat"}"')
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except Exception as e:
        print(f"[Setup] Registry write skipped: {e}")

def create_uninstaller(install_dir: Path):
    uninst_bat = install_dir / "uninstall.bat"
    start_menu = get_start_menu_lnk()
    desktop = get_desktop_lnk()
    bat_content = f"""@echo off
echo Uninstalling BRONO Enterprise...
taskkill /F /IM BRONO.exe >nul 2>&1
timeout /t 1 /nobreak >nul
del /f /q "{start_menu}" >nul 2>&1
del /f /q "{desktop}" >nul 2>&1
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\BRONO" /f >nul 2>&1
echo Cleaning files...
start /b "" cmd /c "timeout /t 2 /nobreak >nul & rd /s /q \\"{install_dir}\\""
echo BRONO has been successfully uninstalled.
pause
"""
    try:
        uninst_bat.write_text(bat_content, encoding="utf-8")
    except Exception:
        pass


class InstallWorker(QThread):
    progress = pyqtSignal(int, str)
    finished = pyqtSignal(bool, str)

    def run(self):
        try:
            self.progress.emit(10, "Preparing installation environment...")
            time.sleep(0.3)

            # Terminate running BRONO if any
            try:
                subprocess.run(["taskkill", "/F", "/IM", "BRONO.exe"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "Windows" else 0)
            except Exception:
                pass

            target_dir = get_install_target_dir()
            target_dir.mkdir(parents=True, exist_ok=True)

            self.progress.emit(25, "Extracting application packages...")
            
            # Find payload zip
            payload_zip = None
            if getattr(sys, "frozen", False):
                base = Path(sys._MEIPASS)
                if (base / "payload.zip").exists():
                    payload_zip = base / "payload.zip"
            else:
                base = Path(__file__).resolve().parent
                if (base / "payload.zip").exists():
                    payload_zip = base / "payload.zip"
                elif (base / "dist" / "BRONO").exists():
                    # Fallback: direct copy if running unpacked
                    self.progress.emit(40, "Copying application binaries...")
                    shutil.copytree(base / "dist" / "BRONO", target_dir, dirs_exist_ok=True)

            if payload_zip and payload_zip.exists():
                with zipfile.ZipFile(payload_zip, "r") as zf:
                    total_files = len(zf.namelist())
                    for idx, item in enumerate(zf.namelist(), 1):
                        zf.extract(item, target_dir)
                        if idx % 10 == 0:
                            pct = 25 + int((idx / total_files) * 50)
                            self.progress.emit(pct, f"Installing {Path(item).name}...")

            self.progress.emit(80, "Creating Windows Start Menu & Desktop shortcuts...")
            exe_path = target_dir / EXE_NAME
            create_windows_shortcut(get_start_menu_lnk(), exe_path, target_dir, f"{exe_path},0")
            create_windows_shortcut(get_desktop_lnk(), exe_path, target_dir, f"{exe_path},0")

            self.progress.emit(90, "Registering in Windows Application Index...")
            register_uninstall_entry(target_dir, exe_path)
            create_uninstaller(target_dir)

            self.progress.emit(100, "Installation complete!")
            time.sleep(0.5)
            self.finished.emit(True, str(exe_path))

        except Exception as e:
            self.finished.emit(False, str(e))


class InstallerWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BRONO Enterprise — Setup Installer")
        self.setFixedSize(540, 360)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowCloseButtonHint)
        self.setStyleSheet("""
            QWidget {
                background-color: #0b0f19;
                color: #e2e8f0;
                font-family: 'Segoe UI', sans-serif;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # Header with branding
        header = QHBoxLayout()
        logo_lbl = QLabel()
        logo_path = Path(__file__).resolve().parent / "face.png"
        if getattr(sys, "frozen", False):
            logo_path = Path(sys._MEIPASS) / "face.png"
        if logo_path.exists():
            pix = QPixmap(str(logo_path)).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            logo_lbl.setPixmap(pix)
        header.addWidget(logo_lbl)
        header.addSpacing(15)

        title_box = QVBoxLayout()
        title = QLabel("BRONO ENTERPRISE")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet("color: #00e5ff; letter-spacing: 1px;")
        subtitle = QLabel("Personal AI Operating Assistant • Setup Wizard")
        subtitle.setFont(QFont("Segoe UI", 9))
        subtitle.setStyleSheet("color: #94a3b8;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        header.addLayout(title_box)
        header.addStretch()
        layout.addLayout(header)

        # Divider
        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        div.setStyleSheet("color: #1e293b;")
        layout.addWidget(div)
        layout.addSpacing(10)

        # Status text
        self.status_lbl = QLabel("Ready to install BRONO Enterprise to your system...")
        self.status_lbl.setFont(QFont("Segoe UI", 10))
        self.status_lbl.setStyleSheet("color: #cbd5e1;")
        layout.addWidget(self.status_lbl)

        # Progress bar
        self.pbar = QProgressBar()
        self.pbar.setFixedHeight(12)
        self.pbar.setTextVisible(False)
        self.pbar.setStyleSheet("""
            QProgressBar {
                background-color: #1e293b;
                border-radius: 6px;
                border: 1px solid #334155;
            }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #00b4d8, stop:1 #00e5ff);
                border-radius: 5px;
            }
        """)
        self.pbar.setValue(0)
        layout.addWidget(self.pbar)

        self.detail_lbl = QLabel("Will register Start Menu search, Desktop shortcut & persistent memory.")
        self.detail_lbl.setFont(QFont("Segoe UI", 8))
        self.detail_lbl.setStyleSheet("color: #64748b;")
        layout.addWidget(self.detail_lbl)

        layout.addStretch()

        # Buttons
        btn_box = QHBoxLayout()
        btn_box.addStretch()
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setFixedSize(90, 34)
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background: #1e293b; color: #94a3b8;
                border: 1px solid #334155; border-radius: 6px; font-weight: bold;
            }
            QPushButton:hover { background: #334155; color: #fff; }
        """)
        self.cancel_btn.clicked.connect(self.close)
        btn_box.addWidget(self.cancel_btn)

        self.install_btn = QPushButton("Install Now")
        self.install_btn.setFixedSize(130, 34)
        self.install_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.install_btn.setStyleSheet("""
            QPushButton {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #0096c7, stop:1 #00b4d8);
                color: #ffffff; border: none; border-radius: 6px; font-weight: bold; font-size: 11pt;
            }
            QPushButton:hover { background: #00e5ff; color: #0b0f19; }
        """)
        self.install_btn.clicked.connect(self.start_install)
        btn_box.addWidget(self.install_btn)
        layout.addLayout(btn_box)

        # Worker thread
        self.worker = InstallWorker()
        self.worker.progress.connect(self.on_progress)
        self.worker.finished.connect(self.on_finished)

    def start_install(self):
        self.install_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.install_btn.setText("Installing...")
        self.worker.start()

    def on_progress(self, val: int, msg: str):
        self.pbar.setValue(val)
        self.status_lbl.setText(msg)

    def on_finished(self, success: bool, result: str):
        if success:
            self.pbar.setValue(100)
            self.status_lbl.setText("🎉 BRONO Enterprise installed successfully!")
            self.status_lbl.setStyleSheet("color: #00ff88; font-weight: bold;")
            self.detail_lbl.setText("Launch BRONO from Desktop or search 'BRONO' in Windows Start Menu!")
            self.install_btn.setText("Launch BRONO")
            self.install_btn.setEnabled(True)
            self.install_btn.clicked.disconnect()
            self.exe_path = result
            self.install_btn.clicked.connect(self.launch_and_exit)
            self.cancel_btn.setText("Close")
            self.cancel_btn.setEnabled(True)
        else:
            self.status_lbl.setText("❌ Installation encountered an error.")
            self.status_lbl.setStyleSheet("color: #ff5c8a; font-weight: bold;")
            self.detail_lbl.setText(result)
            self.cancel_btn.setText("Close")
            self.cancel_btn.setEnabled(True)

    def launch_and_exit(self):
        if hasattr(self, "exe_path") and os.path.exists(self.exe_path):
            subprocess.Popen([self.exe_path], cwd=os.path.dirname(self.exe_path), creationflags=subprocess.DETACHED_PROCESS if sys.platform == "Windows" else 0)
        self.close()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = InstallerWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
