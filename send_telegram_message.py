#!/usr/bin/env python3
"""
Send a message to a Telegram chat using a bot.

Setup:
1. Create a bot by messaging @BotFather on Telegram and run /newbot.
   Save the bot token it gives you.
2. Get your chat ID:
   - Send any message to your new bot.
   - Open https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates in a browser.
   - Look for "chat":{"id": <number>, ...} — that number is your chat ID.

Usage:
    # Using environment variables
    export TELEGRAM_BOT_TOKEN="123456:ABC-DEF..."
    export TELEGRAM_CHAT_ID="123456789"
    python send_telegram_message.py "Hello from Python!"

    # Or pass everything on the command line
    python send_telegram_message.py --token <BOT_TOKEN> --chat-id <CHAT_ID> "Hello!"
"""

import argparse
import os
import sys
from urllib import request, parse, error


def send_message(bot_token: str, chat_id: str, text: str) -> dict:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    data = parse.urlencode({
        "chat_id": chat_id,
        "text": text,
    }).encode("utf-8")

    req = request.Request(url, data=data, method="POST")
    try:
        with request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode("utf-8")
            return {"status": resp.status, "body": body}
    except error.HTTPError as e:
        return {"status": e.code, "body": e.read().decode("utf-8", errors="replace")}
    except error.URLError as e:
        return {"status": None, "body": f"Network error: {e.reason}"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a message to a Telegram chat via a bot.")
    parser.add_argument("message", nargs="?", help="The text message to send.")
    parser.add_argument("--token", default=os.environ.get("TELEGRAM_BOT_TOKEN"),
                        help="Telegram bot token (or set TELEGRAM_BOT_TOKEN).")
    parser.add_argument("--chat-id", default=os.environ.get("TELEGRAM_CHAT_ID"),
                        help="Target chat ID (or set TELEGRAM_CHAT_ID).")
    args = parser.parse_args()

    if not args.token:
        print("Error: bot token is required. Pass --token or set TELEGRAM_BOT_TOKEN.", file=sys.stderr)
        return 2
    if not args.chat_id:
        print("Error: chat id is required. Pass --chat-id or set TELEGRAM_CHAT_ID.", file=sys.stderr)
        return 2
    if not args.message:
        print("Error: message text is required.", file=sys.stderr)
        return 2

    result = send_message(args.token, args.chat_id, args.message)
    print(f"HTTP {result['status']}")
    print(result["body"])
    return 0 if result["status"] == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
