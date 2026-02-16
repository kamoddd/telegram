# Ice Schedule Telegram Bot

The bot:
- sends 2 schedule images when the `Schedule` button is pressed;
- checks the website every hour;
- notifies all subscribed users when images change.

## Repository Structure
- repository root: `telegram/`
- bot project: `telegram/LeaderIceBot/`

## Stack
- Python 3.10+
- `python-telegram-bot` (long polling)
- `requests` + `BeautifulSoup`
- SQLite (local)

## 1) Create a Telegram Bot
1. Open `@BotFather`.
2. Run `/newbot`.
3. Copy the bot token.

## 2) Project Setup
From repository root:
```bash
cd LeaderIceBot
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill `.env`:
- `BOT_TOKEN` - token from BotFather
- `TARGET_URL` - source website with schedule images
- `CHECK_INTERVAL_MINUTES` - polling interval (default `60`)
- `DB_PATH` - SQLite database path

## 3) Run
```bash
cd LeaderIceBot
source .venv/bin/activate
python bot.py
```

## 4) Usage
- Send `/start` to subscribe the chat to updates.
- Press `Schedule` to receive the current 2 images.
- Send `/stop` to unsubscribe from notifications.

## How It Works
1. The bot parses the page and finds 2 schedule images.
2. It downloads images and calculates `sha256`.
3. It compares hashes with previous values in SQLite.
4. If changed, it sends updated images to subscribers.

## Logs
The bot currently logs to console (stdout/stderr).

Example:
- `logger.exception("Failed to send schedule: %s", exc)`

If running from terminal, logs are visible in that terminal.
If running as a service, use the service logs.

## Git and Secrets
- `.env` contains secrets and must not be committed.
- Commit `.env.example` only.

## Home Hosting Note
The project uses **long polling**, so no inbound port is required.
The host machine only needs outbound internet access.
