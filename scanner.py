import os
import pandas as pd
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from datetime import datetime
from zoneinfo import ZoneInfo

# ================= CONFIG =================

V20_MIN_MOVE = 0.20          # 20% up move
V20_LOOKBACK_YEARS = 4
V20_PRICE_TOLERANCE = 0.03  # 3%

H45_MA_DAYS = 200
H45_DROP_PCT = 0.14         # 14%

CSV_FILE = "stocks_layout.csv"

# GitHub event type
GITHUB_EVENT = os.getenv("GITHUB_EVENT_NAME", "")

# Email env
EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")

if not all([EMAIL_FROM, EMAIL_PASSWORD, EMAIL_TO]):
    raise ValueError("Email environment variables not set")

# ================= TIME HELPERS =================

def is_weekend_ist():
    ist_now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return ist_now.weekday() >= 5


def should_send_email():
    # Manual run → always send
    if GITHUB_EVENT == "workflow_dispatch":
        print("Manual run detected → email allowed")
        return True

    # Scheduled run → block weekends
    if GITHUB_EVENT == "schedule" and is_weekend_ist():
        print("Weekend scheduled run → email blocked")
        return False

    return True


# ================= EMAIL =================

def send_email(body):
    msg = MIMEText(body)
    msg["Subject"] = "📈 Stock Strategy Alert"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)

    print("Email sent successfully")


# ================= DATA =================

def load_symbols():
    df = pd.read_csv(CSV_FILE)

    return {
        "V40": df["V40"].dropna().tolist(),
        "V40_NEXT": df["V40_NEXT"].dropna().tolist(),
        "H45": df["H45"].dropna().tolist(),
    }


def fetch_data(symbol):
    df = yf.download(
        symbol,
        period=f"{V20_LOOKBACK_YEARS}y",
        interval="1d",
        progress=False,
        auto_adjust=True,
    )

    if df.empty:
        return None

    df = df.reset_index()
    return df


# ================= V20 / V40 LOGIC =================

def find_v20_patterns(df):
    patterns = []
    closes = df["Close"].values
    dates = df["Date"].values

    for i in range(len(closes)):
        start_price = closes[i]

        for j in range(i + 1, len(closes)):
            move = (closes[j] - start_price) / start_price

            if move >= V20_MIN_MOVE:
                patterns.append({
                    "start_price": start_price,
                    "end_price": closes[j],
                    "start_date": dates[i],
                    "end_date": dates[j],
                })
                break

    return patterns


def check_v20_signal(symbol, group):
    alerts = []
    df = fetch_data(symbol)
    if df is None:
        return alerts

    current_price = float(df["Close"].iloc[-1])
    patterns = find_v20_patterns(df)

    for p in patterns:
        diff = abs(current_price - p["start_price"]) / p["start_price"]

        if diff <= V20_PRICE_TOLERANCE:
            alerts.append(
                f"""🟢 {symbol}
Group: {group}
Strategy: V20 Activated
Pattern Start: {p['start_date'].date()}
Pattern End: {p['end_date'].date()}
Pattern Price: {p['start_price']:.2f}
Current Price: {current_price:.2f}
Difference: {diff*100:.2f}%"""
            )

    return alerts


# ================= H45 LOGIC =================

def check_h45_signal(symbol):
    alerts = []
    df = fetch_data(symbol)
    if df is None or len(df) < H45_MA_DAYS:
        return alerts

    df["MA200"] = df["Close"].rolling(H45_MA_DAYS).mean()

    current_price = float(df["Close"].iloc[-1])
    ma200 = float(df["MA200"].iloc[-1])

    if pd.isna(ma200):
        return alerts

    drop = (ma200 - current_price) / ma200

    if drop >= H45_DROP_PCT:
        alerts.append(
            f"""🔵 {symbol}
Group: H45
Strategy: H45 Activated
200 DMA: {ma200:.2f}
Current Price: {current_price:.2f}
Drop from MA: {drop*100:.2f}%"""
        )

    return alerts


# ================= MAIN =================

def main():
    symbols = load_symbols()
    all_alerts = []

    for s in symbols["V40"]:
        all_alerts.extend(check_v20_signal(s, "V40"))

    for s in symbols["V40_NEXT"]:
        all_alerts.extend(check_v20_signal(s, "V40 NEXT"))

    for s in symbols["H45"]:
        all_alerts.extend(check_h45_signal(s))

    if not all_alerts:
        print("No signals found")
        return

    report = "\n\n".join(all_alerts)

    if should_send_email():
        send_email(report)
    else:
        print("Email suppressed by weekend rule")


if __name__ == "__main__":
    main()
