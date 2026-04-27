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

TOKEN = os.getenv("8792659138:AAEjyeUVGwNSmD-kTN-f8TX9AxFE5InjJ3c")
CHAT_ID = os.getenv("7595410408")

USE_CLAUDE = False  # per ora OFF, lo riattiviamo quando paghi Claude

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
    "PLTR": {"name": "Palantir", "risk": "alto", "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08, "take_profit": 0.12},
    "LMT": {"name": "Lockheed Martin", "risk": "medio", "rsi_buy": 30, "rsi_sell": 70, "stop_loss": 0.05, "take_profit": 0.10},
    "PFE": {"name": "Pfizer", "risk": "medio", "rsi_buy": 30, "rsi_sell": 70, "stop_loss": 0.05, "take_profit": 0.10}
}

UNDER_RADAR = ["QQQ", "SMH", "SOXX", "XLK", "XLE", "IWM", "BOTZ", "URA", "ARKQ", "XBI", "PANW", "CRWD", "NET", "DDOG", "ENPH"]


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
# ALGORITMO MIGLIORATO
# ======================

def score_risk_adjustment(risk):
    if risk == "basso":
        return 5
    if risk == "medio":
        return 0
    if risk == "alto":
        return -5
    return 0


def calcola_rsi(close):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    return float(100 - (100 / (1 + rs.iloc[-1])))


def calcola_confidence(price, ema20, ema50, ema200, rsi, change_15m, change_5d, volume, avg_volume, config):
    confidence = 50
    reasons = []

    # Trend breve
    if ema20 > ema50:
        confidence += 12
        reasons.append("trend breve positivo")
    else:
        confidence -= 12
        reasons.append("trend breve debole")

    # Trend lungo
    if price > ema200:
        confidence += 10
        reasons.append("prezzo sopra EMA200")
    else:
        confidence -= 10
        reasons.append("prezzo sotto EMA200")

    # Momentum
    if change_15m > 0:
        confidence += 6
        reasons.append("momentum 15m positivo")
    else:
        confidence -= 6
        reasons.append("momentum 15m negativo")

    if change_5d > 1:
        confidence += 8
        reasons.append("momentum 5 giorni forte")
    elif change_5d < -1:
        confidence -= 8
        reasons.append("momentum 5 giorni debole")

    # RSI
    if 45 <= rsi <= 62:
        confidence += 8
        reasons.append("RSI sano")
    elif rsi < config["rsi_buy"]:
        confidence += 10
        reasons.append("RSI basso: possibile rimbalzo")
    elif rsi > config["rsi_sell"]:
        confidence -= 12
        reasons.append("RSI alto: rischio ipercomprato")

    # Volume
    if avg_volume > 0:
        volume_ratio = volume / avg_volume
        if volume_ratio > 1.4 and change_15m > 0:
            confidence += 10
            reasons.append("volume forte con prezzo in salita")
        elif volume_ratio > 1.4 and change_15m < 0:
            confidence -= 10
            reasons.append("volume forte con prezzo in discesa")
        elif volume_ratio < 0.6:
            confidence -= 4
            reasons.append("volume debole")

    # Rischio asset
    confidence += score_risk_adjustment(config["risk"])

    confidence = max(0, min(100, int(confidence)))
    return confidence, reasons


def decisione_da_confidence(confidence):
    if confidence >= 72:
        return "BUY"
    if confidence <= 30:
        return "SELL"
    return "HOLD"


def analizza_asset(symbol, config):
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="6mo", interval="1d")

    if data.empty or len(data) < 60:
        return {"symbol": symbol, "error": "Dati insufficienti"}

    close = data["Close"]
    volume_series = data["Volume"]

    price = float(close.iloc[-1])
    previous_price = float(close.iloc[-2])
    old_price = float(close.iloc[-6]) if len(close) >= 6 else previous_price

    change_15m = ((price - previous_price) / previous_price) * 100
    change_5d = ((price - old_price) / old_price) * 100

    ema20 = float(close.ewm(span=20).mean().iloc[-1])
    ema50 = float(close.ewm(span=50).mean().iloc[-1])
    ema200 = float(close.ewm(span=200).mean().iloc[-1])

    rsi = calcola_rsi(close)

    volume = int(volume_series.iloc[-1])
    avg_volume = float(volume_series.rolling(20).mean().iloc[-1])

    confidence, reasons = calcola_confidence(
        price, ema20, ema50, ema200, rsi,
        change_15m, change_5d,
        volume, avg_volume, config
    )

    decision = decisione_da_confidence(confidence)

    return {
        "symbol": symbol,
        "name": config["name"],
        "risk": config["risk"],
        "price": round(price, 2),
        "change_1d": round(change_15m, 2),
        "change_5d": round(change_5d, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "ema200": round(ema200, 2),
        "rsi": round(rsi, 2),
        "volume": volume,
        "avg_volume": int(avg_volume),
        "confidence": confidence,
        "decision": decision,
        "reasons": reasons,
        "stop_loss": config["stop_loss"],
        "take_profit": config["take_profit"]
    }


def analizza_con_timeout(symbol, config, timeout_sec=20):
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


def messaggio_asset(result):
    reasons = "\n".join([f"• {r}" for r in result["reasons"][:4]])

    msg = f"""
📊 {result["symbol"]} - {result["name"]}

💰 Prezzo: ${result["price"]}
📉 1D: {result["change_1d"]}%
📆 5D: {result["change_5d"]}%

📈 EMA20: {result["ema20"]}
📈 EMA50: {result["ema50"]}
📈 EMA200: {result["ema200"]}
📊 RSI: {result["rsi"]}

📦 Volume: {result["volume"]}
📦 Volume medio: {result["avg_volume"]}

⚠️ Rischio: {result["risk"]}
🎯 Confidence: {result["confidence"]}%
🤖 Decisione: {result["decision"]}

🧠 Motivi:
{reasons}

🛑 Stop loss: {result["stop_loss"] * 100:.1f}%
🎯 Take profit: {result["take_profit"] * 100:.1f}%
"""

    if result["decision"] == "BUY":
        msg += f"""

✅ Approva simulazione:
 /ok {result["symbol"]} IMPORTO

❌ Rifiuta:
 /no {result["symbol"]}
"""

    return msg


def crea_report(tipo="manuale"):
    manda_telegram("📌 REPORT\n⏳ Analizzo gli asset e preparo ranking TOP...")

    risultati = []

    for symbol, config in tutti_gli_asset().items():
        result = analizza_con_timeout(symbol, config)

        if "error" in result:
            manda_telegram(f"⚠️ {symbol}: {result['error']}")
            continue

        aggiorna_pending(symbol, result)
        risultati.append(result)

    risultati.sort(key=lambda x: x["confidence"], reverse=True)

    top = risultati[:5]

    msg = "🏆 TOP 5 OPPORTUNITÀ\n"
    for i, r in enumerate(top, 1):
        msg += f'\n{i}. {r["symbol"]} | {r["decision"]} | Confidence {r["confidence"]}% | RSI {r["rsi"]} | 5D {r["change_5d"]}%'

    manda_telegram(msg)

    for r in top:
        manda_telegram(messaggio_asset(r))
        time.sleep(1)

    manda_telegram("✅ Report completato.")


def suggerisci_under_radar():
    manda_telegram("🔎 Cerco opportunità sotto radar...")

    risultati = []

    for symbol in UNDER_RADAR:
        result = analizza_con_timeout(symbol, config_default(symbol))
        if "error" not in result:
            risultati.append(result)

    risultati.sort(key=lambda x: x["confidence"], reverse=True)

    top = [r for r in risultati if r["confidence"] >= 65][:5]

    if not top:
        manda_telegram("Nessuna opportunità sotto radar interessante al momento.")
        return

    for r in top:
        manda_telegram(f"""
💡 SOTTO RADAR: {r["symbol"]}

Prezzo: ${r["price"]}
Confidence: {r["confidence"]}%
Decisione: {r["decision"]}
RSI: {r["rsi"]}
5D: {r["change_5d"]}%

Motivi:
{chr(10).join(["• " + x for x in r["reasons"][:4]])}

Per monitorarlo:
 /add {r["symbol"]}
""")


# ======================
# SIMULAZIONE PAPER INTERNA
# ======================

def prezzo_attuale(symbol):
    try:
        data = yf.Ticker(symbol).history(period="5d", interval="1d")
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
            manda_telegram(f"🛑 STOP LOSS SIMULATO su {symbol}: P/L {pnl_pct:.2f}%")
            del posizioni[symbol]
            salva_posizioni(posizioni)

        elif pnl_pct >= take:
            manda_telegram(f"🎯 TAKE PROFIT SIMULATO su {symbol}: P/L {pnl_pct:.2f}%")
            del posizioni[symbol]
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
                manda_telegram("Uso: /add QQQ")
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
                manda_telegram("Uso: /remove QQQ")
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
                manda_telegram("Uso: /ok NVDA 100")
                continue

            symbol = parts[1].upper()
            amount = float(parts[2])

            pending = carica_pending()
            posizioni = carica_posizioni()

            if symbol not in pending:
                manda_telegram(f"Nessun trade in attesa per {symbol}")
                continue

            trade = pending[symbol]
            price = prezzo_attuale(symbol) or trade["price"]

            posizioni[symbol] = {
                "symbol": symbol,
                "amount": amount,
                "entry_price": price,
                "stop_loss": trade["stop_loss"],
                "take_profit": trade["take_profit"],
                "confidence": trade["confidence"],
                "opened_at": time.ctime()
            }

            del pending[symbol]

            salva_posizioni(posizioni)
            salva_pending(pending)

            manda_telegram(f"""
✅ TRADE SIMULATO APERTO

Asset: {symbol}
Capitale: ${amount}
Entry: ${price:.2f}
Confidence: {trade["confidence"]}%
""")

        elif text.startswith("/no"):
            parts = text.split()
            if len(parts) < 2:
                manda_telegram("Uso: /no NVDA")
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
                manda_telegram("Nessuna posizione simulata aperta")
            else:
                msg = "📌 Posizioni simulate:\n"
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
                manda_telegram("Uso: /close NVDA")
                continue

            symbol = parts[1].upper()
            posizioni = carica_posizioni()

            if symbol in posizioni:
                del posizioni[symbol]
                salva_posizioni(posizioni)
                manda_telegram(f"🔒 Posizione simulata chiusa: {symbol}")
            else:
                manda_telegram(f"Nessuna posizione aperta su {symbol}")


# ======================
# SCHEDULE
# ======================

schedule.every().day.at("07:30").do(lambda: crea_report("mattina"))
schedule.every().day.at("20:30").do(lambda: crea_report("sera"))
schedule.every(3).days.do(lambda: manda_telegram("📆 Controllo 3 giorni: mandami /positions e miglioriamo il bot."))
schedule.every(5).minutes.do(controlla_posizioni)

print("Bot avviato... algoritmo migliorato attivo.")

while True:
    gestisci_comandi()
    schedule.run_pending()
    time.sleep(5)