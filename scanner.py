import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import sys
import pytz

# ================== CONFIG ==================

V20_LOOKBACK_DAYS = 365 * 4
V20_MIN_GAIN = 20
V20_TOLERANCE = 3        # ±3%

H45_DROP_PCT = 14        # 14%
H45_SMA_DAYS = 200

IST = pytz.timezone("Asia/Kolkata")
GITHUB_EVENT = os.getenv("GITHUB_EVENT_NAME", "")

# ================== EMAIL RULE ==================

def should_send_email():
    now_ist = datetime.now(IST)

    if GITHUB_EVENT == "workflow_dispatch":
        print("Manual run → email allowed")
        return True

    if GITHUB_EVENT == "schedule" and now_ist.weekday() >= 5:
        print("Weekend auto run → email blocked")
        return False

    return True

# ================== SCANNER ==================

class V20Scanner:
    def __init__(self, excel_file, email_to, email_from, email_password):
        self.excel_file = excel_file
        self.email_to = email_to
        self.email_from = email_from
        self.email_password = email_password
        self.alerts = []

    def read_stocks(self):
        xls = pd.ExcelFile(self.excel_file)
        stocks = {}

        for sheet in ["v40", "v40next", "v200"]:
            if sheet in xls.sheet_names:
                df = pd.read_excel(xls, sheet_name=sheet)
                stocks[sheet] = df.iloc[:, 1].dropna().tolist()

        return stocks

    # ================== V20 PATTERN ==================

    def find_v20_patterns(self, symbol):
        end = datetime.now()
        start = end - timedelta(days=V20_LOOKBACK_DAYS)

        df = yf.Ticker(symbol).history(start=start, end=end)
        if df.empty:
            return []

        patterns = []
        i = 0

        while i < len(df):
            start_price = df.iloc[i]["Open"]
            start_date = df.index[i]

            j = i
            high = start_price

            while j < len(df) and df.iloc[j]["Close"] > df.iloc[j]["Open"]:
                high = max(high, df.iloc[j]["Close"])
                j += 1

            gain = ((high - start_price) / start_price) * 100

            if gain >= V20_MIN_GAIN:
                patterns.append({
                    "start_price": round(start_price, 2),
                    "start_date": start_date.strftime("%Y-%m-%d"),
                    "end_date": df.index[j - 1].strftime("%Y-%m-%d"),
                    "gain": round(gain, 2)
                })

            i = max(j, i + 1)

        return patterns

    # ================== CURRENT PRICE ==================

    def current_price_and_sma(self, symbol):
        df = yf.Ticker(symbol).history(period="220d")
        if df.empty:
            return None, None

        price = round(df.iloc[-1]["Close"], 2)
        sma = df["Close"].rolling(H45_SMA_DAYS).mean().iloc[-1]

        return price, round(sma, 2) if not pd.isna(sma) else None

    # ================== CHECK LOGIC ==================

    def check_v20(self, symbol, group):
        patterns = self.find_v20_patterns(symbol)
        price, _ = self.current_price_and_sma(symbol)

        if not patterns or price is None:
            return

        for p in patterns:
            diff = abs(price - p["start_price"]) / p["start_price"] * 100

            if diff <= V20_TOLERANCE:
                self.alerts.append(
                    f"""🟢 {symbol}
Group: {group.upper()}
Strategy: V20 ACTIVATED
Pattern: {p['start_date']} → {p['end_date']}
Pattern Price: {p['start_price']}
Current Price: {price}
Difference: {round(diff,2)}%
Gain: {p['gain']}%"""
                )

    def check_h45(self, symbol):
        price, sma = self.current_price_and_sma(symbol)
        if price is None or sma is None:
            return

        drop = (sma - price) / sma * 100

        if drop >= H45_DROP_PCT:
            self.alerts.append(
                f"""🔵 {symbol}
Group: H45
Strategy: H45 ACTIVATED
200 DMA: {sma}
Current Price: {price}
Below MA: {round(drop,2)}%"""
            )

    # ================== EMAIL ==================

    def send_email(self):
        if not self.alerts:
            print("No alerts generated")
            return

        if not should_send_email():
            print("Email suppressed by rule")
            return

        msg = MIMEMultipart()
        msg["From"] = self.email_from
        msg["To"] = self.email_to
        msg["Subject"] = f"Stock Strategy Alert – {datetime.now(IST).date()}"

        body = "\n\n".join(self.alerts)
        msg.attach(MIMEText(body, "plain"))

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(self.email_from, self.email_password)
        server.send_message(msg)
        server.quit()

        print("Email sent successfully")

    # ================== RUN ==================

    def run(self):
        stocks = self.read_stocks()

        for s in stocks.get("v40", []):
            self.check_v20(s, "V40")

        for s in stocks.get("v40next", []):
            self.check_v20(s, "V40 NEXT")

        for s in stocks.get("v200", []):
            self.check_h45(s)

        self.send_email()

# ================== MAIN ==================

if __name__ == "__main__":
    EMAIL_FROM = os.getenv("EMAIL_FROM")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
    EMAIL_TO = "deb.4uuu@gmail.com"

    if not EMAIL_FROM or not EMAIL_PASSWORD:
        print("Email credentials missing")
        sys.exit(1)

    scanner = V20Scanner("stocks.xlsx", EMAIL_TO, EMAIL_FROM, EMAIL_PASSWORD)
    scanner.run()
