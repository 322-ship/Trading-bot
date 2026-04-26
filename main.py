import os
import json
import time
import requests
import yfinance as yf
import schedule
import anthropic
from concurrent.futures import ThreadPoolExecutor, TimeoutError

# ======================
# CONFIG
# ======================

TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
USE_CLAUDE = True

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")
ALPACA_BASE_URL = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets")

WATCHLIST_FILE = "watchlist.json"
POSITIONS_FILE = "positions.json"
PENDING_FILE = "pending_trades.json"

last_update_id = 0

ASSETS = {
    "SPY": {"name": "S&P 500 ETF", "risk": "basso", "rsi_buy": 35, "rsi_sell": 70, "stop_loss": 0.04, "take_profit": 0.08},

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

    "PLTR": {"name": "Palantir", "risk": "alto",
         "rsi_buy": 32, "rsi_sell": 72,
         "stop_loss": 0.08, "take_profit": 0.12},

    "LMT": {"name": "Lockheed Martin", "risk": "medio",
        "rsi_buy": 30, "rsi_sell": 70,
        "stop_loss": 0.05, "take_profit": 0.10},

    "PFE": {"name": "Pfizer", "risk": "medio",
        "rsi_buy": 30, "rsi_sell": 70,
        "stop_loss": 0.05, "take_profit": 0.10}
}

UNDER_RADAR = ["QQQ", "SMH", "SOXX", "XLK", "XLE", "IWM", "BOTZ", "URA", "ARKQ", "XBI"]

# ======================
# TELEGRAM
# ======================

def manda_telegram(message):
    if not TOKEN or not CHAT_ID:
        print("Telegram non configurato")
        return

    try:
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": message[:3900],
                "disable_web_page_preview": True
            },
            timeout=10
        )
    except Exception as e:
        print(f"Errore Telegram: {e}")


def leggi_messaggi():
    global last_update_id

    try:
        r = requests.get(
            f"https://api.telegram.org/bot{TOKEN}/getUpdates",
            params={"offset": last_update_id, "timeout": 5},
            timeout=10
        )
        return r.json()
    except Exception as e:
        print(f"Errore lettura Telegram: {e}")
        return {"ok": False, "result": []}

# ======================
# JSON
# ======================

def leggi_json(file_path, default):
    try:
        if not os.path.exists(file_path):
            salva_json(file_path, default)
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
# ASSET
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

# ======================
# ALPACA PAPER
# ======================

def alpaca_headers():
    return {
        "APCA-API-KEY-ID": ALPACA_API_KEY,
        "APCA-API-SECRET-KEY": ALPACA_SECRET_KEY,
        "Content-Type": "application/json"
    }


def alpaca_configurato():
    return bool(ALPACA_API_KEY and ALPACA_SECRET_KEY)


def alpaca_submit_order(symbol, side, amount):
    if not alpaca_configurato():
        return False, "Alpaca non configurato"

    try:
        payload = {
            "symbol": symbol,
            "side": side,
            "type": "market",
            "time_in_force": "day",
            "notional": str(round(float(amount), 2))
        }

        r = requests.post(
            f"{ALPACA_BASE_URL}/v2/orders",
            headers=alpaca_headers(),
            json=payload,
            timeout=15
        )

        if r.status_code in [200, 201]:
            return True, r.json()

        return False, r.text

    except Exception as e:
        return False, str(e)


def alpaca_close_position(symbol):
    if not alpaca_configurato():
        return False, "Alpaca non configurato"

    try:
        r = requests.delete(
            f"{ALPACA_BASE_URL}/v2/positions/{symbol}",
            headers=alpaca_headers(),
            timeout=15
        )

        if r.status_code in [200, 204]:
            return True, "Posizione chiusa"

        return False, r.text

    except Exception as e:
        return False, str(e)

# ======================
# ANALISI
# ======================

def estrai_news(ticker):
    try:
        news_items = ticker.news or []
    except:
        return "News non disponibili."

    righe = []

    for item in news_items[:3]:
        try:
            content = item.get("content") or {}

            title = content.get("title") or item.get("title") or "Titolo non disponibile"
            provider = content.get("provider") or {}
            publisher = provider.get("displayName") or item.get("publisher") or "Fonte sconosciuta"

            righe.append(f"- {title}\nFonte: {publisher}")
        except:
            continue

    return "\n\n".join(righe) if righe else "Nessuna news rilevante."


def calcola_confidence(ema20, ema50, rsi, change_pct, config):
    confidence = 50

    if ema20 > ema50:
        confidence += 15
    else:
        confidence -= 15

    if change_pct > 0:
        confidence += 10
    else:
        confidence -= 10

    if rsi < config["rsi_buy"]:
        confidence += 15
    elif rsi > config["rsi_sell"]:
        confidence -= 15

    if config["risk"] == "basso":
        confidence += 5
    elif config["risk"] == "alto":
        confidence -= 5

    return max(0, min(100, int(confidence)))


def decisione_da_confidence(confidence):
    if confidence >= 65:
        return "BUY"
    if confidence <= 35:
        return "SELL"
    return "HOLD"


def analisi_claude(symbol, result):
    if not USE_CLAUDE or not ANTHROPIC_API_KEY:
        return ""

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        prompt = f"""
Analizza questo asset in modo prudente.

Asset: {symbol}
Prezzo: {result["price"]}
Variazione: {result["change_pct"]}%
EMA20: {result["ema20"]}
EMA50: {result["ema50"]}
RSI: {result["rsi"]}
Rischio: {result["risk"]}
Confidence tecnica: {result["confidence"]}%
Decisione tecnica: {result["decision"]}

News:
{result["news"]}

Rispondi breve in italiano:
1. confermi o indebolisci il segnale?
2. rischio principale
3. opportunità
4. BUY, HOLD o SELL
5. capitale prudente: basso, medio o alto

Non promettere guadagni.
"""

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=400,
        messages=[{"role": "user", "content": prompt}]
    )

    text_parts = []

    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            text_parts.append(str(text))

    return "\n".join(text_parts).strip()

    except Exception as e:
        return f"Claude non disponibile: {e}"


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
    confidence = calcola_confidence(ema20, ema50, rsi, change_pct, config)
    decision = decisione_da_confidence(confidence)
    news = estrai_news(ticker)

    result = {
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
        "confidence": confidence,
        "decision": decision,
        "news": news,
        "ai": ""
    }

    result["ai"] = analisi_claude(symbol, result)
    return result


def analizza_con_timeout(symbol, config, timeout_sec=30):
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
    if result["decision"] == "HOLD":
        return

    posizioni = carica_posizioni()
    pending = carica_pending()

    if symbol in posizioni:
        return

    pending[symbol] = {
        "decision": result["decision"],
        "price": result["price"],
        "risk": result["risk"],
        "confidence": result["confidence"],
        "stop_loss": result["stop_loss"],
        "take_profit": result["take_profit"],
        "created_at": time.ctime()
    }

    salva_pending(pending)


def crea_report(tipo="manuale"):
    if tipo == "mattina":
        titolo = "🌅 REPORT MATTINA"
    elif tipo == "sera":
        titolo = "🌙 REPORT SERALE"
    else:
        titolo = "📌 REPORT MANUALE"

    manda_telegram(f"{titolo}\n⏳ Sto preparando il report asset per asset...")

    for symbol, config in tutti_gli_asset().items():
        result = analizza_con_timeout(symbol, config)

        if "error" in result:
            manda_telegram(f"⚠️ {symbol}: {result['error']}")
            continue

        aggiorna_pending(symbol, result)

        msg = f"""
📊 {symbol} - {result["name"]}

💰 Prezzo: ${result["price"]}
📉 Variazione: {result["change_pct"]}%

📈 EMA20: {result["ema20"]}
📈 EMA50: {result["ema50"]}
📊 RSI: {result["rsi"]}
📦 Volume: {result["volume"]}

⚠️ Rischio: {result["risk"]}
🎯 Confidence: {result["confidence"]}%

🛑 Stop loss: {result["stop_loss"] * 100:.1f}%
🎯 Take profit: {result["take_profit"] * 100:.1f}%

🤖 Decisione: {result["decision"]}
"""

        if result["decision"] != "HOLD":
            msg += f"""

✅ Approva paper trade:
 /ok {symbol} IMPORTO

❌ Rifiuta:
 /no {symbol}
"""

        msg += f"""

📰 News:
{result["news"]}
"""

        if result["ai"]:
            msg += f"""

🧠 Claude:
{result["ai"]}
"""

        manda_telegram(msg)
        time.sleep(1)

    manda_telegram("✅ Report completato.")

# ======================
# IDEE SOTTO RADAR
# ======================

def suggerisci_under_radar():
    manda_telegram("🔎 Cerco opportunità sotto radar...")

    found = 0

    for symbol in UNDER_RADAR:
        result = analizza_con_timeout(symbol, config_default(symbol))

        if "error" in result:
            continue

        if result["confidence"] >= 65:
            found += 1
            manda_telegram(f"""
💡 Opportunità possibile: {symbol}

Prezzo: ${result["price"]}
Confidence: {result["confidence"]}%
Decisione: {result["decision"]}
RSI: {result["rsi"]}
EMA20/EMA50: {result["ema20"]}/{result["ema50"]}

Per monitorarlo:
 /add {symbol}
""")

    if found == 0:
        manda_telegram("Nessuna opportunità interessante sotto radar al momento.")

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

    for symbol, p in list(posizioni.items()):
        current = prezzo_attuale(symbol)
        if current is None:
            continue

        entry = p["entry_price"]
        pnl_pct = ((current - entry) / entry) * 100

        stop = p["stop_loss"] * 100
        take = p["take_profit"] * 100

        if pnl_pct <= -stop:
            manda_telegram(f"🛑 STOP LOSS PAPER su {symbol}: P/L {pnl_pct:.2f}%")
            alpaca_close_position(symbol)
            del posizioni[symbol]
            salva_posizioni(posizioni)

        elif pnl_pct >= take:
            manda_telegram(f"🎯 TAKE PROFIT PAPER su {symbol}: P/L {pnl_pct:.2f}%")
            alpaca_close_position(symbol)
            del posizioni[symbol]
            salva_posizioni(posizioni)

# ======================
# COMANDI TELEGRAM
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
/ideas
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

        elif text == "/ideas":
            suggerisci_under_radar()

        elif text == "/list":
            manda_telegram("📊 Asset monitorati:\n" + "\n".join(tutti_gli_asset().keys()))

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
                    msg += f'\n{symbol}: {trade["decision"]} | Confidence {trade["confidence"]}% | ${trade["price"]}'
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

            trade = pending[symbol]

            if trade["decision"] == "BUY":
                ok, response = alpaca_submit_order(symbol, "buy", amount)
            else:
                ok, response = False, "Per ora il bot esegue solo BUY paper. SELL chiude posizioni."

            if not ok:
                manda_telegram(f"❌ Errore Alpaca paper su {symbol}:\n{response}")
                continue

            price = prezzo_attuale(symbol) or trade["price"]

            posizioni[symbol] = {
                "symbol": symbol,
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
✅ PAPER TRADE ESEGUITO

Asset: {symbol}
Capitale: ${amount}
Entry stimata: ${price:.2f}
Confidence: {trade["confidence"]}%
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
                manda_telegram("Nessuna posizione paper aperta")
            else:
                msg = "📌 Posizioni paper aperte:\n"

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

            ok, response = alpaca_close_position(symbol)

            if symbol in posizioni:
                del posizioni[symbol]
                salva_posizioni(posizioni)

            manda_telegram(f"🔒 Chiusura {symbol}: {response}")

# ======================
# SCHEDULE
# ======================

schedule.every().day.at("07:30").do(lambda: crea_report("mattina"))
schedule.every().day.at("20:30").do(lambda: crea_report("sera"))
schedule.every(3).days.do(lambda: manda_telegram("📆 Controllo 3 giorni: mandami /positions e screenshot Alpaca."))
schedule.every(5).minutes.do(controlla_posizioni)

print("Bot avviato... routine attiva.")

while True:
    gestisci_comandi()
    schedule.run_pending()
    time.sleep(5)