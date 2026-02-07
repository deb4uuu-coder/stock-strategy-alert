import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os
import sys
import pytz

# Initial debug output
print("\n" + "=" * 80)
print("V20 SCANNER SCRIPT STARTING")
print("=" * 80)
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Files in current directory: {os.listdir('.')}")
print(f"stocks.xlsx exists? {os.path.exists('stocks.xlsx')}")
print("=" * 80 + "\n")

class V20Scanner:
    def __init__(self, excel_file_path, email_to, email_from, email_password):
        self.excel_file_path = excel_file_path
        self.email_to = email_to
        self.email_from = email_from
        self.email_password = email_password
        self.v20_alerts = []
        self.envelope_alerts = []
        
    def read_stocks_from_excel(self):
        """Read stock symbols from Excel file"""
        try:
            xls = pd.ExcelFile(self.excel_file_path)
            stocks = {}
            for sheet_name in ['v40', 'v40next', 'h45']:
                if sheet_name in xls.sheet_names:
                    df = pd.read_excel(xls, sheet_name=sheet_name)
                    stocks[sheet_name] = df.iloc[:, 1].dropna().tolist()
            return stocks
        except Exception as e:
            print(f"Error reading Excel file: {e}")
            import traceback
            traceback.print_exc()
            return {}
    
    def find_20_percent_patterns(self, symbol, days=365):
        """Find consecutive green candle patterns with 20%+ gain"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            stock = yf.Ticker(symbol)
            df = stock.history(start=start_date, end=end_date)
            
            if df.empty:
                return []
            
            patterns = []
            i = 0
            
            while i < len(df):
                start_idx = i
                start_price = df.iloc[i]['Open']
                current_high = df.iloc[i]['Close']
                
                j = i
                consecutive_green = 0
                
                while j < len(df) and df.iloc[j]['Close'] > df.iloc[j]['Open']:
                    current_high = max(current_high, df.iloc[j]['Close'])
                    consecutive_green += 1
                    j += 1
                
                if consecutive_green > 0:
                    gain_percent = ((current_high - start_price) / start_price) * 100
                    
                    if gain_percent >= 20:
                        patterns.append({
                            'start_date': df.index[start_idx].strftime('%Y-%m-%d'),
                            'start_price': round(start_price, 2),
                            'end_price': round(current_high, 2),
                            'gain_percent': round(gain_percent, 2),
                            'candles': consecutive_green
                        })
                
                i = j if j > i else i + 1
            
            return patterns
        except Exception as e:
            print(f"Error analyzing {symbol}: {e}")
            return []
    
    def get_current_price_and_sma(self, symbol):
        """Get current price and 200 SMA"""
        try:
            stock = yf.Ticker(symbol)
            df = stock.history(period='220d')
            
            if df.empty:
                return None, None
            
            current_price = df.iloc[-1]['Close']
            sma_200 = df['Close'].rolling(window=200).mean().iloc[-1] if len(df) >= 200 else None
            
            return round(current_price, 2), round(sma_200, 2) if sma_200 else None
        except Exception as e:
            print(f"Error getting current price for {symbol}: {e}")
            return None, None
    
    def check_envelope_strategy(self, symbol, group):
        """Check Envelope strategy: Buy at -14% from 200 SMA, Sell at +30% from buy"""
        try:
            current_price, sma_200 = self.get_current_price_and_sma(symbol)
            
            if current_price is None or sma_200 is None:
                print(f"    - Insufficient data for Envelope strategy")
                return
            
            # Calculate percentage drop from 200 SMA
            drop_from_sma = ((sma_200 - current_price) / sma_200) * 100
            
            print(f"    Current Price: Rs.{current_price}")
            print(f"    200 SMA: Rs.{sma_200}")
            print(f"    Drop from SMA: {round(drop_from_sma, 2)}%")
            
            # BUY Signal: Price is 14% or more below 200 SMA
            if drop_from_sma >= 14:
                sell_target = round(current_price * 1.30, 2)  # 30% above current price
                
                alert_msg = f"ENVELOPE BUY - {symbol} ({group})\n"
                alert_msg += f"   Current Price: Rs.{current_price}\n"
                alert_msg += f"   200 SMA: Rs.{sma_200}\n"
                alert_msg += f"   Drop from SMA: {round(drop_from_sma, 2)}%\n"
                alert_msg += f"   SELL Target (30% up): Rs.{sell_target}\n"
                
                self.envelope_alerts.append(alert_msg)
                print(f"    🔔 ENVELOPE BUY ALERT GENERATED!")
            else:
                print(f"    ℹ️  Not at buy point (need 14%+ drop, current: {round(drop_from_sma, 2)}%)")
        
        except Exception as e:
            print(f"  ❌ Error in Envelope strategy for {symbol}: {e}")
    
    def check_v20_alerts(self, symbol, group, patterns, current_price):
        """Check if stock meets V20 alert conditions"""
        if not patterns or current_price is None:
            return
        
        for pattern in patterns:
            start_price = pattern['start_price']
            difference_percent = abs((current_price - start_price) / start_price) * 100
            
            if difference_percent <= 1:
                alert_msg = f"V20 ACTIVATED - {symbol} ({group})\n"
                alert_msg += f"   Current Price: Rs.{current_price}\n"
                alert_msg += f"   Pattern Start: Rs.{start_price} (Date: {pattern['start_date']})\n"
                alert_msg += f"   Pattern Gain: {pattern['gain_percent']}%\n"
                self.v20_alerts.append(alert_msg)
            
            elif difference_percent <= 5 and current_price < start_price:
                alert_msg = f"NEAR V20 - {symbol} ({group})\n"
                alert_msg += f"   Current Price: Rs.{current_price}\n"
                alert_msg += f"   Pattern Start: Rs.{start_price} (Date: {pattern['start_date']})\n"
                alert_msg += f"   Difference: {round(difference_percent, 2)}%\n"
                alert_msg += f"   Pattern Gain: {pattern['gain_percent']}%\n"
                self.v20_alerts.append(alert_msg)
    
    def send_email(self):
        """Send consolidated email with all alerts"""
        total_alerts = len(self.v20_alerts) + len(self.envelope_alerts)
        
        if total_alerts == 0:
            print("No alerts to send.")
            return
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.email_from
            msg['To'] = self.email_to
            msg['Subject'] = f"Stock Scanner Alerts - {datetime.now().strftime('%Y-%m-%d')}"
            
            body = "STOCK SCANNER DAILY REPORT\n"
            body += "=" * 50 + "\n\n"
            body += f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M IST')}\n"
            body += f"Total Alerts: {total_alerts}\n"
            body += f"  - V20 Alerts: {len(self.v20_alerts)}\n"
            body += f"  - Envelope Alerts: {len(self.envelope_alerts)}\n\n"
            body += "=" * 50 + "\n\n"
            
            # V20 Alerts
            if self.v20_alerts:
                body += "V20 STRATEGY ALERTS\n"
                body += "-" * 50 + "\n"
                body += "\n".join(self.v20_alerts)
                body += "\n\n"
            
            # Envelope Alerts
            if self.envelope_alerts:
                body += "ENVELOPE STRATEGY ALERTS\n"
                body += "-" * 50 + "\n"
                body += "\n".join(self.envelope_alerts)
                body += "\n\n"
            
            body += "=" * 50 + "\n"
            body += "STRATEGY DEFINITIONS:\n\n"
            body += "V20 Strategy:\n"
            body += "  - Pattern = 20%+ gain from consecutive green candles\n"
            body += "  - NEAR = Current price within 5% of pattern start\n"
            body += "  - ACTIVATED = Current price matches pattern start\n\n"
            body += "Envelope Strategy:\n"
            body += "  - BUY = Price drops 14%+ below 200-day SMA\n"
            body += "  - SELL Target = 30% gain from buy price\n"
            
            msg.attach(MIMEText(body, 'plain'))
            
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(self.email_from, self.email_password)
            server.send_message(msg)
            server.quit()
            
            print(f"✅ Email sent successfully with {total_alerts} alerts!")
        except Exception as e:
            print(f"❌ Error sending email: {e}")
            import traceback
            traceback.print_exc()
    
    def run_scan(self):
        """Main scanning function"""
        print("\n" + "=" * 80)
        print("RUN_SCAN FUNCTION CALLED")
        print("=" * 80)
        print(f"Starting scan at {datetime.now()}")
        print("=" * 80 + "\n")
        
        print("Reading Excel file...")
        stocks = self.read_stocks_from_excel()
        
        print(f"\n{'='*60}")
        print(f"EXCEL FILE READ SUCCESSFULLY")
        print(f"Total groups found: {len(stocks)}")
        for group, symbols in stocks.items():
            print(f"  {group}: {len(symbols)} stocks")
            print(f"  Symbols: {symbols[:3]}..." if len(symbols) > 3 else f"  Symbols: {symbols}")
        print(f"{'='*60}\n")
        
        if not stocks or all(len(v) == 0 for v in stocks.values()):
            print("ERROR: No stocks found in Excel file!")
            print("Please check:")
            print("  1. Excel file name is 'stocks.xlsx'")
            print("  2. Sheet names are: v40, v40next, h45")
            print("  3. Stock symbols are in Column B")
            return
        
        total_patterns_found = 0
        
        for group, symbols in stocks.items():
            print(f"\n{'='*60}")
            print(f"Scanning {group} group ({len(symbols)} stocks)...")
            print(f"{'='*60}")
            
            # Determine strategy for this group
            if group == 'h45':
                strategy = 'ENVELOPE'
            else:
                strategy = 'V20'
            
            print(f"Strategy: {strategy}")
            
            for symbol in symbols:
                try:
                    print(f"\n  Analyzing {symbol}...")
                    
                    if strategy == 'V20':
                        # V20 Strategy for v40 and v40next groups
                        patterns = self.find_20_percent_patterns(symbol)
                        
                        if patterns:
                            print(f"    ✓ Found {len(patterns)} pattern(s) with 20%+ gain")
                            for idx, p in enumerate(patterns, 1):
                                print(f"      Pattern {idx}: Start={p['start_date']}, Price=Rs.{p['start_price']}, Gain={p['gain_percent']}%")
                            total_patterns_found += len(patterns)
                            
                            current_price, _ = self.get_current_price_and_sma(symbol)
                            print(f"    Current Price: Rs.{current_price}")
                            
                            alerts_before = len(self.v20_alerts)
                            self.check_v20_alerts(symbol, group, patterns, current_price)
                            alerts_after = len(self.v20_alerts)
                            
                            if alerts_after > alerts_before:
                                print(f"    🔔 V20 ALERT GENERATED!")
                            else:
                                print(f"    ℹ️  Pattern found but doesn't meet alert conditions")
                        else:
                            print(f"    - No 20% patterns found in last year")
                    
                    elif strategy == 'ENVELOPE':
                        # Envelope Strategy for h45 group
                        alerts_before = len(self.envelope_alerts)
                        self.check_envelope_strategy(symbol, group)
                        alerts_after = len(self.envelope_alerts)
                        
                        if alerts_after <= alerts_before:
                            print(f"    ℹ️  No Envelope alert (need 14%+ drop from 200 SMA)")
                    
                except Exception as e:
                    print(f"  ❌ Error processing {symbol}: {e}")
                    import traceback
                    traceback.print_exc()
                    continue
        
        print(f"\n{'='*80}")
        print(f"SCAN SUMMARY")
        print(f"{'='*80}")
        print(f"Total 20% patterns found: {total_patterns_found}")
        print(f"V20 alerts generated: {len(self.v20_alerts)}")
        print(f"Envelope alerts generated: {len(self.envelope_alerts)}")
        print(f"Total alerts: {len(self.v20_alerts) + len(self.envelope_alerts)}")
        print(f"{'='*80}\n")
        
        if self.v20_alerts or self.envelope_alerts:
            print("📧 Attempting to send email...")
            print(f"From: {self.email_from}")
            print(f"To: {self.email_to}")
            print(f"Number of alerts: {len(self.v20_alerts) + len(self.envelope_alerts)}\n")
            self.send_email()
        else:
            print("\n⚠️  No alerts generated today.")
            print("\nREASON: Conditions not met:")
            print("  V20: Current price not within 5% below pattern start")
            print("  Envelope: Price not 14%+ below 200 SMA")
            print("\nThis is normal - no buying opportunities right now.")
        
        print("\n" + "=" * 80)
        print("SCAN COMPLETED SUCCESSFULLY")
        print("=" * 80)

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("MAIN EXECUTION STARTING")
    print("=" * 80)
    
    # Configuration
    EXCEL_FILE = "stocks.xlsx"
    EMAIL_TO = "deb.4uuu@gmail.com"
    EMAIL_FROM = os.environ.get('EMAIL_FROM')
    EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
    
    print(f"Excel File: {EXCEL_FILE}")
    print(f"Email To: {EMAIL_TO}")
    print(f"Email From: {EMAIL_FROM}")
    print(f"Email Password: {'*' * len(EMAIL_PASSWORD) if EMAIL_PASSWORD else 'NOT SET'}")
    print("=" * 80 + "\n")
    
    if not EMAIL_FROM or not EMAIL_PASSWORD:
        print("ERROR: Email credentials not set!")
        print("EMAIL_FROM:", EMAIL_FROM)
        print("EMAIL_PASSWORD:", "SET" if EMAIL_PASSWORD else "NOT SET")
        sys.exit(1)
    
    # Run scanner
    print("Creating V20Scanner instance...")
    scanner = V20Scanner(EXCEL_FILE, EMAIL_TO, EMAIL_FROM, EMAIL_PASSWORD)
    
    print("Calling run_scan()...")
    scanner.run_scan()
    
    print("\n" + "=" * 80)
    print("SCRIPT EXECUTION COMPLETED")
    print("=" * 80)
