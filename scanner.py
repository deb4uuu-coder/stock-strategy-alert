import pandas as pd
import yfinance as yf
import math
import smtplib
from email.message import EmailMessage
import os

# ================= SETTINGS =================
GREEN_MOVE_PERCENT = 20          # minimum up move
PRICE_MATCH_TOLERANCE = 3        # +3% tolerance
H45_DMA_DROP = 14                # 14% below 200 DMA
YEARS_OF_DATA = "5y"

# ================= LOAD STOCKS =================
def load_stocks():
    df = pd.read_csv("stocks_layout.csv", header=None)

    groups = {
        "V40": [],
        "V40_NEXT": [],
        "H45": []
    }

    # Column indexes: B=1, E=4, H=7
    for col, group in [(1, "V40"), (4, "V40_NEXT"), (7, "H45")]:
        for row in range(2, len(df)):
            symbol = df.iloc[row, col]
            if isinstance(symbol, str) and symbol.strip():
                groups[group].append(symbol.strip())

    return groups

# ================= DATA FETCH =================
def get_data(symbol):
    df = yf.download(symbol, period=YEARS_OF_DATA, interval="1d", progress=False)
    if df.empty or len(df) < 200:
        return None
    df.reset_index(inplace=True)
    return df

# ================= GREEN PATTERN LOGIC =================
def find_green_patterns(df):
    patterns = []
    start_idx = None

    for i in range(1, len(df)):
        if df["Close"][i] > df["Close"][i - 1]:
            if start_idx is None:
                start_idx = i - 1
        else:
            if start_idx is not None:
                evaluate_pattern(df, start_idx, i - 1, patterns)
                start_idx = None

    if start_idx is not None:
        evaluate_pattern(df, start_idx, len(df) - 1, patterns)

    return patterns

def evaluate_pattern(df, start, end, patterns):
    start_price = df["Close"][start]
    end_price = df["Close"][end]
    move_pct = ((end_price - start_price) / start_price) * 100

    if move_pct >= GREEN_MOVE_PERCENT:
        patterns.append({
            "start_date": df["Date"][start].date(),
            "end_date": df["Date"][end].date(),
            "start_price": start_price,
            "move_pct": move_pct
        })

# ================= V40 / V40 NEXT =================
def process_v40(symbol):
    df = get_data(symbol)
    if df is None:
        return []

    patterns = find_green_patterns(df)
    cmp_price = df["Close"].iloc[-1]

    alerts = []
    for p in patterns:
        diff_pct = ((cmp_price - p["start_price"]) / p["start_price"]) * 100
        if cmp_price <= p["start_price"] or diff_pct <= PRICE_MATCH_TOLERANCE:
            alerts.append(
                f"BUY ALERT (V40 / V40 NEXT)\n"
                f"Stock: {symbol}\n"
                f"CMP: {round(cmp_price,2)}\n"
                f"Pattern Start: {p['start_date']}\n"
                f"Pattern End: {p['end_date']}\n"
                f"Pattern Move: {round(p['move_pct'],2)}%\n"
                f"Pattern Start Price: {round(p['start_price'],2)}\n"
                f"Difference: {round(diff_pct,2)}%"
            )
    return alerts

# ================= H45 =================
def process_h45(symbol):
    df = get_data(symbol)
    if df is None:
        return None

    df["DMA200"] = df["Close"].rolling(200).mean()
    cmp_price = df["Close"].iloc[-1]
    dma200 = df["DMA200"].iloc[-1]

    if math.isnan(dma200):
        return None

    drop_pct = ((dma200 - cmp_price) / dma200) * 100

    if drop_pct >= H45_DMA_DROP:
        return (
            f"BUY ALERT (H45)\n"
            f"Stock: {symbol}\n"
            f"CMP: {round(cmp_price,2)}\n"
            f"200 DMA: {round(dma200,2)}\n"
            f"Down from DMA: {round(drop_pct,2)}%"
        )
    return None

# ================= EMAIL =================
def send_email_alert(message):
    email_user = os.getenv("EMAIL_USER")
    email_pass = os.getenv("EMAIL_PASS")

    if not email_user or not email_pass:
        print("Email credentials missing")
        return

    msg = EmailMessage()
    msg["Subject"] = "📊 Stock Buy Alert"
    msg["From"] = email_user
    msg["To"] = email_user
    msg.set_content(message)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(email_user, email_pass)
        server.send_message(msg)

# ================= MAIN =================
def main():
    groups = load_stocks()
    all_alerts = []

    for symbol in groups["V40"]:
        all_alerts.extend(process_v40(symbol))

    for symbol in groups["V40_NEXT"]:
        all_alerts.extend(process_v40(symbol))

    for symbol in groups["H45"]:
        alert = process_h45(symbol)
        if alert:
            all_alerts.append(alert)

    if all_alerts:
        full_message = "\n\n".join(all_alerts)
        print(full_message)
        send_email_alert(full_message)
    else:
        print("No alerts today.")

if __name__ == "__main__":
    main()
