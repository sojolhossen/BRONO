"""
telegram_remote.py — BRONO Telegram Remote Control System

Allows the user to command BRONO remotely via Telegram:
- Send files from PC to Telegram
- Execute BRONO commands remotely
- Get PC status, screenshots, etc.

Setup:
  1. Create a Telegram Bot via @BotFather → get BOT_TOKEN
  2. Send any message to your bot → get your CHAT_ID
  3. Add both to config/api_keys.json:
     "telegram_bot_token": "YOUR_BOT_TOKEN"
     "telegram_chat_id":   "YOUR_CHAT_ID"

Auto-discovery: When BRONO starts, it launches the Telegram listener in background.
User can message the bot: "send me file C:/Users/Admin/Documents/report.pdf"
"""

import json
import os
import sys
import platform
import threading
import time
import logging
from pathlib import Path

_OS = platform.system()

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def _get_config() -> dict:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


def _get_bot_token() -> str:
    return _get_config().get("telegram_bot_token", "").strip()


def _get_chat_id() -> str:
    return str(_get_config().get("telegram_chat_id", "")).strip()


def _is_configured() -> bool:
    return bool(_get_bot_token() and _get_chat_id())


# ── HTTP helpers (uses only stdlib urllib — no requests dependency) ────────────

def _telegram_api(method: str, data: dict = None, files: dict = None, timeout: int = 30):
    """Call the Telegram Bot API. Returns parsed JSON or raises on error."""
    import urllib.request
    import urllib.parse

    token = _get_bot_token()
    url = f"https://api.telegram.org/bot{token}/{method}"

    if files:
        # Multipart form-data for file uploads
        import email.mime.multipart
        import io

        boundary = "BRONOBoundary123456"
        body = b""
        for key, value in (data or {}).items():
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"\r\n\r\n{value}\r\n".encode()
        for key, (filename, file_bytes, mime) in files.items():
            body += (
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"{key}\"; "
                f"filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n"
            ).encode() + file_bytes + b"\r\n"
        body += f"--{boundary}--\r\n".encode()

        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
    else:
        body = json.dumps(data or {}).encode("utf-8")
        req = urllib.request.Request(
            url, data=body,
            headers={"Content-Type": "application/json"},
        )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return {"ok": False, "description": str(e)}


def send_telegram_message(text: str, chat_id: str = "") -> bool:
    """Send a plain text message to the Telegram chat."""
    chat = chat_id or _get_chat_id()
    if not _get_bot_token() or not chat:
        return False
    result = _telegram_api("sendMessage", {"chat_id": chat, "text": text, "parse_mode": "HTML"})
    return result.get("ok", False)


def send_telegram_file(file_path: str, caption: str = "", chat_id: str = "") -> str:
    """Send a file from the PC to Telegram.
    Automatically picks document/photo/audio based on extension.
    Returns a status string."""
    chat = chat_id or _get_chat_id()
    if not _get_bot_token() or not chat:
        return "Telegram not configured. Add telegram_bot_token and telegram_chat_id to config."

    p = Path(file_path)
    if not p.exists():
        # Try common shortcuts
        from actions.file_controller import _resolve_path
        resolved = _resolve_path(file_path)
        if resolved.is_file():
            p = resolved
        else:
            return f"File not found: {file_path}"

    if not p.is_file():
        return f"Not a file: {file_path}"

    file_size = p.stat().st_size
    MAX_SIZE = 50 * 1024 * 1024  # 50 MB Telegram limit
    if file_size > MAX_SIZE:
        return (f"File too large: {file_size / (1024*1024):.1f} MB "
                f"(Telegram max is 50 MB).")

    try:
        file_bytes = p.read_bytes()
    except PermissionError:
        return f"Permission denied reading: {p.name}"
    except Exception as e:
        return f"Could not read file: {e}"

    # Choose send method by extension
    ext = p.suffix.lower()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    audio_exts = {".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"}
    video_exts = {".mp4", ".mov", ".avi", ".mkv", ".webm"}

    if ext in image_exts:
        method = "sendPhoto"
        field  = "photo"
        mime   = f"image/{ext.lstrip('.').replace('jpg', 'jpeg')}"
    elif ext in audio_exts:
        method = "sendAudio"
        field  = "audio"
        mime   = f"audio/{ext.lstrip('.')}"
    elif ext in video_exts:
        method = "sendVideo"
        field  = "video"
        mime   = f"video/{ext.lstrip('.')}"
    else:
        method = "sendDocument"
        field  = "document"
        mime   = "application/octet-stream"

    cap = caption or f"📁 {p.name} ({file_size / 1024:.1f} KB)"
    data = {"chat_id": chat, "caption": cap}
    files = {field: (p.name, file_bytes, mime)}

    result = _telegram_api(method, data=data, files=files, timeout=120)
    if result.get("ok"):
        return f"✅ Sent to Telegram: {p.name}"
    else:
        return f"❌ Telegram error: {result.get('description', 'Unknown error')}"


# ── Remote Command Listener ────────────────────────────────────────────────────

_listener_running = False
_listener_thread: threading.Thread | None = None
_last_update_id = 0
_ui_ref = None  # Set by BRONO main to allow writing to the log


def _parse_remote_command(text: str) -> tuple[str, str]:
    """Parse a user message into (action, argument).
    Returns ("unknown", "") if not recognized."""
    t = text.strip()
    tl = t.lower()

    # File send: "send file X", "send me X", "give me X", "amar X dao"
    for prefix in ("send file ", "send me ", "give me ", "amar ", "পাঠাও ", "দাও ", "send ", "file send "):
        if tl.startswith(prefix):
            arg = t[len(prefix):].strip().strip('"').strip("'")
            return ("send_file", arg)

    # Screenshot
    if any(k in tl for k in ("screenshot", "screen shot", "স্ক্রিনশট", "screen capture")):
        return ("screenshot", "")

    # Status
    if any(k in tl for k in ("status", "stat", "health", "pc status", "কেমন আছ")):
        return ("status", "")

    # List files on desktop
    if any(k in tl for k in ("list files", "desktop files", "list desktop", "ফাইল দেখাও")):
        return ("list_files", "desktop")

    # List downloads
    if any(k in tl for k in ("list downloads", "downloads", "ডাউনলোড")):
        return ("list_files", "downloads")

    # Help
    if any(k in tl for k in ("help", "commands", "সাহায্য", "কি করতে পার")):
        return ("help", "")

    return ("unknown", t)


def _handle_remote_command(action: str, arg: str) -> str:
    """Execute a remote command and return the response text."""
    if action == "send_file":
        return send_telegram_file(arg)

    elif action == "screenshot":
        try:
            import subprocess
            import tempfile
            screenshot_path = Path(tempfile.gettempdir()) / "brono_screenshot.png"
            if _OS == "Windows":
                # Use PowerShell to capture screenshot without any GUI popup
                ps_cmd = (
                    f"Add-Type -AssemblyName System.Windows.Forms; "
                    f"$b=[System.Drawing.Bitmap]::new([System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Width,"
                    f"[System.Windows.Forms.Screen]::PrimaryScreen.Bounds.Height); "
                    f"$g=[System.Drawing.Graphics]::FromImage($b); "
                    f"$g.CopyFromScreen(0,0,0,0,$b.Size); "
                    f"$b.Save('{screenshot_path}'); $g.Dispose(); $b.Dispose()"
                )
                subprocess.run(
                    ["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    capture_output=True,
                    timeout=15
                )
            else:
                subprocess.run(["scrot", str(screenshot_path)], timeout=15)

            if screenshot_path.exists():
                result = send_telegram_file(str(screenshot_path), "🖥️ PC Screenshot from BRONO")
                screenshot_path.unlink(missing_ok=True)
                return result
            return "Could not capture screenshot."
        except Exception as e:
            return f"Screenshot error: {e}"

    elif action == "status":
        try:
            import psutil
            cpu = psutil.cpu_percent(interval=1)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("/")
            uptime_s = time.time() - psutil.boot_time()
            h = int(uptime_s // 3600)
            m = int((uptime_s % 3600) // 60)
            return (
                f"🖥️ <b>BRONO PC Status</b>\n"
                f"━━━━━━━━━━━━━━\n"
                f"🔴 CPU: {cpu:.1f}%\n"
                f"🧠 RAM: {mem.percent:.1f}% ({mem.available // (1024**2)} MB free)\n"
                f"💾 Disk C: {disk.percent:.1f}% used\n"
                f"⏱️ Uptime: {h:02d}h {m:02d}m\n"
                f"✅ BRONO is Online"
            )
        except Exception as e:
            return f"Status error: {e}"

    elif action == "list_files":
        try:
            from actions.file_controller import list_files
            result = list_files(arg or "desktop")
            # Trim for Telegram message limit
            if len(result) > 3800:
                result = result[:3800] + "\n...(truncated)"
            return f"📂 <b>Files in {arg}:</b>\n<pre>{result}</pre>"
        except Exception as e:
            return f"List error: {e}"

    elif action == "help":
        return (
            "🤖 <b>BRONO Remote Commands</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "📁 <b>send file [path]</b> — Send a file to your phone\n"
            "   Example: <code>send file C:/Users/Admin/report.pdf</code>\n"
            "   Shortcut: <code>send me documents/resume.docx</code>\n\n"
            "🖥️ <b>screenshot</b> — Capture & send PC screen\n"
            "📊 <b>status</b> — PC health (CPU/RAM/Disk)\n"
            "📂 <b>list files</b> — Desktop file list\n"
            "📂 <b>list downloads</b> — Downloads folder\n"
            "❓ <b>help</b> — Show this menu\n\n"
            "💡 You can also write in Bengali!"
        )

    else:
        return (
            f"❓ I didn't understand: <b>{arg}</b>\n"
            "Type <b>help</b> to see available commands."
        )


def _poll_loop(ui=None):
    """Long-poll Telegram for new messages and process commands."""
    global _last_update_id, _listener_running

    token = _get_bot_token()
    chat_id = _get_chat_id()

    if not token or not chat_id:
        return

    # Send startup notification
    send_telegram_message(
        "🟢 <b>BRONO is Online</b>\nYour PC assistant is ready. "
        "Type <b>help</b> to see remote commands.",
        chat_id
    )

    while _listener_running:
        try:
            result = _telegram_api("getUpdates", {
                "offset": _last_update_id + 1,
                "timeout": 20,
                "allowed_updates": ["message"],
            }, timeout=30)

            if not result.get("ok"):
                time.sleep(5)
                continue

            updates = result.get("result", [])
            for update in updates:
                _last_update_id = update["update_id"]
                msg = update.get("message", {})
                sender_chat = str(msg.get("chat", {}).get("id", ""))

                # Only process messages from the authorized chat
                if sender_chat != str(chat_id):
                    continue

                text = msg.get("text", "").strip()
                if not text:
                    continue

                if ui:
                    try:
                        ui.write_log(f"[Telegram] Remote: {text[:60]}")
                    except Exception:
                        pass

                action, arg = _parse_remote_command(text)
                response = _handle_remote_command(action, arg)
                send_telegram_message(response, chat_id)

        except Exception as e:
            time.sleep(10)

    # Send offline notification
    send_telegram_message("🔴 <b>BRONO is now Offline</b>", chat_id)


def start_telegram_listener(ui=None):
    """Start the background Telegram polling thread. Called once at BRONO startup."""
    global _listener_running, _listener_thread, _ui_ref

    if _listener_running:
        return "Telegram listener already running."

    if not _is_configured():
        return ("Telegram not configured. Add 'telegram_bot_token' and "
                "'telegram_chat_id' to config/api_keys.json.")

    _ui_ref = ui
    _listener_running = True
    _listener_thread = threading.Thread(
        target=_poll_loop, args=(ui,), daemon=True, name="telegram-remote"
    )
    _listener_thread.start()
    return "✅ Telegram remote listener started."


def stop_telegram_listener():
    """Stop the Telegram polling thread."""
    global _listener_running
    _listener_running = False
    return "Telegram listener stopped."


# ── BRONO Tool Action Wrapper ─────────────────────────────────────────────────

def telegram_remote(parameters: dict = None, response=None, player=None, session_memory=None) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()

    if action == "setup_check":
        if _is_configured():
            return ("✅ Telegram is configured.\n"
                    f"Bot Token: {'*' * 10 + _get_bot_token()[-6:]}\n"
                    f"Chat ID: {_get_chat_id()}\n"
                    "BRONO is listening for your remote commands.")
        else:
            return ("❌ Telegram not configured.\n"
                    "To set up:\n"
                    "1. Message @BotFather on Telegram → /newbot → copy the token\n"
                    "2. Start your bot → send any message\n"
                    "3. Visit https://api.telegram.org/bot<TOKEN>/getUpdates to get your chat_id\n"
                    "4. BRONO will add them to config automatically via the Settings panel.")

    elif action == "save_config":
        token = params.get("bot_token", "").strip()
        chat  = params.get("chat_id", "").strip()
        if not token or not chat:
            return "Please provide both bot_token and chat_id."
        try:
            cfg_path = _base_dir() / "config" / "api_keys.json"
            cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else {}
            cfg["telegram_bot_token"] = token
            cfg["telegram_chat_id"] = chat
            cfg_path.write_text(json.dumps(cfg, indent=4), encoding="utf-8")
            # Restart listener with new creds
            stop_telegram_listener()
            time.sleep(1)
            start_telegram_listener(_ui_ref)
            return "✅ Telegram credentials saved and listener restarted!"
        except Exception as e:
            return f"Could not save config: {e}"

    elif action == "send_file":
        file_path = params.get("path", params.get("file", "")).strip()
        caption   = params.get("caption", "").strip()
        if not file_path:
            return "Please specify a file path."
        return send_telegram_file(file_path, caption)

    elif action == "send_message":
        text = params.get("text", params.get("message", "")).strip()
        if not text:
            return "Please provide message text."
        ok = send_telegram_message(text)
        return "✅ Message sent to Telegram." if ok else "❌ Failed to send message."

    elif action == "screenshot":
        return _handle_remote_command("screenshot", "")

    elif action == "status":
        return _handle_remote_command("status", "")

    elif action == "start_listener":
        return start_telegram_listener(_ui_ref)

    elif action == "stop_listener":
        return stop_telegram_listener()

    else:
        return ("Unknown Telegram action. "
                "Options: setup_check | save_config | send_file | send_message | screenshot | status | start_listener")


# ── Tool declaration (auto-discovered by core/action_loader.py) ───────────────
TOOL = {
    "name": "telegram_remote",
    "description": (
        "Control BRONO remotely via Telegram. "
        "Can send files, screenshots, and messages to the user's Telegram. "
        "Also handles configuration of the Telegram bot."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "setup_check | save_config | send_file | send_message | "
                    "screenshot | status | start_listener | stop_listener"
                ),
            },
            "path": {
                "type": "STRING",
                "description": "Full file path or shortcut (desktop, documents, etc.) to send",
            },
            "caption": {
                "type": "STRING",
                "description": "Optional caption text for the file",
            },
            "text": {
                "type": "STRING",
                "description": "Message text to send",
            },
            "bot_token": {
                "type": "STRING",
                "description": "Telegram Bot Token from @BotFather",
            },
            "chat_id": {
                "type": "STRING",
                "description": "Your Telegram Chat ID",
            },
        },
        "required": ["action"],
    },
    "handler": telegram_remote,
}
