import pandas as pd
import yfinance as yf
import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime
from zoneinfo import ZoneInfo

# ================= CONFIG =================

CSV_FILE = "stocks_layout.csv"

EMAIL_FROM = "deb.4uuu@gmail.com"
EMAIL_TO = "deb.4uuu@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

PRICE_TOLERANCE = 0.03
V20_MIN_MOVE = 0.20
H45_DMA_DROP = 0.14
LOOKBACK_YEARS = 4

GITHUB_EVENT = os.getenv("GITHUB_EVENT_NAME", "")
IST = ZoneInfo("Asia/Kolkata")

# =========================================


def is_weekend_ist():
    return datetime.now(IST).weekday() >= 5


def allow_email():
    if GITHUB_EVENT == "workflow_dispatch":
        return True
    if GITHUB_EVENT == "schedule" and is_weekend_ist():
        return False
    return True


def send_email(body):
    if not allow_email():
        print("Weekend detected (IST) — email skipped.")
        return

    msg = MIMEText(body)
    msg["Subject"] = "📈 Stock Strategy Buy Alert"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)


def download_data(symbol):
    try:
        df = yf.download(
            symbol,
            period=f"{LOOKBACK_YEARS}y",
            interval="1d",
            progress=False
        )
        if df.empty or "Close" not in df.columns:
            return None

        df = df.dropna()
        df["Close"] = df["Close"].astype(float)  # 🔑 FIX
        return df

    except Exception:
        return None


# ================= V20 / V40 LOGIC =================

def find_v20_patterns(df):
    patterns = []
    closes = df["Close"].values  # numpy array (fast + safe)
    dates = df.index

    for i in range(len(closes) - 1):
        start_price = closes[i]
        start_date = dates[i]

        for j in range(i + 1, len(closes)):
            move = (closes[j] - start_price) / start_price

            if move >= V20_MIN_MOVE:
                patterns.append({
                    "start_date": start_date,
                    "end_date": dates[j],
                    "start_price": start_price,
                    "end_price": closes[j],
                    "move_pct": move * 100
                })
                break

    return patterns


def check_v20_signal(symbol, group_name):
    df = download_data(symbol)
    if df is None or len(df) < 300:
        return []

    current_price = float(df["Close"].iloc[-1])
    patterns = find_v20_patterns(df)

    alerts = []

    for p in patterns:
        diff_pct = (current_price - p["start_price"]) / p["start_price"]

        if abs(diff_pct) <= PRICE_TOLERANCE:
            alerts.append(
                f"🟢 BUY ALERT – {group_name} ACTIVATED\n\n"
                f"Stock: {symbol}\n"
                f"Strategy: V20 (20% Up-Move Retracement)\n\n"
                f"Pattern Used:\n"
                f"• Start Date: {p['start_date'].date()}\n"
                f"• End Date: {p['end_date'].date()}\n"
                f"• Start Price: ₹{p['start_price']:.2f}\n"
                f"• End Price: ₹{p['end_price']:.2f}\n"
                f"• Pattern Move: +{p['move_pct']:.1f}%\n\n"
                f"Current Status:\n"
                f"• Current Price: ₹{current_price:.2f}\n"
                f"• Distance from Pattern Start: {diff_pct*100:.2f}%\n\n"
                f"Reason:\n"
                f"Price is near or matching historical pattern start price\n"
                f"{'-'*50}\n"
            )
            break

    return alerts


# ================= H45 LOGIC =================

def check_h45_signal(symbol):
    df = download_data(symbol)
    if df is None or len(df) < 220:
        return []

    df["DMA200"] = df["Close"].rolling(200).mean()

    current_price = float(df["Close"].iloc[-1])
    dma200 = df["DMA200"].iloc[-1]

    if pd.isna(dma200):
        return []

    drop_pct = (current_price - dma200) / dma200

    if drop_pct <= -H45_DMA_DROP:
        return [
            f"🟣 BUY ALERT – H45 ACTIVATED\n\n"
            f"Stock: {symbol}\n"
            f"Strategy: Mean Reversion (200 DMA)\n\n"
            f"Current Status:\n"
            f"• Current Price: ₹{current_price:.2f}\n"
            f"• 200 DMA: ₹{dma200:.2f}\n"
            f"• Distance from 200 DMA: {drop_pct*100:.2f}%\n\n"
            f"Reason:\n"
            f"Stock is trading ≥14% below 200-day moving average\n"
            f"{'-'*50}\n"
        ]

    return []


# ================= UTIL =================

def read_symbols(col_index):
    df = pd.read_csv(CSV_FILE)
    symbols = []

    for i in range(2, len(df)):
        val = str(df.iloc[i, col_index]).strip()
        if val and val != "nan":
            symbols.append(val)

    return symbols


# ================= MAIN =================

def main():
    alerts = []

    v40_symbols = read_symbols(1)
    v40_next_symbols = read_symbols(4)
    h45_symbols = read_symbols(7)

    for s in v40_symbols:
        alerts.extend(check_v20_signal(s, "V40"))

    for s in v40_next_symbols:
        alerts.extend(check_v20_signal(s, "V40 NEXT"))

    for s in h45_symbols:
        alerts.extend(check_h45_signal(s))

    if alerts:
        send_email("\n".join(alerts))
        print("Buy alerts sent")
    else:
        print("No strategy triggered today")


if __name__ == "__main__":
    main()
