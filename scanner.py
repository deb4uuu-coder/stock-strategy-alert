import pandas as pd
import yfinance as yf
import smtplib
import os
from email.mime.text import MIMEText
from datetime import datetime

CSV_FILE = "stocks_layout.csv"

EMAIL_FROM = "deb.4uuu@gmail.com"
EMAIL_TO = "deb.4uuu@gmail.com"
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

GITHUB_EVENT = os.getenv("GITHUB_EVENT_NAME", "")


def is_weekend():
    today = datetime.now().weekday()
    return today >= 5   # 5 = Saturday, 6 = Sunday


def allow_email():
    # Manual run → always allow
    if GITHUB_EVENT == "workflow_dispatch":
        return True

    # Scheduled run → block weekends
    if GITHUB_EVENT == "schedule" and is_weekend():
        return False

    return True


def send_email(message):
    if not allow_email():
        print("Weekend detected — email skipped.")
        return

    msg = MIMEText(message)
    msg["Subject"] = "📈 Stock Strategy Alert"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)


def download_data(symbol):
    try:
        df = yf.download(symbol, period="4y", interval="1d", progress=False)
        if df.empty:
            return None
        return df.dropna()
    except Exception:
        return None


def process_v40(symbol):
    alerts = []
    df = download_data(symbol)
    if df is None:
        return alerts

    if len(df) > 200:
        alerts.append(f"V40 watch: {symbol}")

    return alerts


def read_symbols(col_index):
    df = pd.read_csv(CSV_FILE)
    symbols = []

    for i in range(2, len(df)):
        val = str(df.iloc[i, col_index]).strip()
        if val and val != "nan":
            symbols.append(val)

    return symbols


def main():
    all_alerts = []

    v40 = read_symbols(1)
    h45 = read_symbols(7)

    for s in v40:
        all_alerts.extend(process_v40(s))

    for s in h45:
        all_alerts.append(f"H45 watch: {s}")

    if all_alerts:
        send_email("\n".join(all_alerts))
        print("Email sent")
    else:
        print("No alerts")


if __name__ == "__main__":
    main()
