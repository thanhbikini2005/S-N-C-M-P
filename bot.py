import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
from datetime import datetime

# --- CẤU HÌNH BOT TELEGRAM ---
TELEGRAM_TOKEN = "8987786992:AAH6SvFiPUdvI6coXAuC9JGWNSQPWLWkrCI"
CHAT_ID = "1242874545"

# Danh sách mã chứng khoán (thêm hậu tố .VN cho Yahoo Finance)
TICKERS = ["HPG.VN", "SSI.VN", "FPT.VN", "MWG.VN", "VNM.VN", "VIC.VN", "VHM.VN", "TCB.VN", "STB.VN", "VND.VN", "DIG.VN", "NVL.VN", "KBC.VN"]

# --- PARAMETERS TỪ JSON ---
PARAMS = {
    "support_lookback_bars": 20,
    "volume_ma_period": 20,
    "cmf_period": 20,
    "mfi_period": 14,
    "min_lower_shadow_ratio": 0.50,
    "close_range_ratio": 0.70,
    "volume_multiplier_min": 1.5,
    "volume_multiplier_max": 3.0,
    "mfi_threshold": 55,
    "max_stop_loss_pct": 0.07
}

def send_telegram(message):
    """Gửi tin nhắn qua Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, data=payload)
    except Exception as e:
        print(f"Lỗi gửi Telegram: {e}")

def process_data(df):
    """Tính toán các chỉ báo và công thức Shark Tracker"""
    # Xóa các dòng thiếu dữ liệu
    df = df.dropna()
    if len(df) < 50: return None # Cần đủ data để tính MA20, CMF20
    
    # Tính các chỉ báo vệ tinh bằng pandas_ta
    df['CMF_20'] = ta.cmf(df['High'], df['Low'], df['Close'], df['Volume'], length=PARAMS['cmf_period'])
    df['MFI_14'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=PARAMS['mfi_period'])
    df['MA20_Volume'] = df['Volume'].rolling(window=PARAMS['volume_ma_period']).mean()
    df['SMA_20'] = ta.sma(df['Close'], length=20)
    df['RSI_14'] = ta.rsi(df['Close'], length=14)
    
    # Biến số (Variables Calculation)
    df['support_level'] = df['Low'].rolling(window=PARAMS['support_lookback_bars']).min().shift(1)
    df['candle_range'] = df['High'] - df['Low']
    df['lower_shadow'] = df['Close'] - df['Low']
    df['stop_loss_risk_pct'] = (df['Close'] - df['Low']) / df['Close']
    
    # Gatekeepers (Lọc nhiễu/Xu hướng)
    # Xấp xỉ trend_confirmed: Vượt MA20 kèm Vol > 1.5x HOẶC RSI tạo đáy sau cao hơn đáy trước khi giá tạo đáy mới
    df['break_ma20_with_volume'] = (df['Close'] > df['SMA_20']) & (df['Volume'] > 1.5 * df['MA20_Volume'])
    df['rsi_divergence'] = (df['RSI_14'] > df['RSI_14'].shift(1)) & (df['Low'] < df['Low'].shift(1))
    
    df['cmf_ok'] = df['CMF_20'] > 0
    df['trend_confirmed'] = df['break_ma20_with_volume'] | df['rsi_divergence'] # Lược bỏ double_bottom để tối ưu tốc độ
    df['is_not_blocked'] = df['cmf_ok'] & df['trend_confirmed']
    
    # Điều kiện tính điểm (Scoring Conditions)
    df['A1'] = df['Low'] < df['support_level']
    df['A2'] = df['Close'] > df['support_level']
    df['B1'] = (df['lower_shadow'] / df['candle_range']) >= PARAMS['min_lower_shadow_ratio']
    df['B2'] = (df['lower_shadow'] / df['candle_range']) >= PARAMS['close_range_ratio']
    df['B3'] = (df['Volume'] / df['MA20_Volume'] >= PARAMS['volume_multiplier_min']) & (df['Volume'] / df['MA20_Volume'] <= PARAMS['volume_multiplier_max'])
    df['B4'] = df['CMF_20'] > 0
    df['B5'] = df['MFI_14'] > PARAMS['mfi_threshold']
    df['B6'] = df['stop_loss_risk_pct'] <= PARAMS['max_stop_loss_pct']
    
    # Logic Pipeline: Tính điểm và màu sắc
    df['is_valid_shark'] = df['A1'] & df['A2'] & df['is_not_blocked']
    df['condCount'] = df[['A1', 'A2', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6']].sum(axis=1)
    
    def classify_shark(row):
        if not row['is_valid_shark']: return None
        if row['condCount'] >= 7: return "🟣 TÍM (Đạt >= 7/8 tiêu chí)"
        elif row['condCount'] >= 5: return "🟡 VÀNG (Đạt 5-6/8 tiêu chí)"
        else: return "🟢 XANH (Đạt < 5/8 tiêu chí)"
        
    df['Shark_Color'] = df.apply(classify_shark, axis=1)
    
    # Lấy 30 phiên gần nhất
    return df.tail(30)

def main():
    today_str = datetime.now().strftime("%d/%m/%Y")
    message = f"🦈 <b>BÁO CÁO SHARK TRACKER (30 PHIÊN GẦN NHẤT)</b>\n📅 Ngày quét: {today_str}\n\n"
    
    found_any = False
    
    for ticker in TICKERS:
        try:
            # Lấy data 6 tháng để có đủ nến tính MA, CMF
            raw_data = yf.download(ticker, period="6mo", progress=False)
            if raw_data.empty: continue
            
            # Gộp multi-index column nếu có
            if isinstance(raw_data.columns, pd.MultiIndex):
                raw_data.columns = raw_data.columns.droplevel(1)
                
            processed_df = process_data(raw_data)
            if processed_df is None: continue
            
            # Lọc ra các ngày có Cá Mập
            sharks = processed_df[processed_df['is_valid_shark'] == True]
            
            if not sharks.empty:
                found_any = True
                symbol_clean = ticker.replace(".VN", "")
                message += f"<b>{symbol_clean}</b> phát hiện tín hiệu:\n"
                
                for idx, row in sharks.iterrows():
                    date_val = idx.strftime('%d/%m/%Y')
                    color = row['Shark_Color']
                    close_p = row['Close']
                    pts = row['condCount']
                    message += f" ├ {date_val}: {color} (Giá: {close_p:,.0f} | Điểm: {pts}/8)\n"
                message += "\n"
                
        except Exception as e:
            print(f"Lỗi khi xử lý {ticker}: {e}")
            
    if not found_any:
        message += "<i>Không phát hiện tín hiệu Cá Mập nào thỏa mãn màng lọc trong 30 phiên qua ở danh mục theo dõi.</i>"
        
    send_telegram(message)
    print("Đã hoàn tất quét và gửi thông báo!")

if __name__ == "__main__":
    main()
