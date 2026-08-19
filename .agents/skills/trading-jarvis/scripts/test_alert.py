# === CODE INDEX ===
# 1. verify_bot_token() - Queries Telegram getMe endpoint to check bot identity (Line 18)
# 2. test_telegram_connection() - Comprehensive connectivity and message test (Line 42)
# 3. main() - Entry point for test script (Line 80)
# =================

import os
import sys
import json
import urllib.request
import urllib.error
from telegram_notifier import load_config, send_raw_telegram_message, format_jarvis_message


def verify_bot_token(token: str) -> dict:
    """Verifies that the bot token is valid and retrieves bot username."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TradingJarvis/1.0"})
        with urllib.request.urlopen(req, timeout=10) as res:
            data = json.loads(res.read().decode("utf-8"))
            if data.get("ok"):
                return {"valid": True, "user": data.get("result", {})}
    except urllib.error.HTTPError as e:
        return {"valid": False, "error": f"HTTP {e.code}: {e.reason}"}
    except Exception as e:
        return {"valid": False, "error": str(e)}
    return {"valid": False, "error": "Unknown verification error"}


def test_telegram_connection():
    """Performs end-to-end diagnostic test of the Telegram notification pipeline."""
    print("==================================================")
    print("      J.A.R.V.I.S. TELEGRAM DIAGNOSTIC TEST       ")
    print("==================================================")
    
    cfg = load_config()
    token = cfg.get("bot_token")
    chat_id = cfg.get("chat_id")

    print(f"[*] Checking Bot Token configuration: {'[PRESENT]' if token else '[MISSING]'}")
    print(f"[*] Checking Target Chat ID configuration: {'[PRESENT]' if chat_id else '[MISSING]'}")

    if not token or token.startswith("YOUR_"):
        print("[!] ERROR: TELEGRAM_BOT_TOKEN is not set or contains placeholder text.", file=sys.stderr)
        print("    Please configure your bot token in .env or resources/telegram_config.json.")
        return False

    if not chat_id or chat_id.startswith("YOUR_"):
        print("[!] ERROR: TELEGRAM_CHAT_ID is not set or contains placeholder text.", file=sys.stderr)
        print("    Please configure your chat ID in .env or resources/telegram_config.json.")
        return False

    print("\n[1/2] Verifying Bot Token with Telegram API...")
    check = verify_bot_token(token)
    if not check.get("valid"):
        print(f"[!] Bot Token verification failed: {check.get('error')}", file=sys.stderr)
        return False

    bot_info = check.get("user", {})
    print(f"[+] Bot Online: @{bot_info.get('username')} ({bot_info.get('first_name')})")

    print("\n[2/2] Transmitting Test Diagnostic Message...")
    content = (
        "<b>Diagnostic Status:</b> <code>ALL SYSTEMS NOMINAL</code>\n"
        "<b>Pipeline:</b> Telegram Notification Subsystem\n"
        "<b>Integration:</b> TradingJarvis v1.0\n\n"
        "<i>Sir, this test transmission confirms our secure communication link is fully functional.</i>"
    )
    formatted = format_jarvis_message(title="DIAGNOSTIC TEST", content=content, icon="🧪")
    
    success = send_raw_telegram_message(formatted, bot_token=token, chat_id=chat_id)
    if success:
        print("\n[+] SUCCESS: Test alert was delivered to Telegram!")
        print("==================================================")
        return True
    else:
        print("\n[!] Transmission failed. Check your chat ID and permissions.")
        print("==================================================")
        return False


def main():
    """Main function."""
    success = test_telegram_connection()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
