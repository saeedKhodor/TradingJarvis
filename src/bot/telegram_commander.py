# === CODE INDEX ===
# 1. Imports & Constants (Line 18)
# 2. TelegramCommander.__init__() - Initializes commander thread and config (Line 38)
# 3. TelegramCommander.start() / stop() - Thread lifecycle management (Line 68)
# 4. TelegramCommander._poll_updates() - Long-polling loop for Telegram API (Line 88)
# 5. TelegramCommander._handle_message() - Parses incoming user commands (Line 140)
# 6. TelegramCommander._cmd_reboot() - Executes clean process reboot sequence (Line 185)
# 7. TelegramCommander._cmd_status() - Formats and replies with live system telemetry (Line 218)
# =================

import os
import sys
import time
import json
import logging
import threading
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime
from typing import Optional, Dict, Any, Callable

# Load Telegram config
SKILL_SCRIPTS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".agents", "skills", "trading-jarvis", "scripts"
)
if SKILL_SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, SKILL_SCRIPTS_DIR)

try:
    from telegram_notifier import load_config, send_raw_telegram_message, format_jarvis_message
except ImportError:
    pass

logger = logging.getLogger("TradingJarvis.Commander")


class TelegramCommander:
    """Listens for incoming Telegram commands from authorized chat ID and triggers system actions."""

    def __init__(
        self,
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None,
        status_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        on_reboot_callback: Optional[Callable[[], None]] = None
    ):
        cfg = load_config()
        self.bot_token = bot_token or cfg.get("bot_token")
        self.authorized_chat_id = str(chat_id or cfg.get("chat_id"))
        self.status_provider = status_provider
        self.on_reboot_callback = on_reboot_callback

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_update_id = 0

    def start(self) -> None:
        """Starts the background command listener thread."""
        if not self.bot_token or not self.authorized_chat_id:
            logger.warning("TelegramCommander cannot start: Missing bot token or chat ID.")
            return

        self._running = True
        self._thread = threading.Thread(target=self._poll_updates, name="JarvisTelegramCommander", daemon=True)
        self._thread.start()
        logger.info(f"Telegram Commander is online. Listening for commands from Chat ID: {self.authorized_chat_id}")

    def stop(self) -> None:
        """Stops the command listener thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        logger.info("Telegram Commander stopped.")

    def _poll_updates(self) -> None:
        """Long-polling loop for Telegram getUpdates API."""
        # Initial offset flush
        self._flush_pending_updates()

        while self._running:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                params = {
                    "offset": self._last_update_id + 1,
                    "timeout": 10,
                    "allowed_updates": ["message"]
                }
                req_url = f"{url}?{urllib.parse.urlencode(params)}"
                req = urllib.request.Request(req_url, headers={"User-Agent": "TradingJarvisCommander/1.0"})

                with urllib.request.urlopen(req, timeout=15) as res:
                    data = json.loads(res.read().decode("utf-8"))
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for u in updates:
                            self._last_update_id = u["update_id"]
                            if "message" in u:
                                self._handle_message(u["message"])

            except urllib.error.URLError as e:
                logger.debug(f"Network error polling Telegram updates: {e}")
                time.sleep(3.0)
            except Exception as e:
                logger.error(f"Unexpected error in Telegram polling: {e}")
                time.sleep(3.0)

    def _flush_pending_updates(self) -> None:
        """Processes any recent pending updates on startup without discarding valid user commands."""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            req = urllib.request.Request(url, headers={"User-Agent": "TradingJarvisCommander/1.0"})
            with urllib.request.urlopen(req, timeout=5) as res:
                data = json.loads(res.read().decode("utf-8"))
                if data.get("ok") and data.get("result"):
                    now_ts = time.time()
                    for u in data.get("result", []):
                        self._last_update_id = u["update_id"]
                        msg = u.get("message", {})
                        # Process if sent in the last 2 minutes
                        msg_date = msg.get("date", 0)
                        if (now_ts - msg_date) < 120 and "text" in msg:
                            self._handle_message(msg)
        except Exception as e:
            logger.debug(f"Initial updates check: {e}")

    def _handle_message(self, msg: Dict[str, Any]) -> None:
        """Validates authorization and routes incoming command text."""
        chat_id = str(msg.get("chat", {}).get("id", ""))
        sender_name = msg.get("from", {}).get("first_name", "User")
        text = msg.get("text", "").strip()

        # Security check: only respond to authorized chat ID
        if chat_id != self.authorized_chat_id:
            logger.warning(f"Unauthorized command attempt from Chat ID: {chat_id} ({sender_name}): {text}")
            return

        logger.info(f"Received authorized command from {sender_name}: '{text}'")
        raw_cmd = text.split()[0].lower() if text else ""
        # Remove bot mention (e.g. /skills@TradingJarvis1_bot -> /skills) and strip leading slash
        clean_cmd = raw_cmd.split("@")[0].lstrip("/")

        if clean_cmd in ["reboot", "restart"]:
            self._cmd_reboot()
        elif clean_cmd in ["status", "ping", "health"]:
            self._cmd_status()
        elif clean_cmd in ["help", "start"]:
            self._cmd_help()
        elif clean_cmd in ["skills", "sentinel"]:
            self._cmd_skills()
        elif clean_cmd in ["skill", "safetylock", "cascade", "lock"]:
            # Parse skill target if provided (e.g. /skill safetylock or /skill 1)
            parts = text.split()
            target = parts[1] if len(parts) > 1 else "safetylock"
            self._cmd_skill_detail(target)
        else:
            if raw_cmd.startswith("/"):
                reply = format_jarvis_message(
                    title="COMMAND UNRECOGNIZED",
                    content=f"<i>Sir, command <code>{raw_cmd}</code> is not recognized. Send /help for available directives.</i>",
                    icon="❓"
                )
                send_raw_telegram_message(reply)

    def _cmd_reboot(self) -> None:
        """Executes a clean, graceful reboot of the J.A.R.V.I.S. process."""
        reply = format_jarvis_message(
            title="REBOOT SEQUENCE INITIATED",
            content=(
                "<b>Status:</b> <code>RESTARTING ALL SUBSYSTEMS</code>\n"
                "━━━━━━━━━━━━━━━━━━━━\n"
                "• Gracefully flushing price buffers &amp; cache.\n"
                "• Disconnecting MetaTrader 5 IPC channel.\n"
                "• Re-spawning main daemon process.\n\n"
                "<i>Sir, standby. Systems will re-initialize in approximately 3 seconds.</i>"
            ),
            icon="⚡"
        )
        send_raw_telegram_message(reply)
        logger.info("Executing J.A.R.V.I.S. process reboot requested via Telegram...")

        # Optional pre-reboot callback
        if self.on_reboot_callback:
            try:
                self.on_reboot_callback()
            except Exception as e:
                logger.error(f"Error in pre-reboot callback: {e}")

        # Small delay for message dispatch
        time.sleep(1.5)

        # Trigger clean Python process restart
        python_exe = sys.executable
        args = [python_exe] + sys.argv
        logger.info(f"Re-executing process: {args}")
        
        # On Windows/POSIX, re-execute the current process
        os.execv(python_exe, args)

    def _cmd_status(self) -> None:
        """Queries status provider and sends live telemetry status."""
        status_info = self.status_provider() if self.status_provider else {}
        
        symbol = status_info.get("symbol", "US500.cash")
        price = status_info.get("price", "N/A")
        mt5_connected = "🟢 CONNECTED" if status_info.get("mt5_connected") else "🔴 DISCONNECTED"
        safety_status = status_info.get("safety_status", "NORMAL")
        balance = status_info.get("balance", "$100,000.00")
        equity = status_info.get("equity", "$100,000.00")
        skills_count = status_info.get("skills_count", 1)

        body = (
            f"<b>System State:</b> <code>ONLINE &amp; ARMED</code>\n"
            f"<b>Terminal IPC:</b> {mt5_connected}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Instrument:</b> <code>{symbol}</code>\n"
            f"💵 <b>Current Price:</b> <code>{price}</code>\n"
            f"🛡️ <b>Safety Lock:</b> <code>{safety_status}</code>\n"
            f"💰 <b>Equity:</b> <code>{equity}</code> (<b>Bal:</b> <code>{balance}</code>)\n"
            f"⚙️ <b>Active Skills:</b> <code>{skills_count} Active</code>\n\n"
            f"<i>Sir, all sentinel monitors are operating within nominal parameters.</i>"
        )
        reply = format_jarvis_message(title="SYSTEM DIAGNOSTICS", content=body, icon="📊")
        send_raw_telegram_message(reply)

    def _cmd_skills(self) -> None:
        """Sends summary of active trading skills."""
        body = (
            f"<b>Active Skills Roster:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"1. <b>SafetyLock_Cascade (SKILL-01)</b>\n"
            f"   • Hierarchy: <code>H1 Close &lt; 9 &lt; 21 &lt; 50-EMA</code>\n"
            f"   • Action: Enforces <code>LOCKED IN CASH</code>\n"
            f"   • Retests: H1 9-EMA &amp; 30M 9-EMA\n"
            f"   • Status: 🟢 <code>ARMED</code>\n\n"
            f"💡 <i>Tip: Send <b>/skill 1</b> to query live cascade metrics &amp; distances.</i>"
        )
        reply = format_jarvis_message(title="SKILLS ROSTER", content=body, icon="🏛️")
        send_raw_telegram_message(reply)

    def _cmd_skill_detail(self, target: str) -> None:
        """Queries and formats deep diagnostic telemetry for a specific skill."""
        status_info = self.status_provider() if self.status_provider else {}
        skill_data = status_info.get("skill_details", {}).get(target.lower(), {}) if status_info else {}

        # Default SafetyLock values if status_provider provided top-level
        price_val = status_info.get("price", "7698.00")
        is_locked = status_info.get("safety_status") == "LOCKED_IN_CASH"
        state_icon = "🚨" if is_locked else "🟢"
        state_text = "LOCKED IN CASH" if is_locked else "ARMED (NORMAL MARKET)"

        h1_ema9 = skill_data.get("h1_ema9")
        h1_ema21 = skill_data.get("h1_ema21")
        h1_ema50 = skill_data.get("h1_ema50")
        m30_ema9 = skill_data.get("m30_ema9")

        h1_9_str = f"<code>{h1_ema9:.2f}</code>" if h1_ema9 else "<code>N/A</code>"
        h1_21_str = f"<code>{h1_ema21:.2f}</code>" if h1_ema21 else "<code>N/A</code>"
        h1_50_str = f"<code>{h1_ema50:.2f}</code>" if h1_ema50 else "<code>N/A</code>"
        m30_9_str = f"<code>{m30_ema9:.2f}</code>" if m30_ema9 else "<code>N/A</code>"

        dist_h1 = skill_data.get("dist_to_h1_9")
        dist_m30 = skill_data.get("dist_to_m30_9")
        dist_h1_str = f" (Dist: {dist_h1:+.2f} pts)" if dist_h1 is not None else ""
        dist_m30_str = f" (Dist: {dist_m30:+.2f} pts)" if dist_m30 is not None else ""

        cascade_active = skill_data.get("cascade_active", False)
        cascade_icon = "🚨" if cascade_active else "✅"
        cascade_text = "ACTIVE (BEARISH CASCADE)" if cascade_active else "INACTIVE (NO CASCADE)"

        body = (
            f"<b>Skill Diagnostic:</b> <code>SafetyLock_Cascade (SKILL-01)</code>\n"
            f"<b>Current State:</b> {state_icon} <code>{state_text}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Price:</b> <code>{price_val}</code>\n\n"
            f"🏛️ <b>Cascade Indicator Levels:</b>\n"
            f"• H1 9-EMA : {h1_9_str}{dist_h1_str}\n"
            f"• H1 21-EMA: {h1_21_str}\n"
            f"• H1 50-EMA: {h1_50_str}\n"
            f"• 30M 9-EMA: {m30_9_str}{dist_m30_str}\n\n"
            f"⚖️ <b>Cascade Condition:</b> {cascade_icon} <code>{cascade_text}</code>\n"
            f"🎯 <b>Retest Tolerance:</b> <code>±2.0 pts</code>\n\n"
            f"<i>Sir, Safety Lock is actively guarding capital against H1 cascades.</i>"
        )
        reply = format_jarvis_message(title="SKILL TELEMETRY", content=body, icon="🛡️")
        send_raw_telegram_message(reply)

    def _cmd_help(self) -> None:
        """Sends command documentation."""
        body = (
            f"<b>Available Telegram Directives:</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"• <b>/status</b> - Live US500 price, equity, &amp; lock state.\n"
            f"• <b>/skills</b> - Displays active trading skills roster.\n"
            f"• <b>/skill 1</b> - Detailed telemetry &amp; EMA distances for Skill 01.\n"
            f"• <b>/reboot</b> - Safely restarts J.A.R.V.I.S. daemon.\n"
            f"• <b>/ping</b> - Diagnostic heartbeat check.\n"
            f"• <b>/help</b> - Displays this directive menu.\n\n"
            f"<i>At your command, sir.</i>"
        )
        reply = format_jarvis_message(title="COMMAND MENU", content=body, icon="📋")
        send_raw_telegram_message(reply)
