import pandas as pd
import yfinance as yf
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
import os
import sys
import pytz

# ================= CONFIG =================
# CSV file can be set via environment variable or defaults to stocks_layout.csv
CSV_FILE = os.getenv("STOCKS_CSV_FILE", "stocks_layout.csv")

IST = pytz.timezone("Asia/Kolkata")

V20_MIN_MOVE = 20      # 20% upmove
V20_NEAR_DIFF = 3      # 3% near pattern
H45_DMA_DIFF = 14      # 14% below 200 DMA
# ==========================================


# ---------------- EMAIL -------------------
def send_email(subject, body):
    """Send email alert. Returns True if successful, False otherwise."""
    email_from = os.getenv("EMAIL_FROM")
    email_to = os.getenv("EMAIL_TO")
    password = os.getenv("EMAIL_PASSWORD")

    if not email_from or not email_to or not password:
        print("\n⚠️  Email credentials not configured")
        print("Set EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD environment variables to enable email")
        return False

    try:
        msg = MIMEText(body)
        msg["From"] = email_from
        msg["To"] = email_to
        msg["Subject"] = subject

        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.starttls()
        server.login(email_from, password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        print(f"\n❌ Email send failed: {e}")
        return False


# ---------------- UTIL -------------------
def clean_yf_df(df):
    """Flatten yfinance dataframe safely"""
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    # Reset index to make date-based access easier
    df = df.reset_index(drop=False)
    return df


# ---------------- READ CSV ----------------
def read_stocks():
    """Read stock symbols from CSV file and validate format."""
    if not os.path.exists(CSV_FILE):
        print(f"\n❌ ERROR: CSV file not found!")
        print(f"   Looking for: {CSV_FILE}")
        print(f"   Current directory: {os.getcwd()}")
        print(f"\n   Files in current directory:")
        for f in os.listdir('.'):
            if f.endswith('.csv') or f.endswith('.xlsx'):
                print(f"   - {f}")
        sys.exit(1)
    
    print(f"✓ Reading stocks from: {CSV_FILE}")
    
    try:
        df = pd.read_csv(CSV_FILE)
    except Exception as e:
        print(f"\n❌ Error reading CSV file: {e}")
        sys.exit(1)

    stocks = {
        "V40": df.iloc[:, 0].dropna().tolist(),
        "V40NEXT": df.iloc[:, 1].dropna().tolist(),
        "H45": df.iloc[:, 2].dropna().tolist(),
    }

    for k in stocks:
        stocks[k] = [
            s.strip()
            for s in stocks[k]
            if isinstance(s, str) and s.endswith(".NS")
        ]
    
    print(f"  - V40: {len(stocks['V40'])} stocks")
    print(f"  - V40NEXT: {len(stocks['V40NEXT'])} stocks")
    print(f"  - H45: {len(stocks['H45'])} stocks")

    return stocks


# ------------- V20 PATTERN ----------------
def find_v20_patterns(symbol):
    """
    Find V20 patterns (consecutive green candles with 20%+ move).
    Returns list of patterns with start date, prices, and move percentage.
    """
    try:
        df = yf.download(symbol, period="4y", progress=False)
        if df.empty:
            return []

        df = clean_yf_df(df)

        if len(df) < 50:
            return []

        patterns = []
        i = 0

        while i < len(df) - 1:
            # Use iloc for safe access
            open_p = float(df.iloc[i]["Open"])
            close_p = float(df.iloc[i]["Close"])

            # Must be green candle
            if close_p <= open_p:
                i += 1
                continue

            start_price = open_p
            start_date = df.iloc[i]["Date"] if "Date" in df.columns else df.index[i]
            if hasattr(start_date, 'date'):
                start_date = start_date.date()
            
            high = close_p
            j = i + 1

            # Count consecutive green candles
            while j < len(df):
                o = float(df.iloc[j]["Open"])
                c = float(df.iloc[j]["Close"])

                if c <= o:  # Red candle, stop
                    break

                high = max(high, c)
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
    
    except Exception as e:
        print(f"  ⚠️  Error processing {symbol}: {e}")
        return []


# ------------- H45 LOGIC ------------------
def check_h45(symbol):
    """
    Check if stock is 14%+ below 200 DMA (H45 pattern).
    Returns (diff%, current_price, 200_dma) or None.
    """
    try:
        df = yf.download(symbol, period="1y", progress=False)
        if df.empty:
            return None

        df = clean_yf_df(df)

        if len(df) < 200:
            return None

        # Use iloc for safe access
        current = float(df["Close"].iloc[-1])
        dma200 = float(df["Close"].rolling(200).mean().iloc[-1])

        diff = ((dma200 - current) / dma200) * 100

        if diff >= H45_DMA_DIFF:
            return round(diff, 2), round(current, 2), round(dma200, 2)

        return None
    
    except Exception as e:
        print(f"  ⚠️  Error processing {symbol}: {e}")
        return None


# ---------------- RUN ---------------------
def run(manual):
    """Main scanner logic - runs on all weekdays and weekends."""
    now = datetime.now(IST)

    print(f"\n{'='*60}")
    print(f"Stock Scanner - {now.strftime('%d %b %Y %H:%M:%S IST')}")
    print(f"Run mode: {'Manual' if manual else 'Automatic'}")
    print(f"{'='*60}\n")

    stocks = read_stocks()
    alerts = []

    # -------- V40 & V40 NEXT (V20 Pattern Detection)
    print(f"\n{'='*60}")
    print(f"Scanning V40 and V40NEXT stocks for V20 patterns...")
    print(f"{'='*60}")
    
    for group in ["V40", "V40NEXT"]:
        for s in stocks[group]:
            try:
                patterns = find_v20_patterns(s)
                if not patterns:
                    continue

                # Get current price
                df = yf.download(s, period="5d", progress=False)
                df = clean_yf_df(df)

                if df.empty:
                    continue

                current = float(df["Close"].iloc[-1])

                # Check if current price is near any pattern start
                for p in patterns:
                    diff = abs((current - p["start_price"]) / p["start_price"]) * 100

                    if diff <= V20_NEAR_DIFF:
                        alerts.append(
                            f"V20 ACTIVATED ({group})\n"
                            f"Stock: {s}\n"
                            f"Pattern Start: {p['start_date']} @ ₹{p['start_price']}\n"
                            f"Pattern End Price: ₹{p['end_price']}\n"
                            f"Upmove: {p['move']}%\n"
                            f"Current Price: ₹{round(current, 2)}\n"
                            f"Difference: {round(diff, 2)}%\n"
                        )
                        print(f"  ✓ {s} - V20 Pattern Alert!")
            
            except Exception as e:
                print(f"  ⚠️  Error scanning {s}: {e}")

    # -------- H45 (Below 200 DMA)
    print(f"\n{'='*60}")
    print(f"Scanning H45 stocks for 200 DMA patterns...")
    print(f"{'='*60}")
    
    for s in stocks["H45"]:
        try:
            result = check_h45(s)
            if result:
                diff, price, dma = result
                alerts.append(
                    f"H45 ACTIVATED\n"
                    f"Stock: {s}\n"
                    f"Current Price: ₹{price}\n"
                    f"200 DMA: ₹{dma}\n"
                    f"Below DMA: {diff}%\n"
                )
                print(f"  ✓ {s} - H45 Pattern Alert!")
        
        except Exception as e:
            print(f"  ⚠️  Error scanning {s}: {e}")

    # -------- Send Alerts
    print(f"\n{'='*60}")
    print(f"SCAN COMPLETE")
    print(f"{'='*60}")
    
    if alerts:
        subject = f"Stock Strategy Report – {now.strftime('%d %b %Y')}"
        body = "\n\n".join(alerts)
        
        print(f"\n📧 EMAIL REPORT")
        print(f"{'-'*60}")
        print(f"Subject: {subject}\n")
        print(body)
        print(f"{'-'*60}\n")
        
        email_sent = send_email(subject, body)
        if email_sent:
            print(f"✅ Email sent successfully with {len(alerts)} alerts")
        else:
            print(f"⚠️  {len(alerts)} alerts found but email not sent")
            print(f"   Configure EMAIL_FROM, EMAIL_TO, EMAIL_PASSWORD to enable email")
    else:
        print("\n❌ No alerts today")
        print("   All stocks are outside the strategy thresholds")


# --------------- ENTRY --------------------
if __name__ == "__main__":
    # Detect if running manually or via GitHub Actions
    github_event = os.getenv("GITHUB_EVENT_NAME")
    github_actions = os.getenv("GITHUB_ACTIONS")

    manual_run = (
        github_event == "workflow_dispatch"
        or github_actions is None
    )

    run(manual=manual_run)
