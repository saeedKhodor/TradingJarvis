# === CODE INDEX ===
# 1. Imports & Configuration Loading (Line 15)
# 2. send_raw_telegram_message() - Core HTTPS POST dispatcher to Telegram Bot API (Line 42)
# 3. format_jarvis_message() - Wraps alert content in J.A.R.V.I.S. styling (Line 72)
# 4. send_signal_alert() - Formats and dispatches trade signal notifications (Line 98)
# 5. send_risk_alert() - Formats and dispatches urgent risk/drawdown alerts (Line 135)
# 6. send_session_briefing() - Formats and dispatches market briefing summaries (Line 172)
# 7. main() - CLI entry point for command-line notifications (Line 206)
# =================

import os
import sys
import json
import urllib.request
import urllib.parse
import urllib.error
import argparse
from datetime import datetime
from typing import Optional, Dict, Any


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load Telegram configuration from environment variables, .env file, or JSON config."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    # Try reading .env file if env vars are unset
    if not (token and chat_id):
        # Look for .env in current directory or workspace root
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        workspace_root = os.path.dirname(os.path.dirname(base_dir))
        for env_path in [os.path.join(workspace_root, ".env"), os.path.join(os.getcwd(), ".env")]:
            if os.path.exists(env_path):
                try:
                    with open(env_path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                k, v = k.strip(), v.strip().strip("\"'")
                                if k == "TELEGRAM_BOT_TOKEN" and not token:
                                    token = v
                                elif k == "TELEGRAM_CHAT_ID" and not chat_id:
                                    chat_id = v
                except Exception as e:
                    print(f"[J.A.R.V.I.S. Warning] Failed to read .env file {env_path}: {e}", file=sys.stderr)

    # If both token and chat_id are found and not placeholders, return them
    if token and chat_id and not token.startswith("YOUR_") and not chat_id.startswith("YOUR_"):
        return {"bot_token": token, "chat_id": chat_id, "parse_mode": "HTML"}
    
    # Fallback to config file
    if not config_path:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        config_path = os.path.join(base_dir, "resources", "telegram_config.json")
        template_path = os.path.join(base_dir, "resources", "telegram_config.template.json")
        if not os.path.exists(config_path) and os.path.exists(template_path):
            config_path = template_path

    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                if token and not token.startswith("YOUR_"):
                    cfg["bot_token"] = token
                if chat_id and not chat_id.startswith("YOUR_"):
                    cfg["chat_id"] = chat_id
                return cfg
        except Exception as e:
            print(f"[J.A.R.V.I.S. Warning] Failed to read config file {config_path}: {e}", file=sys.stderr)

    return {"bot_token": token or "", "chat_id": chat_id or "", "parse_mode": "HTML"}


def send_raw_telegram_message(
    message: str,
    bot_token: Optional[str] = None,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML"
) -> bool:
    """Dispatches a raw message string to the Telegram Bot API via HTTPS."""
    cfg = load_config()
    token = bot_token or cfg.get("bot_token")
    target_chat = chat_id or cfg.get("chat_id")

    if not token or token == "YOUR_TELEGRAM_BOT_TOKEN_HERE":
        print("[J.A.R.V.I.S. Error] Telegram Bot Token is missing or unconfigured.", file=sys.stderr)
        return False

    if not target_chat or target_chat == "YOUR_TELEGRAM_CHAT_ID_HERE":
        print("[J.A.R.V.I.S. Error] Telegram Chat ID is missing or unconfigured.", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            res_body = response.read().decode("utf-8")
            res_json = json.loads(res_body)
            if res_json.get("ok"):
                print("[J.A.R.V.I.S.] Notification transmitted successfully, sir.")
                return True
            else:
                print(f"[J.A.R.V.I.S. Error] API rejected transmission: {res_json}", file=sys.stderr)
                return False
    except urllib.error.HTTPError as e:
        err_content = e.read().decode("utf-8", errors="ignore")
        print(f"[J.A.R.V.I.S. Error] HTTP {e.code}: {err_content}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[J.A.R.V.I.S. Error] Transmission failed: {e}", file=sys.stderr)
        return False


def format_jarvis_message(title: str, content: str, icon: str = "🛡️") -> str:
    """Wraps notification content with J.A.R.V.I.S. header and signature."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    formatted = (
        f"{icon} <b>J.A.R.V.I.S. TELEMETRY</b> | {title}\n"
        f"<code>Timestamp: {timestamp}</code>\n\n"
        f"{content}\n\n"
        f"<i>At your service, sir.</i>"
    )
    return formatted


def send_signal_alert(
    symbol: str,
    action: str,
    entry_price: float,
    stop_loss: float,
    take_profit: float,
    strategy: str = "Quantitative Engine",
    timeframe: str = "M15",
    risk_reward: Optional[str] = None
) -> bool:
    """Formats and sends a high-priority trading signal alert."""
    icon = "📈" if action.upper() in ["BUY", "LONG"] else "📉"
    
    if not risk_reward and stop_loss and entry_price and take_profit:
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        if risk > 0:
            risk_reward = f"1:{reward / risk:.2f}"
        else:
            risk_reward = "N/A"

    body = (
        f"<b>Signal Detected:</b> <code>{action.upper()} {symbol}</code>\n"
        f"<b>Strategy:</b> {strategy} ({timeframe})\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 <b>Entry:</b> <code>{entry_price:.5f}</code>\n"
        f"🛑 <b>Stop Loss:</b> <code>{stop_loss:.5f}</code>\n"
        f"🎁 <b>Take Profit:</b> <code>{take_profit:.5f}</code>\n"
        f"⚖️ <b>Risk/Reward:</b> <code>{risk_reward or 'N/A'}</code>"
    )
    
    message = format_jarvis_message(
        title=f"TRADE SIGNAL [{symbol}]",
        content=body,
        icon=icon
    )
    return send_raw_telegram_message(message)


def send_risk_alert(
    level: str,
    metric_name: str,
    current_value: str,
    threshold: str,
    recommendation: str
) -> bool:
    """Formats and sends an urgent risk or drawdown alert."""
    icon = "🚨" if level.upper() in ["CRITICAL", "EMERGENCY"] else "⚠️"
    
    body = (
        f"<b>Risk Advisory Level:</b> <code>{level.upper()}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📊 <b>Metric:</b> {metric_name}\n"
        f"📉 <b>Current Value:</b> <code>{current_value}</code>\n"
        f"🛑 <b>Threshold Limit:</b> <code>{threshold}</code>\n\n"
        f"💡 <b>Directive / Protocol:</b>\n{recommendation}"
    )
    
    message = format_jarvis_message(
        title=f"RISK PROTOCOL [{level.upper()}]",
        content=body,
        icon=icon
    )
    return send_raw_telegram_message(message)


def send_session_briefing(
    session_name: str,
    equity: str,
    daily_pnl: str,
    open_positions: int,
    notes: str
) -> bool:
    """Formats and sends a daily market briefing or session status report."""
    icon = "🌐"
    
    body = (
        f"<b>Trading Session:</b> <code>{session_name}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💰 <b>Total Equity:</b> <code>{equity}</code>\n"
        f"📈 <b>Daily PnL:</b> <code>{daily_pnl}</code>\n"
        f"📂 <b>Open Positions:</b> <code>{open_positions}</code>\n\n"
        f"📋 <b>Diagnostics & Intelligence:</b>\n{notes}"
    )
    
    message = format_jarvis_message(
        title=f"SESSION BRIEFING [{session_name}]",
        content=body,
        icon=icon
    )
    return send_raw_telegram_message(message)


def main():
    """CLI dispatcher for J.A.R.V.I.S. Telegram notifications."""
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. Telegram Notification Dispatcher")
    parser.add_argument("--type", choices=["raw", "signal", "risk", "briefing"], default="raw", help="Alert category")
    parser.add_argument("--message", type=str, help="Raw message content")
    parser.add_argument("--symbol", type=str, help="Trading instrument symbol (e.g., EURUSD, XAUUSD)")
    parser.add_argument("--action", type=str, help="Trade action (BUY/SELL)")
    parser.add_argument("--entry", type=float, help="Entry price")
    parser.add_argument("--sl", type=float, help="Stop Loss price")
    parser.add_argument("--tp", type=float, help="Take Profit price")
    parser.add_argument("--strategy", type=str, default="Jarvis Algo", help="Strategy name")
    parser.add_argument("--level", type=str, default="Warning", help="Risk severity level")
    parser.add_argument("--metric", type=str, help="Risk metric name")
    parser.add_argument("--current", type=str, help="Current metric value")
    parser.add_argument("--threshold", type=str, help="Metric threshold")
    parser.add_argument("--notes", type=str, help="Briefing notes or risk recommendation")

    args = parser.parse_args()

    if args.type == "raw":
        msg = args.message or "Sir, all diagnostic systems are fully operational."
        formatted = format_jarvis_message(title="SYSTEM BROADCAST", content=msg, icon="⚡")
        success = send_raw_telegram_message(formatted)
    elif args.type == "signal":
        if not (args.symbol and args.action and args.entry and args.sl and args.tp):
            print("[J.A.R.V.I.S. Error] --symbol, --action, --entry, --sl, --tp are required for signal alert.", file=sys.stderr)
            sys.exit(1)
        success = send_signal_alert(
            symbol=args.symbol,
            action=args.action,
            entry_price=args.entry,
            stop_loss=args.sl,
            take_profit=args.tp,
            strategy=args.strategy
        )
    elif args.type == "risk":
        success = send_risk_alert(
            level=args.level,
            metric_name=args.metric or "Drawdown Limit",
            current_value=args.current or "N/A",
            threshold=args.threshold or "N/A",
            recommendation=args.notes or "Halting new order execution per risk protocol."
        )
    elif args.type == "briefing":
        success = send_session_briefing(
            session_name=args.symbol or "London/NY Overlap",
            equity=args.current or "$100,000.00",
            daily_pnl=args.threshold or "+$1,420.50 (+1.42%)",
            open_positions=int(args.entry or 0),
            notes=args.notes or "No critical volatility events detected on the economic calendar."
        )
    else:
        success = False

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
