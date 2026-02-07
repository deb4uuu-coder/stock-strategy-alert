import pandas as pd
import yfinance as yf
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import os
import sys
import pytz

CSV_FILE = "stocks_layout.csv"

IST = pytz.timezone("Asia/Kolkata")

V20_MIN_MOVE = 20          # 20% upmove
V20_NEAR_DIFF = 3          # 3% near pattern
H45_DMA_DIFF = 14          # 14% below 200 DMA


# -------------------------------------------------------
# EMAIL
# -------------------------------------------------------
def send_email(subject, body):
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")
    password = os.getenv("EMAIL_PASSWORD")

    if not email_from or not email_to or not password:
        print("Email credentials missing")
        sys.exit(1)

    msg = MIMEText(body)
    msg["From"] = email_from
    msg["To"] = email_to
    msg["Subject"] = subject

    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.starttls()
    server.login(email_from, password)
    server.send_message(msg)
    server.quit()


# -------------------------------------------------------
# READ CSV (YOUR FORMAT)
# -------------------------------------------------------
def read_stocks():
    df = pd.read_csv(CSV_FILE)

    stocks = {
        "V40": df.iloc[:, 0].dropna().tolist(),
        "V40NEXT": df.iloc[:, 1].dropna().tolist(),
        "H45": df.iloc[:, 2].dropna().tolist(),
    }

    # Remove numeric rows like 1,2,3
    for k in stocks:
        stocks[k] = [s for s in stocks[k] if isinstance(s, str) and ".NS" in s]

    return stocks


# -------------------------------------------------------
# FIND V20 PATTERNS (SAFE LOGIC)
# -------------------------------------------------------
def find_v20_patterns(symbol):
    df = yf.download(symbol, period="4y", progress=False)

    if df.empty or len(df) < 50:
        return []

    patterns = []
    i = 0

    while i < len(df) - 1:
        if df.iloc[i]["Close"] <= df.iloc[i]["Open"]:
            i += 1
            continue

        start_price = float(df.iloc[i]["Open"])
        start_date = df.index[i].date()
        high = start_price
        j = i

        while j < len(df) and df.iloc[j]["Close"] > df.iloc[j]["Open"]:
            high = max(high, float(df.iloc[j]["Close"]))
            j += 1

        move = ((high - start_price) / start_price) * 100

        if move >= V20_MIN_MOVE:
            patterns.append({
                "start_date": start_date,
                "start_price": round(start_price, 2),
                "end_price": round(high, 2),
                "move": round(move, 2),
            })

        i = j

    return patterns


# -------------------------------------------------------
# CHECK H45 CONDITION
# -------------------------------------------------------
def check_h45(symbol):
    df = yf.download(symbol, period="1y", progress=False)

    if df.empty or len(df) < 200:
        return None

    current = float(df.iloc[-1]["Close"])
    dma200 = df["Close"].rolling(200).mean().iloc[-1]

    diff = ((dma200 - current) / dma200) * 100

    if diff >= H45_DMA_DIFF:
        return round(diff, 2), round(current, 2), round(dma200, 2)

    return None


# -------------------------------------------------------
# MAIN RUN
# -------------------------------------------------------
def run(manual=False):
    now = datetime.now(IST)

    if not manual and now.weekday() >= 5:
        print("Weekend – no automatic email")
        return

    stocks = read_stocks()
    alerts = []

    # -------- V40 & V40 NEXT (V20 LOGIC)
    for group in ["V40", "V40NEXT"]:
        for s in stocks[group]:
            patterns = find_v20_patterns(s)
            if not patterns:
                continue

            df = yf.download(s, period="5d", progress=False)
            current = float(df.iloc[-1]["Close"])

            for p in patterns:
                diff = abs((current - p["start_price"]) / p["start_price"]) * 100

                if diff <= V20_NEAR_DIFF:
                    alerts.append(
                        f"V20 ACTIVATED ({group})\n"
                        f"Stock: {s}\n"
                        f"Pattern Start: {p['start_date']} @ {p['start_price']}\n"
                        f"Pattern End Price: {p['end_price']}\n"
                        f"Upmove: {p['move']}%\n"
                        f"Current Price: {round(current,2)}\n"
                        f"Difference: {round(diff,2)}%\n"
                    )

    # -------- H45 LOGIC
    for s in stocks["H45"]:
        result = check_h45(s)
        if result:
            diff, price, dma = result
            alerts.append(
                f"H45 ACTIVATED\n"
                f"Stock: {s}\n"
                f"Current Price: {price}\n"
                f"200 DMA: {dma}\n"
                f"Below DMA: {diff}%\n"
            )

    if alerts:
        subject = f"Stock Strategy Report – {now.strftime('%d %b %Y')}"
        body = "\n\n".join(alerts)
        send_email(subject, body)
        print(f"Email sent with {len(alerts)} alerts")
    else:
        print("No alerts today")


# -------------------------------------------------------
# ENTRY
# -------------------------------------------------------
if __name__ == "__main__":
    manual_run = "--manual" in sys.argv
    run(manual=manual_run)
