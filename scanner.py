import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import os
import sys
import pytz

# ================= CONFIG =================
CSV_FILE = os.getenv("STOCKS_CSV_FILE", "stocks_layout.csv")

IST = pytz.timezone("Asia/Kolkata")

V20_MIN_MOVE = 20      # 20% upmove
V20_PULLBACK_RANGE = 5 # Alert when price pulls back within 5% of pattern start
V20_LOOKBACK_DAYS = 180  # Only check patterns from last 6 months
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
    Find V20 patterns - strong upward moves of 20%+ that could indicate support levels.
    Returns list of recent patterns (last 6 months).
    """
    try:
        # Download longer history for pattern detection
        df = yf.download(symbol, period="4y", progress=False)
        if df.empty:
            return []

        df = clean_yf_df(df)

        if len(df) < 50:
            return []

        # Calculate lookback cutoff date
        cutoff_date = datetime.now() - timedelta(days=V20_LOOKBACK_DAYS)

        patterns = []
        i = 0

        while i < len(df) - 5:  # Need at least 5 days for a pattern
            open_p = float(df.iloc[i]["Open"])
            close_p = float(df.iloc[i]["Close"])

            # Must be green candle to start
            if close_p <= open_p:
                i += 1
                continue

            start_price = open_p
            start_date = df.iloc[i]["Date"] if "Date" in df.columns else df.index[i]
            
            # Convert to datetime for comparison
            if hasattr(start_date, 'date'):
                pattern_date = start_date
            else:
                pattern_date = pd.to_datetime(start_date)
            
            # Skip old patterns
            if pattern_date.replace(tzinfo=None) < cutoff_date:
                i += 1
                continue
            
            high = close_p
            end_idx = i + 1

            # Look for strong upward move (allow 1-2 red candles in between)
            consecutive_red = 0
            max_consecutive_red = 2
            
            for j in range(i + 1, min(i + 30, len(df))):  # Look up to 30 days ahead
                o = float(df.iloc[j]["Open"])
                c = float(df.iloc[j]["Close"])
                
                if c > o:  # Green candle
                    high = max(high, c)
                    consecutive_red = 0
                    end_idx = j
                else:  # Red candle
                    consecutive_red += 1
                    if consecutive_red > max_consecutive_red:
                        break

            move = ((high - start_price) / start_price) * 100

            # Only keep patterns with 20%+ move
            if move >= V20_MIN_MOVE:
                patterns.append({
                    "start_date": pattern_date.date() if hasattr(pattern_date, 'date') else pattern_date,
                    "start_price": round(start_price, 2),
                    "peak_price": round(high, 2),
                    "move": round(move, 2),
                })

            i = end_idx + 1

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
    """Main scanner logic."""
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
                # Find historical V20 patterns
                patterns = find_v20_patterns(s)
                if not patterns:
                    continue

                # Get current price
                df = yf.download(s, period="5d", progress=False)
                df = clean_yf_df(df)

                if df.empty:
                    continue

                current = float(df["Close"].iloc[-1])

                # Check if current price has pulled back near any pattern's START price
                for p in patterns:
                    # Calculate how far current price is from pattern start
                    diff_from_start = ((current - p["start_price"]) / p["start_price"]) * 100
                    
                    # Calculate how far current price has fallen from the peak
                    pullback_from_peak = ((p["peak_price"] - current) / p["peak_price"]) * 100

                    # Alert if:
                    # 1. Price is within V20_PULLBACK_RANGE% of the original start price (support level)
                    # 2. Price has pulled back at least 10% from peak (confirming it's a pullback scenario)
                    if abs(diff_from_start) <= V20_PULLBACK_RANGE and pullback_from_peak >= 10:
                        alerts.append(
                            f"🎯 V20 PATTERN ACTIVATED ({group})\n"
                            f"Stock: {s}\n"
                            f"Pattern Start: {p['start_date']} @ ₹{p['start_price']}\n"
                            f"Peak Price: ₹{p['peak_price']} (+{p['move']}%)\n"
                            f"Current Price: ₹{round(current, 2)}\n"
                            f"Distance from Support: {round(diff_from_start, 2)}%\n"
                            f"Pullback from Peak: {round(pullback_from_peak, 2)}%\n"
                            f"📊 ACTION: Price near support level - potential buy opportunity"
                        )
                        print(f"  ✓ {s} - V20 Pattern Alert! (Current: ₹{round(current, 2)}, Support: ₹{p['start_price']})")
                        break  # Only one alert per stock
            
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
                    f"📉 H45 PATTERN ACTIVATED\n"
                    f"Stock: {s}\n"
                    f"Current Price: ₹{price}\n"
                    f"200 DMA: ₹{dma}\n"
                    f"Below DMA: {diff}%\n"
                    f"📊 ACTION: Stock significantly below long-term average"
                )
                print(f"  ✓ {s} - H45 Pattern Alert! ({diff}% below 200 DMA)")
        
        except Exception as e:
            print(f"  ⚠️  Error scanning {s}: {e}")

    # -------- Send Alerts
    print(f"\n{'='*60}")
    print(f"SCAN COMPLETE")
    print(f"{'='*60}")
    
    if alerts:
        subject = f"🚨 Stock Strategy Alerts – {len(alerts)} Opportunities – {now.strftime('%d %b %Y')}"
        body = f"Found {len(alerts)} trading opportunities:\n\n" + "\n\n".join(alerts)
        body += f"\n\n{'─'*60}\n"
        body += f"Scan completed at {now.strftime('%d %b %Y %H:%M:%S IST')}\n"
        body += f"Next scan: Tomorrow same time\n"
        
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
        
        # Optional: Send a daily "no alerts" summary email
        # Uncomment below if you want daily confirmation emails even when no alerts
        """
        if not manual:
            subject = f"📊 Daily Stock Scan – No Alerts – {now.strftime('%d %b %Y')}"
            body = f"Daily scan completed at {now.strftime('%d %b %Y %H:%M:%S IST')}\n\n"
            body += f"Stocks scanned:\n"
            body += f"  • V40: {len(stocks['V40'])} stocks\n"
            body += f"  • V40NEXT: {len(stocks['V40NEXT'])} stocks\n"
            body += f"  • H45: {len(stocks['H45'])} stocks\n\n"
            body += "No trading opportunities found today.\n"
            body += "All stocks are outside strategy thresholds.\n"
            send_email(subject, body)
        """


# --------------- ENTRY --------------------
if __name__ == "__main__":
    github_event = os.getenv("GITHUB_EVENT_NAME")
    github_actions = os.getenv("GITHUB_ACTIONS")

    manual_run = (
        github_event == "workflow_dispatch"
        or github_actions is None
    )

    run(manual=manual_run)
