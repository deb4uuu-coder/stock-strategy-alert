import pandas as pd
import yfinance as yf
import smtplib
import os
from datetime import datetime
from email.mime.text import MIMEText

# ================= CONFIG =================
EMAIL_FROM = os.environ["EMAIL_FROM"]
EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
EMAIL_TO = os.environ["EMAIL_TO"]

CSV_FILE = "stocks_layout.csv"

V20_MIN_MOVE = 0.20      # 20%
PRICE_NEAR_PCT = 0.03    # 3%
LOOKBACK_DAYS = 120
# =========================================


def is_weekend():
    return datetime.today().weekday() >= 5


def send_email(body):
    msg = MIMEText(body)
    msg["Subject"] = "📊 Stock Strategy Alert"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)


def load_stocks(col):
    df = pd.read_csv(CSV_FILE)
    stocks = df[col].dropna().astype(str).tolist()
    return stocks


def get_data(symbol):
    df = yf.download(symbol, period="6mo", interval="1d", progress=False)
    if df.empty:
        return None
    df = df.reset_index()
    df["Close"] = df["Close"].astype(float)
    return df


def find_v20_patterns(df):
    patterns = []
    close = df["Close"]

    for i in range(10, len(df)):
        start_price = close.iloc[i - 10]
        end_price = close.iloc[i]
        move = (end_price - start_price) / start_price

        if move >= V20_MIN_MOVE:
            patterns.append({
                "start_date": df["Date"].iloc[i - 10].date(),
                "end_date": df["Date"].iloc[i].date(),
                "start_price": round(start_price, 2),
                "end_price": round(end_price, 2)
            })

    return patterns


def check_signal(symbol, group):
    df = get_data(symbol)
    if df is None:
        return []

    alerts = []
    close = df["Close"]
    current_price = close.iloc[-1]

    patterns = find_v20_patterns(df)

    for p in patterns:
        pattern_price = p["end_price"]
        diff_pct = abs(current_price - pattern_price) / pattern_price

        if diff_pct <= PRICE_NEAR_PCT:
            alerts.append(
                f"""
Stock : {symbol}
Group : {group}
Pattern : V20 Activated
Pattern Start : {p['start_date']}
Pattern End   : {p['end_date']}
Pattern Price : {pattern_price}
Current Price : {round(current_price,2)}
Status : Price near / matching pattern
------------------------------------
"""
            )

    return alerts


def main():
    manual_run = os.environ.get("MANUAL_RUN", "false").lower() == "true"

    if not manual_run and is_weekend():
        print("Weekend – no automatic email")
        return

    alerts = []

    for s in load_stocks("V40"):
        alerts.extend(check_signal(s, "V40"))

    for s in load_stocks("H45"):
        alerts.extend(check_signal(s, "H45"))

    if alerts:
        send_email("\n".join(alerts))
        print("Email sent")
    else:
        print("No signals today")


if __name__ == "__main__":
    main()
