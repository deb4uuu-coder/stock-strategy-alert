import os
import sys
import pandas as pd
import yfinance as yf
import smtplib
from email.mime.text import MIMEText
from datetime import datetime


# =========================
# CONFIG
# =========================
CSV_FILE = "stocks_layout.csv"

EMAIL_FROM = os.getenv("EMAIL_FROM")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
EMAIL_TO = os.getenv("EMAIL_TO")


# =========================
# EMAIL CHECK
# =========================
if not EMAIL_FROM or not EMAIL_PASSWORD or not EMAIL_TO:
    print("Email credentials missing")
    sys.exit(1)


# =========================
# EMAIL FUNCTION
# =========================
def send_email(body):
    msg = MIMEText(body)
    msg["Subject"] = "Stock Strategy Alert"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)


# =========================
# SCANNER
# =========================
class StockScanner:

    def read_stocks(self):
        if not os.path.exists(CSV_FILE):
            raise FileNotFoundError(f"{CSV_FILE} not found")

        df = pd.read_csv(CSV_FILE)

        if "Symbol" not in df.columns:
            raise ValueError("CSV must contain column named 'Symbol'")

        return df["Symbol"].dropna().unique().tolist()

    def fetch_data(self, symbol):
        df = yf.download(symbol, period="6mo", interval="1d", progress=False)

        if df.empty:
            return None

        df.reset_index(inplace=True)
        return df

    def check_v20(self, df, symbol):
        alerts = []

        if len(df) < 20:
            return alerts

        df["MA20"] = df["Close"].rolling(20).mean()

        prev = df.iloc[-2]
        curr = df.iloc[-1]

        if prev["Close"] < prev["MA20"] and curr["Close"] > curr["MA20"]:
            alerts.append(
                f"{symbol}\n"
                f"V20 ACTIVATED\n"
                f"Date: {curr['Date'].date()}\n"
                f"Price: {round(curr['Close'], 2)}"
            )

        return alerts

    def run(self):
        symbols = self.read_stocks()
        alerts = []

        for s in symbols:
            df = self.fetch_data(s)
            if df is None:
                continue
            alerts.extend(self.check_v20(df, s))

        if alerts:
            send_email("\n\n".join(alerts))
            print("Email sent")
        else:
            print("No signals found")


# =========================
# MAIN
# =========================
if __name__ == "__main__":
    scanner = StockScanner()
    scanner.run()
