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
# SAFETY CHECK
# =========================
if not EMAIL_FROM or not EMAIL_PASSWORD or not EMAIL_TO:
    print("Email credentials missing")
    sys.exit(1)


# =========================
# EMAIL FUNCTION
# =========================
def send_email(message):
    msg = MIMEText(message)
    msg["Subject"] = "Stock Strategy Alert"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASSWORD)
        server.send_message(msg)


# =========================
# STOCK SCANNER CLASS
# =========================
class StockScanner:

    def read_stocks(self):
        if not os.path.exists(CSV_FILE):
            raise FileNotFoundError(f"{CSV_FILE} not found in repo")

        df = pd.read_csv(CSV_FILE)

        if "Symbol" not in df.columns:
            raise ValueError("CSV must contain 'Symbol' column")

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

        last = df.iloc[-1]
        prev = df.iloc[-2]

        # V20 logic: price crossing above 20 MA
        if prev["Close"] < prev["MA20"] and last["Close"] > last["MA20"]:
            alerts.append(
                f"{symbol} | V20 ACTIVATED\n"
                f"Date: {last['Date'].date()}\n"
                f"Price: {round(last['Close'], 2)}"
            )

        return alerts

    def run(self):
        symbols = self.read_stocks()
        all_alerts = []

        for symbol in symbols:
            df = self.fetch_data(symbol)
            if df is None:
                continue

            all_alerts.extend(self.check_v20(df, symbol))

        if all_alerts:
            send_email("\n\n".join(all_alerts))
            print("Email sent successfully")
        else:
            print("No signals found")


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    scanner = StockScanner()
    scanner.run()
