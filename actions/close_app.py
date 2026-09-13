import time
import subprocess
import platform
import os
import sys
from pathlib import Path

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    import pyautogui
    _PYAUTOGUI = True
except ImportError:
    _PYAUTOGUI = False

_SYSTEM = platform.system()

# Process names map for common apps across OS
_PROCESS_MAP: dict[str, dict[str, list[str]]] = {
    "chrome":             {"Windows": ["chrome.exe"],                      "Darwin": ["Google Chrome"],       "Linux": ["chrome", "google-chrome"]},
    "google chrome":      {"Windows": ["chrome.exe"],                      "Darwin": ["Google Chrome"],       "Linux": ["chrome", "google-chrome"]},
    "firefox":            {"Windows": ["firefox.exe"],                     "Darwin": ["firefox"],             "Linux": ["firefox"]},
    "edge":               {"Windows": ["msedge.exe"],                      "Darwin": ["Microsoft Edge"],      "Linux": ["msedge"]},
    "microsoft edge":     {"Windows": ["msedge.exe"],                      "Darwin": ["Microsoft Edge"],      "Linux": ["msedge"]},
    "brave":              {"Windows": ["brave.exe"],                       "Darwin": ["Brave Browser"],       "Linux": ["brave"]},
    "brave browser":      {"Windows": ["brave.exe"],                       "Darwin": ["Brave Browser"],       "Linux": ["brave"]},
    "opera":              {"Windows": ["opera.exe"],                       "Darwin": ["Opera"],               "Linux": ["opera"]},
    "whatsapp":           {"Windows": ["WhatsApp.exe", "WhatsApp.Root.exe"],"Darwin": ["WhatsApp"],          "Linux": ["whatsapp"]},
    "telegram":           {"Windows": ["Telegram.exe"],                    "Darwin": ["Telegram"],            "Linux": ["telegram"]},
    "discord":            {"Windows": ["Discord.exe"],                     "Darwin": ["Discord"],             "Linux": ["discord"]},
    "slack":              {"Windows": ["slack.exe"],                       "Darwin": ["Slack"],               "Linux": ["slack"]},
    "zoom":               {"Windows": ["Zoom.exe"],                        "Darwin": ["zoom.us"],             "Linux": ["zoom"]},
    "teams":              {"Windows": ["ms-teams.exe", "Teams.exe"],       "Darwin": ["Microsoft Teams"],     "Linux": ["teams"]},
    "skype":              {"Windows": ["Skype.exe"],                       "Darwin": ["Skype"],               "Linux": ["skype"]},
    "signal":             {"Windows": ["Signal.exe"],                      "Darwin": ["Signal"],              "Linux": ["signal"]},
    "spotify":            {"Windows": ["Spotify.exe"],                     "Darwin": ["Spotify"],             "Linux": ["spotify"]},
    "vlc":                {"Windows": ["vlc.exe"],                         "Darwin": ["VLC"],                 "Linux": ["vlc"]},
    "vscode":             {"Windows": ["Code.exe"],                        "Darwin": ["Code"],                "Linux": ["code"]},
    "vs code":            {"Windows": ["Code.exe"],                        "Darwin": ["Code"],                "Linux": ["code"]},
    "visual studio code": {"Windows": ["Code.exe"],                        "Darwin": ["Code"],                "Linux": ["code"]},
    "code":               {"Windows": ["Code.exe"],                        "Darwin": ["Code"],                "Linux": ["code"]},
    "android studio":     {"Windows": ["studio64.exe", "studio.exe"],      "Darwin": ["Android Studio"],      "Linux": ["studio64.sh", "studio.sh"]},
    "androidstudio":      {"Windows": ["studio64.exe", "studio.exe"],      "Darwin": ["Android Studio"],      "Linux": ["studio64.sh", "studio.sh"]},
    "studio":             {"Windows": ["studio64.exe", "studio.exe"],      "Darwin": ["Android Studio"],      "Linux": ["studio64.sh", "studio.sh"]},
    "canva":              {"Windows": ["Canva.exe"],                       "Darwin": ["Canva"],               "Linux": ["canva"]},
    "notepad":            {"Windows": ["Notepad.exe", "notepad.exe"],      "Darwin": ["TextEdit"],            "Linux": ["gedit"]},
    "note pad":           {"Windows": ["Notepad.exe", "notepad.exe"],      "Darwin": ["TextEdit"],            "Linux": ["gedit"]},
    "textedit":           {"Windows": ["notepad.exe"],                     "Darwin": ["TextEdit"],            "Linux": ["gedit"]},
    "calculator":         {"Windows": ["CalculatorApp.exe", "calc.exe"],   "Darwin": ["Calculator"],          "Linux": ["gnome-calculator"]},
    "calc":               {"Windows": ["CalculatorApp.exe", "calc.exe"],   "Darwin": ["Calculator"],          "Linux": ["gnome-calculator"]},
    "paint":              {"Windows": ["mspaint.exe"],                     "Darwin": ["Preview"],             "Linux": ["gimp"]},
    "word":               {"Windows": ["WINWORD.EXE"],                     "Darwin": ["Microsoft Word"],      "Linux": ["soffice.bin"]},
    "ms word":            {"Windows": ["WINWORD.EXE"],                     "Darwin": ["Microsoft Word"],      "Linux": ["soffice.bin"]},
    "excel":              {"Windows": ["EXCEL.EXE"],                       "Darwin": ["Microsoft Excel"],     "Linux": ["soffice.bin"]},
    "ms excel":           {"Windows": ["EXCEL.EXE"],                       "Darwin": ["Microsoft Excel"],     "Linux": ["soffice.bin"]},
    "powerpoint":         {"Windows": ["POWERPNT.EXE"],                    "Darwin": ["Microsoft PowerPoint"],"Linux": ["soffice.bin"]},
    "obs":                {"Windows": ["obs64.exe", "obs32.exe"],          "Darwin": ["OBS"],                 "Linux": ["obs"]},
    "obs studio":         {"Windows": ["obs64.exe", "obs32.exe"],          "Darwin": ["OBS"],                 "Linux": ["obs"]},
    "postman":            {"Windows": ["Postman.exe"],                     "Darwin": ["Postman"],             "Linux": ["postman"]},
    "figma":              {"Windows": ["Figma.exe"],                       "Darwin": ["Figma"],               "Linux": ["figma"]},
    "blender":            {"Windows": ["blender.exe"],                     "Darwin": ["Blender"],             "Linux": ["blender"]},
    "capcut":             {"Windows": ["CapCut.exe"],                      "Darwin": ["CapCut"],              "Linux": ["capcut"]},
    "steam":              {"Windows": ["steam.exe"],                       "Darwin": ["Steam"],               "Linux": ["steam"]},
}

# Protected system/assistant processes that should NEVER be killed
_PROTECTED_PROCESSES = {
    "brono.exe", "brono_setup.exe", "python.exe", "pythonw.exe",
    "explorer.exe", "system", "idle", "registry", "smss.exe", "csrss.exe",
    "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "fontdrvhost.exe",
    "winlogon.exe", "dwm.exe", "spoolsv.exe"
}


def _close_active_window() -> bool:
    """Close whatever window currently has focus."""
    if _SYSTEM == "Darwin":
        if _PYAUTOGUI:
            pyautogui.hotkey("command", "w")
            return True
    else:
        if _PYAUTOGUI:
            pyautogui.hotkey("alt", "f4")
            return True
    return False


def _get_target_process_names(app_name: str) -> list[str]:
    """Get list of process name candidates for a given app name."""
    clean = app_name.lower().strip()
    if clean in _PROCESS_MAP:
        return _PROCESS_MAP[clean].get(_SYSTEM, [clean])
    
    for alias_key, os_map in _PROCESS_MAP.items():
        if alias_key == clean or alias_key in clean or clean in alias_key:
            return os_map.get(_SYSTEM, [clean])
            
    # Default candidate
    if _SYSTEM == "Windows":
        return [clean if clean.endswith(".exe") else f"{clean}.exe", clean]
    return [clean]


def close_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()

    if player:
        player.write_log(f"[close_app] {app_name or 'active window'}")

    clean = app_name.lower().strip()

    # If asking to close current / active window
    if not clean or clean in ("current", "active", "this", "this window", "this app", "current window"):
        _close_active_window()
        return "Closed the current active window."

    # If user asks to minimize
    if "minimize" in clean:
        if player and hasattr(player, "ui") and hasattr(player.ui, "minimize_window"):
            player.ui.minimize_window()
            return "BRONO window minimized."
        _close_active_window()
        return "Window minimized."

    candidates = [c.lower() for c in _get_target_process_names(app_name)]
    print(f"[close_app] Attempting to close '{app_name}' (candidates: {candidates})")

    killed_count = 0

    # 1. Use psutil for precise termination
    if _PSUTIL:
        for p in psutil.process_iter(["pid", "name", "exe"]):
            try:
                pname = (p.info.get("name") or "").lower()
                if pname in _PROTECTED_PROCESSES:
                    continue

                matched = False
                for cand in candidates:
                    if pname == cand or cand in pname or pname.startswith(cand.replace(".exe", "")):
                        matched = True
                        break

                if matched:
                    try:
                        p.terminate()
                        killed_count += 1
                    except Exception:
                        try:
                            p.kill()
                            killed_count += 1
                        except Exception:
                            pass
            except Exception:
                pass

    # 2. Windows taskkill fallback
    if killed_count == 0 and _SYSTEM == "Windows":
        for cand in candidates:
            proc_file = cand if cand.endswith(".exe") else f"{cand}.exe"
            if proc_file.lower() in _PROTECTED_PROCESSES:
                continue
            try:
                ret = subprocess.run(
                    ["taskkill", "/IM", proc_file, "/F"],
                    capture_output=True,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                if ret.returncode == 0:
                    killed_count += 1
            except Exception:
                pass

    # 3. Unix killall / pkill fallback
    if killed_count == 0 and _SYSTEM != "Windows":
        for cand in candidates:
            try:
                ret = subprocess.run(["pkill", "-f", cand], capture_output=True)
                if ret.returncode == 0:
                    killed_count += 1
            except Exception:
                pass

    if killed_count > 0:
        return f"Successfully closed {app_name}."
    else:
        # Fallback to Alt+F4 active window if process name not found
        _close_active_window()
        return f"Attempted to close {app_name}."


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "close_app",
    "description": "Closes, terminates, or exits any application, program, or window (e.g. Chrome, Android Studio, Canva, Notepad, WhatsApp, VS Code, or 'current' active window). Always use this tool when the user asks to close, exit, or shut an app.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {
                "type": "STRING",
                "description": "Name of the application to close (e.g. 'Chrome', 'Android Studio', 'Notepad', 'Canva', or 'current' for active window)"
            }
        },
        "required": [
            "app_name"
        ]
    },
    "handler": close_app,
}
