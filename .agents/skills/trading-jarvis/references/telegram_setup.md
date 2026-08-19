# Telegram Bot & Chat ID Setup Guide

Follow these steps to configure your Telegram integration for J.A.R.V.I.S.

---

## Step 1: Create Your Telegram Bot with `@BotFather`

1. Open Telegram and search for `@BotFather`.
2. Send `/newbot` to start the bot creation wizard.
3. Choose a friendly display name (e.g. `Trading Jarvis AI`).
4. Choose a unique username ending in `bot` (e.g. `MyTradingJarvisBot`).
5. Copy the generated **HTTP API Bot Token** (looks like `7123456789:AAF_xYz1234567890abcdef...`).

---

## Step 2: Retrieve Your Telegram `CHAT_ID`

### Option A: Using `@userinfobot` (Fastest for Direct Messages)
1. In Telegram, search for `@userinfobot`.
2. Click **Start**.
3. It will reply with your numeric **Id** (e.g. `123456789`). This is your `CHAT_ID`.

### Option B: For Telegram Groups / Channels
1. Add your newly created bot as an **Administrator** in your private channel or group.
2. Send a sample message in the group (e.g., `Hello Jarvis`).
3. Open your browser and visit:
   `https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates`
4. Look for the `"chat":{"id": -100xxxxxxxxxx}` object in the JSON response.

---

## Step 3: Configure Environment Variables

### Option A: Environment Variables (Recommended)
Set the environment variables in PowerShell or your terminal:

```powershell
$env:TELEGRAM_BOT_TOKEN="7123456789:AAF_xYz..."
$env:TELEGRAM_CHAT_ID="123456789"
```

Or create a `.env` file in the workspace root:
```env
TELEGRAM_BOT_TOKEN=7123456789:AAF_xYz...
TELEGRAM_CHAT_ID=123456789
```

### Option B: Local Config File
Copy [`resources/telegram_config.template.json`](../resources/telegram_config.template.json) to `.agents/skills/trading-jarvis/resources/telegram_config.json` and insert your credentials:

```json
{
  "bot_token": "7123456789:AAF_xYz...",
  "chat_id": "123456789",
  "parse_mode": "HTML"
}
```

---

## Step 4: Verify Connection

Run the diagnostic test script:

```powershell
python .agents/skills/trading-jarvis/scripts/test_alert.py
```

If successful, J.A.R.V.I.S. will transmit a confirmation message to your Telegram account.
