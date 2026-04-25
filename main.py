import os
import json
import time
import requests
import yfinance as yf
import schedule
import anthropic
from flask import Flask
from threading import Thread

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
    "NVDA": {"name": "Nvidia", "risk": "alto",
         "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08,
         "take_profit": 0.12},

    "TSM": {"name": "TSMC", "risk": "alto",
        "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08,
        "take_profit": 0.12},

    "AVGO": {"name": "Broadcom", "risk": "alto",
         "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08,
         "take_profit": 0.12},

    "AMD": {"name": "AMD", "risk": "alto",
        "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08,
        "take_profit": 0.12},

    "MU": {"name": "Micron", "risk": "alto",
       "rsi_buy": 32, "rsi_sell": 72, "stop_loss": 0.08,
       "take_profit": 0.12},

    "JNJ": {"name": "Johnson & Johnson", "risk": "medio",
        "rsi_buy": 30, "rsi_sell": 70, "stop_loss": 0.05,
        "take_profit": 0.10},

    "XOM": {"name": "Exxon Mobil", "risk": "medio",
        "rsi_buy": 30, "rsi_sell": 70, "stop_loss": 0.05,
        "take_profit": 0.10},
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
# FLASK KEEP ALIVE
# ======================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot attivo"

def run_web():
    app.run(host="0.0.0.0", port=5000)

def keep_alive():
    t = Thread(target=run_web)
    t.daemon = True
    t.start()

# ======================
# TELEGRAM
# ======================

def manda_telegram(message):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": CHAT_ID,
        "text": message,
        "disable_web_page_preview": True
    })

def leggi_messaggi():
    global last_update_id

    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    params = {"timeout": 1, "offset": last_update_id}

    response = requests.get(url, params=params)
    return response.json()

# ======================
# JSON FILES
# ======================

def leggi_json(file_path, default):
    if not os.path.exists(file_path):
        return default

    try:
        with open(file_path, "r") as f:
            return json.load(f)
    except:
        return default

def salva_json(file_path, data):
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)

def carica_watchlist():
    return leggi_json(WATCHLIST_FILE, [])

def salva_watchlist(watchlist):
    salva_json(WATCHLIST_FILE, watchlist)

def carica_posizioni():
    return leggi_json(POSITIONS_FILE, {})

def salva_posizioni(posizioni):
    salva_json(POSITIONS_FILE, posizioni)

def carica_pending():
    return leggi_json(PENDING_FILE, {})

def salva_pending(pending):
    salva_json(PENDING_FILE, pending)

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
    final_assets = dict(ASSETS)
    watchlist = carica_watchlist()

    for symbol in watchlist:
        if symbol not in final_assets:
            final_assets[symbol] = config_default(symbol)

    return final_assets

def prezzo_attuale(symbol):
    ticker = yf.Ticker(symbol)
    data = ticker.history(period="1d", interval="5m")

    if data.empty:
        return None

    return float(data["Close"].iloc[-1])

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

        if not text:
            continue

        watchlist = carica_watchlist()
        pending = carica_pending()
        posizioni = carica_posizioni()

        if text.startswith("/add"):
            parts = text.split()
            if len(parts) < 2:
                manda_telegram("Uso corretto: /add QQQ")
                continue

            symbol = parts[1].upper()

            if symbol not in watchlist and symbol not in ASSETS:
                watchlist.append(symbol)
                salva_watchlist(watchlist)
                manda_telegram(f"✅ Aggiunto {symbol} alla watchlist")
            else:
                manda_telegram(f"{symbol} è già monitorato")

        elif text.startswith("/remove"):
            parts = text.split()
            if len(parts) < 2:
                manda_telegram("Uso corretto: /remove QQQ")
                continue

            symbol = parts[1].upper()

            if symbol in watchlist:
                watchlist.remove(symbol)
                salva_watchlist(watchlist)
                manda_telegram(f"❌ Rimosso {symbol}")
            else:
                manda_telegram(f"{symbol} non trovato nella watchlist extra")

        elif text.startswith("/list"):
            base = "\n".join(ASSETS.keys())
            extra = "\n".join(watchlist) if watchlist else "Nessun asset extra"

            manda_telegram(f"""
📊 ASSET BASE:
{base}

➕ WATCHLIST EXTRA:
{extra}
""")

        elif text.startswith("/report"):
            crea_report("manuale")

        elif text.startswith("/pending"):
            if not pending:
                manda_telegram("Nessun trade in attesa")
            else:
                msg = "⏳ TRADE IN ATTESA:\n"
                for symbol, trade in pending.items():
                    msg += f'\n{symbol}: {trade["decision"]} | rischio {trade["risk"]}'
                manda_telegram(msg)

        elif text.startswith("/ok"):
            parts = text.split()

            if len(parts) < 3:
                manda_telegram("Uso corretto: /ok DELL 100")
                continue

            symbol = parts[1].upper()

            try:
                amount = float(parts[2])
            except:
                manda_telegram("Importo non valido. Esempio: /ok DELL 100")
                continue

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
✅ POSIZIONE APPROVATA

Asset: {symbol}
Azione: {trade["decision"]}
Capitale: ${amount:.2f}
Entry price: ${price:.2f}
Stop loss: {trade["stop_loss"] * 100:.1f}%
Take profit: {trade["take_profit"] * 100:.1f}%

Nota: per ora è simulata. Con Alpaca diventerà ordine paper.
""")

        elif text.startswith("/no"):
            parts = text.split()

            if len(parts) < 2:
                manda_telegram("Uso corretto: /no DELL")
                continue

            symbol = parts[1].upper()

            if symbol in pending:
                del pending[symbol]
                salva_pending(pending)
                manda_telegram(f"❌ Trade rifiutato per {symbol}")
            else:
                manda_telegram(f"Nessun trade in attesa per {symbol}")

        elif text.startswith("/positions"):
            if not posizioni:
                manda_telegram("Nessuna posizione aperta")
            else:
                msg = "📌 POSIZIONI APERTE:\n"
                for symbol, p in posizioni.items():
                    current = prezzo_attuale(symbol)

                    if current:
                        pnl_pct = ((current - p["entry_price"]) / p["entry_price"]) * 100
                        msg += f'\n{symbol} | {p["action"]} | ${p["amount"]:.2f} | Entry ${p["entry_price"]:.2f} | Ora ${current:.2f} | P/L {pnl_pct:.2f}%'
                    else:
                        msg += f'\n{symbol} | {p["action"]} | ${p["amount"]:.2f}'

                manda_telegram(msg)

        elif text.startswith("/close"):
            parts = text.split()

            if len(parts) < 2:
                manda_telegram("Uso corretto: /close DELL")
                continue

            symbol = parts[1].upper()

            if symbol in posizioni:
                del posizioni[symbol]
                salva_posizioni(posizioni)
                manda_telegram(f"🔒 Posizione chiusa manualmente: {symbol}")
            else:
                manda_telegram(f"Nessuna posizione aperta su {symbol}")

        elif text.startswith("/help"):
            manda_telegram("""
Comandi disponibili:

/add QQQ
/remove QQQ
/list
/report

/pending
/ok DELL 100
/no DELL

/positions
/close DELL

/help
""")

# ======================
# NEWS
# ======================

def estrai_news(ticker):
    news_items = ticker.news
    news_text = ""

    for item in news_items[:5]:
        title = "Titolo non disponibile"
        publisher = "Fonte sconosciuta"
        link = ""

        content = item.get("content") or {}

        if content:
            title = content.get("title") or title
            provider = content.get("provider") or {}
            publisher = provider.get("displayName") or publisher
            click_url = content.get("clickThroughUrl") or {}
            link = click_url.get("url") or ""
        else:
            title = item.get("title") or title
            publisher = item.get("publisher") or publisher
            link = item.get("link") or ""

        if publisher in TRUSTED_SOURCES:
            news_text += f"- {title}\n  Fonte: {publisher}\n  Link: {link}\n\n"

    if news_text == "":
        news_text = "Nessuna news rilevante da fonti affidabili."

    return news_text

# ======================
# CLAUDE
# ======================

def analisi_claude(symbol, dati, news_text):
    if not USE_CLAUDE or not ANTHROPIC_API_KEY:
        return ""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    prompt = f"""
Sei un assistente di analisi finanziaria.

Analizza l'asset {symbol} usando questi dati:

Prezzo: {dati["price"]}
Variazione: {dati["change_pct"]}%
EMA20: {dati["ema20"]}
EMA50: {dati["ema50"]}
RSI: {dati["rsi"]}
Volume: {dati["volume"]}
Rischio asset: {dati["risk"]}
Stop loss suggerito: {dati["stop_loss"] * 100}%
Take profit suggerito: {dati["take_profit"] * 100}%

News:
{news_text}

Scrivi un'analisi abbastanza lunga ma chiara.
Devi includere:
1. cosa sta succedendo
2. rischi principali
3. opportunità
4. se conviene BUY, HOLD o SELL
5. quanto capitale avrebbe senso usare, in modo prudente

Non promettere guadagni.
Rispondi in italiano.
"""

    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )

    return response.content[0].text.strip()

# ======================
# ANALISI
# ======================

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

    news_text = estrai_news(ticker)

    dati = {
        "price": round(price, 2),
        "change_pct": round(change_pct, 2),
        "ema20": round(ema20, 2),
        "ema50": round(ema50, 2),
        "rsi": round(rsi, 2),
        "volume": volume,
        "risk": config["risk"],
        "stop_loss": config["stop_loss"],
        "take_profit": config["take_profit"]
    }

    ai_text = analisi_claude(symbol, dati, news_text)

    return {
        "symbol": symbol,
        "name": config["name"],
        "decision": decision,
        "news": news_text,
        "ai": ai_text,
        **dati
    }

def aggiorna_pending(symbol, result):
    if result["decision"] == "HOLD":
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

def crea_report(tipo="controllo"):
    assets = tutti_gli_asset()
    messaggi_brevi = []
    report_completo = ""

    if tipo == "mattina":
        titolo = "🌅 REPORT MATTINA"
    elif tipo == "sera":
        titolo = "🌙 REPORT SERALE"
    elif tipo == "settimana":
        titolo = "📅 REPORT SETTIMANALE"
    elif tipo == "manuale":
        titolo = "📌 REPORT MANUALE"
    else:
        titolo = "📊 CONTROLLO MERCATO"

    report_completo += f"{titolo}\n\n"

    for symbol, config in assets.items():
        try:
            result = analizza_asset(symbol, config)

            if "error" in result:
                report_completo += f"\n⚠️ {symbol}: {result['error']}\n"
                continue

            aggiorna_pending(symbol, result)

            if tipo == "controllo":
                if result["decision"] != "HOLD":
                    messaggi_brevi.append(
                        f'{symbol}: {result["decision"]} | usa /ok {symbol} IMPORTO oppure /no {symbol}'
                    )
                continue

            report_completo += f"""
====================
📊 {result["symbol"]} - {result["name"]}

💰 Prezzo: ${result["price"]}
📉 Variazione: {result["change_pct"]}%

📈 EMA20: {result["ema20"]}
📈 EMA50: {result["ema50"]}
📊 RSI: {result["rsi"]}
📦 Volume: {result["volume"]}

⚠️ Rischio asset: {result["risk"]}
🛑 Stop loss suggerito: {result["stop_loss"] * 100:.1f}%
🎯 Take profit suggerito: {result["take_profit"] * 100:.1f}%

🤖 Decisione: {result["decision"]}
"""

            if result["decision"] != "HOLD":
                report_completo += f"""
✅ Per approvare:
 /ok {result["symbol"]} IMPORTO

❌ Per rifiutare:
 /no {result["symbol"]}
"""

            report_completo += f"""
📰 News:
{result["news"]}
"""

            if result["ai"]:
                report_completo += f"""
🧠 Analisi AI:
{result["ai"]}
"""

        except Exception as e:
            report_completo += f"\n⚠️ Errore su {symbol}: {e}\n"
            print(f"Errore su {symbol}: {e}")

    if tipo == "controllo":
        if messaggi_brevi:
            manda_telegram("\n".join(messaggi_brevi))
            print("Controllo inviato")
        else:
            print("Controllo: tutti HOLD, nessun messaggio")
    else:
        manda_telegram(report_completo)
        print(f"Report inviato: {tipo}")

def controllo_movimenti_veloci():
    assets = tutti_gli_asset()

    for symbol, config in assets.items():
        try:
            ticker = yf.Ticker(symbol)
            data = ticker.history(period="1d", interval="5m")

            if data.empty or len(data) < 2:
                continue

            last = float(data["Close"].iloc[-1])
            prev = float(data["Close"].iloc[-2])
            change = ((last - prev) / prev) * 100

            if abs(change) > 2:
                manda_telegram(f"⚡ Movimento forte su {symbol}: {change:.2f}% in 5 minuti")

        except Exception as e:
            print(f"Errore movimento veloce su {symbol}: {e}")

# ======================
# ROUTINE
# ======================

schedule.every().day.at("07:30").do(lambda: crea_report("mattina"))
schedule.every(90).minutes.do(lambda: crea_report("controllo"))
schedule.every(10).minutes.do(controllo_movimenti_veloci)
schedule.every(5).minutes.do(controlla_posizioni)
schedule.every().day.at("20:30").do(lambda: crea_report("sera"))
schedule.every().saturday.at("10:00").do(lambda: crea_report("settimana"))

print("Bot avviato... routine attiva.")

keep_alive()

while True:
    gestisci_comandi()
    schedule.run_pending()
    time.sleep(30)