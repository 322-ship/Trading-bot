import os
import json
import time
import requests
import yfinance as yf
import schedule
from concurrent.futures import ThreadPoolExecutor, TimeoutError

# ======================
# CONFIG
# ======================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

USE_CLAUDE = False

WATCHLIST_FILE = "watchlist.json"
POSITIONS_FILE = "positions.json"
PENDING_FILE = "pending_trades.json"

last_update_id = 0

ASSETS = {
    "DELL": {"name": "Dell", "risk": "alto", "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08, "take_profit": 0.12},
    "LRCX": {"name": "Lam Research", "risk": "alto", "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08, "take_profit": 0.12},
    "SLB": {"name": "Schlumberger", "risk": "medio", "rsi_buy": 35, "rsi_sell": 70, "stop_loss": 0.06, "take_profit": 0.10},
    "VRT": {"name": "Vertiv", "risk": "alto", "rsi_buy": 30, "rsi_sell": 75, "stop_loss": 0.10, "take_profit": 0.15},
    "NBIS": {"name": "Nebius", "risk": "alto", "rsi_buy": 30, "rsi_sell": 75, "stop_loss": 0.10, "take_profit": 0.15},

    "NVDA": {"name": "Nvidia", "risk": "alto", "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08, "take_profit": 0.12},
    "TSM": {"name": "TSMC", "risk": "alto", "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08, "take_profit": 0.12},
    "AVGO": {"name": "Broadcom", "risk": "alto", "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08, "take_profit": 0.12},
    "AMD": {"name": "AMD", "risk": "alto", "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08, "take_profit": 0.12},
    "MU": {"name": "Micron", "risk": "alto", "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08, "take_profit": 0.12},

    "JNJ": {"name": "Johnson & Johnson", "risk": "medio", "rsi_buy": 30, "rsi_sell": 70, "stop_loss": 0.05, "take_profit": 0.10},
    "XOM": {"name": "Exxon Mobil", "risk": "medio", "rsi_buy": 30, "rsi_sell": 70, "stop_loss": 0.05, "take_profit": 0.10},
}

TRUSTED_SOURCES = [
    "Reuters",
    "Bloomberg",
    "Financial Times",
    "The Wall Street Journal",
    "CNBC",
    "MarketWatch",
    "Yahoo Finance"
]

# ======================
# TELEGRAM
# ======================

def manda_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Telegram non configurato")
        return

    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        requests.post(
            url,
            data={
                "chat_id": CHAT_ID,
                "text": message[:3900],
                "disable_web_page_preview": True
            },
            timeout=10
        )
    except Exception as e:
        print(f"Errore invio Telegram: {e}")


def leggi_messaggi():
    global last_update_id

    try:
        url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
        response = requests.get(
            url,
            params={"offset": last_update_id, "timeout": 5},
            timeout=10
        )
        return response.json()
    except Exception as e:
        print(f"Errore lettura Telegram: {e}")
        return {"ok": False, "result": []}

# ======================
# JSON
# ======================

def leggi_json(file_path, default):
    try:
        if not os.path.exists(file_path):
            return default
        with open(file_path, "r") as f:
            return json.load(f)
    except:
        return default


def salva_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def carica_watchlist():
    return leggi_json(WATCHLIST_FILE, [])


def salva_watchlist(data):
    salva_json(WATCHLIST_FILE, data)


def carica_posizioni():
    return leggi_json(POSITIONS_FILE, {})


def salva_posizioni(data):
    salva_json(POSITIONS_FILE, data)


def carica_pending():
    return leggi_json(PENDING_FILE, {})


def salva_pending(data):
    salva_json(PENDING_FILE, data)

# ======================
# DATA
# ======================

def config_default(symbol):
    return {
        "name": symbol,
        "risk": "medio",
        "rsi_buy": 35,
        "rsi_sell": 70,
        "stop_loss": 0.05,
        "take_profit": 0.08
    }


def tutti_gli_asset():
    assets = dict(ASSETS)
    for symbol in carica_watchlist():
        symbol = symbol.upper()
        if symbol not in assets:
            assets[symbol] = config_default(symbol)
    return assets


def estrai_news(ticker):
    try:
        news_items = ticker.news or []
    except:
        return "News non disponibili."

    news_text = ""

    for item in news_items[:3]:
        try:
            content = item.get("content") or {}

            title = content.get("title") or item.get("title") or "Titolo non disponibile"
            provider = content.get("provider") or {}
            publisher = provider.get("displayName") or item.get("publisher") or "Fonte sconosciuta"

            click_url = content.get("clickThroughUrl") or {}
            link = click_url.get("url") or item.get("link") or ""

            if publisher in TRUSTED_SOURCES:
                news_text += f"- {title}\nFonte: {publisher}\nLink: {link}\n\n"
        except:
            continue

    return news_text if news_text else "Nessuna news rilevante da fonti affidabili."


def analizza_asset(symbol, config):
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="5d", interval="15m")

    if data.empty or len(data) < 50:
        return {"symbol": symbol, "error": "Dati insufficienti"}

    close = data["Close"]

    price = float(close.iloc[-1])
    previous_price = float(close.iloc[-2])
    change_pct = ((price - previous_price) / previous_price) * 100

    ema20 = float(close.ewm(span=20).mean().iloc[-1])
    ema50 = float(close.ewm(span=50).mean().iloc[-1])

    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    rsi = float(100 - (100 / (1 + rs.iloc[-1])))

    volume = int(data["Volume"].iloc[-1])

    if rsi < config["rsi_buy"] and ema20 > ema50 and change_pct > 0:
        decision = "BUY"
    elif rsi > config["rsi_sell"] and ema20 < ema50 and change_pct < 0:
        decision = "SELL"
    else:
        decision = "HOLD"

    news = estrai_news(ticker)

    return {
        "symbol": symbol,
        "name": config["name"],
        "risk": config["risk"],
        "price": round(price, 2),
        "change_pct": round(change_pct, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "rsi": round(rsi, 2),
        "volume": volume,
        "stop_loss": config["stop_loss"],
        "take_profit": config["take_profit"],
        "decision": decision,
        "news": news
    }


def analizza_con_timeout(symbol, config, timeout_sec=25):
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(analizza_asset, symbol, config)
        try:
            return future.result(timeout=timeout_sec)
        except TimeoutError:
            return {"symbol": symbol, "error": "Timeout dati mercato"}
        except Exception as e:
            return {"symbol": symbol, "error": str(e)}

# ======================
# REPORT
# ======================

def aggiorna_pending(symbol, result):
    if result.get("decision") == "HOLD":
        return

    posizioni = carica_posizioni()
    if symbol in posizioni:
        return

    pending = carica_pending()
    pending[symbol] = {
        "decision": result["decision"],
        "price": result["price"],
        "risk": result["risk"],
        "stop_loss": result["stop_loss"],
        "take_profit": result["take_profit"],
        "created_at": time.ctime()
    }
    salva_pending(pending)


def crea_report(tipo="manuale"):
    assets = tutti_gli_asset()

    if tipo == "mattina":
        titolo = "🌅 REPORT MATTINA"
    elif tipo == "sera":
        titolo = "🌙 REPORT SERALE"
    elif tipo == "settimana":
        titolo = "📅 REPORT SETTIMANALE"
    else:
        titolo = "📌 REPORT MANUALE"

    manda_telegram(f"{titolo}\n⏳ Sto preparando il report asset per asset...")

    for symbol, config in assets.items():
        result = analizza_con_timeout(symbol, config)

        if "error" in result:
            manda_telegram(f"⚠️ {symbol}: {result['error']}")
            continue

        aggiorna_pending(symbol, result)

        msg = f"""
📊 {result["symbol"]} - {result["name"]}

💰 Prezzo: ${result["price"]}
📉 Variazione: {result["change_pct"]}%

📈 EMA20: {result["ema20"]}
📈 EMA50: {result["ema50"]}
📊 RSI: {result["rsi"]}
📦 Volume: {result["volume"]}

⚠️ Rischio: {result["risk"]}
🛑 Stop loss: {result["stop_loss"] * 100:.1f}%
🎯 Take profit: {result["take_profit"] * 100:.1f}%

🤖 Decisione: {result["decision"]}
"""

        if result["decision"] != "HOLD":
            msg += f"""

✅ Approva:
 /ok {symbol} IMPORTO

❌ Rifiuta:
 /no {symbol}
"""

        msg += f"""

📰 News:
{result["news"]}
"""

        manda_telegram(msg)
        time.sleep(1)

    manda_telegram("✅ Report completato.")

# ======================
# POSIZIONI
# ======================

def prezzo_attuale(symbol):
    try:
        data = yf.Ticker(symbol).history(period="1d", interval="5m")
        if data.empty:
            return None
        return float(data["Close"].iloc[-1])
    except:
        return None


def controlla_posizioni():
    posizioni = carica_posizioni()
    if not posizioni:
        return

    changed = False

    for symbol, p in list(posizioni.items()):
        current = prezzo_attuale(symbol)
        if current is None:
            continue

        entry = p["entry_price"]
        pnl_pct = ((current - entry) / entry) * 100

        stop = p["stop_loss"] * 100
        take = p["take_profit"] * 100

        if pnl_pct <= -stop:
            manda_telegram(f"🛑 STOP LOSS su {symbol}: P/L {pnl_pct:.2f}%")
            del posizioni[symbol]
            changed = True

        elif pnl_pct >= take:
            manda_telegram(f"🎯 TAKE PROFIT su {symbol}: P/L {pnl_pct:.2f}%")
            del posizioni[symbol]
            changed = True

    if changed:
        salva_posizioni(posizioni)

# ======================
# COMANDI
# ======================

def gestisci_comandi():
    global last_update_id

    data = leggi_messaggi()
    if not data.get("ok"):
        return

    for update in data.get("result", []):
        last_update_id = update["update_id"] + 1

        message = update.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))

        if chat_id != str(CHAT_ID):
            continue

        text = message.get("text", "").strip()

        if text == "/help":
            manda_telegram("""
Comandi disponibili:

/report
/list
/add QQQ
/remove QQQ
/pending
/ok TICKER IMPORTO
/no TICKER
/positions
/close TICKER
/help
""")

        elif text == "/report":
            crea_report("manuale")

        elif text == "/list":
            assets = tutti_gli_asset()
            manda_telegram("📊 Asset monitorati:\n" + "\n".join(assets.keys()))

        elif text.startswith("/add"):
            parts = text.split()
            if len(parts) < 2:
                manda_telegram("Uso corretto: /add QQQ")
                continue

            symbol = parts[1].upper()
            watchlist = carica_watchlist()

            if symbol not in watchlist and symbol not in ASSETS:
                watchlist.append(symbol)
                salva_watchlist(watchlist)
                manda_telegram(f"✅ Aggiunto {symbol}")
            else:
                manda_telegram(f"{symbol} è già monitorato")

        elif text.startswith("/remove"):
            parts = text.split()
            if len(parts) < 2:
                manda_telegram("Uso corretto: /remove QQQ")
                continue

            symbol = parts[1].upper()
            watchlist = carica_watchlist()

            if symbol in watchlist:
                watchlist.remove(symbol)
                salva_watchlist(watchlist)
                manda_telegram(f"❌ Rimosso {symbol}")
            else:
                manda_telegram(f"{symbol} non è nella watchlist extra")

        elif text == "/pending":
            pending = carica_pending()

            if not pending:
                manda_telegram("Nessun trade in attesa")
            else:
                msg = "⏳ Trade in attesa:\n"
                for symbol, trade in pending.items():
                    msg += f'\n{symbol}: {trade["decision"]} a ${trade["price"]}'
                manda_telegram(msg)

        elif text.startswith("/ok"):
            parts = text.split()
            if len(parts) < 3:
                manda_telegram("Uso corretto: /ok NVDA 100")
                continue

            symbol = parts[1].upper()
            amount = float(parts[2])

            pending = carica_pending()
            posizioni = carica_posizioni()

            if symbol not in pending:
                manda_telegram(f"Nessun trade in attesa per {symbol}")
                continue

            price = prezzo_attuale(symbol)
            if price is None:
                manda_telegram(f"Prezzo non disponibile per {symbol}")
                continue

            trade = pending[symbol]

            posizioni[symbol] = {
                "symbol": symbol,
                "action": trade["decision"],
                "amount": amount,
                "entry_price": price,
                "stop_loss": trade["stop_loss"],
                "take_profit": trade["take_profit"],
                "opened_at": time.ctime()
            }

            del pending[symbol]

            salva_posizioni(posizioni)
            salva_pending(pending)

            manda_telegram(f"""
✅ Posizione approvata

Asset: {symbol}
Azione: {trade["decision"]}
Capitale: ${amount}
Entry: ${price:.2f}
""")

        elif text.startswith("/no"):
            parts = text.split()
            if len(parts) < 2:
                manda_telegram("Uso corretto: /no NVDA")
                continue

            symbol = parts[1].upper()
            pending = carica_pending()

            if symbol in pending:
                del pending[symbol]
                salva_pending(pending)
                manda_telegram(f"❌ Trade rifiutato: {symbol}")
            else:
                manda_telegram(f"Nessun trade in attesa per {symbol}")

        elif text == "/positions":
            posizioni = carica_posizioni()

            if not posizioni:
                manda_telegram("Nessuna posizione aperta")
            else:
                msg = "📌 Posizioni aperte:\n"
                for symbol, p in posizioni.items():
                    current = prezzo_attuale(symbol)
                    if current:
                        pnl = ((current - p["entry_price"]) / p["entry_price"]) * 100
                        msg += f'\n{symbol}: ${p["amount"]} | Entry ${p["entry_price"]:.2f} | Ora ${current:.2f} | P/L {pnl:.2f}%'
                    else:
                        msg += f'\n{symbol}: ${p["amount"]}'
                manda_telegram(msg)

        elif text.startswith("/close"):
            parts = text.split()
            if len(parts) < 2:
                manda_telegram("Uso corretto: /close NVDA")
                continue

            symbol = parts[1].upper()
            posizioni = carica_posizioni()

            if symbol in posizioni:
                del posizioni[symbol]
                salva_posizioni(posizioni)
                manda_telegram(f"🔒 Posizione chiusa: {symbol}")
            else:
                manda_telegram(f"Nessuna posizione aperta su {symbol}")

# ======================
# SCHEDULE
# ======================

schedule.every().day.at("07:30").do(lambda: crea_report("mattina"))
schedule.every().day.at("20:30").do(lambda: crea_report("sera"))
schedule.every().saturday.at("10:00").do(lambda: crea_report("settimana"))
schedule.every(5).minutes.do(controlla_posizioni)

print("Bot avviato... routine attiva.")

while True:
    gestisci_comandi()
    schedule.run_pending()
    time.sleep(5)