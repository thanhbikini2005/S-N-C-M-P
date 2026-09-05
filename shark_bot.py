import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import os
from datetime import datetime

# Lấy token từ Secrets
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Danh sách mã chứng khoán (đã thêm hậu tố .VN cho Yahoo Finance)
tickers_list = [
    "VCB","BID","CTG","TCB","MBB","VPB","ACB","STB","HDB","VIB","SHB","TPB","LPB","MSB","SSB","OCB","EIB","NAB","BAB","KLB","BVB",
    "SSI","VND","VCI","HCM","SHS","MBS","VIX","FTS","CTS","BSI","AGR","ORS","VDS","BVS","APS","DSC",
    "VHM","VIC","NVL","PDR","DIG","DXG","KDH","NLG","CEO","HDG","TCH","CRE","HQC","SCR","NTL","IJC","SJS","QCG","VPI","NBB",
    "BCM","KBC","IDC","VGC","SZC","PHR","GVR","SIP","NTC","SNZ","TIP","D2D","ITA","SZL",
    "HPG","HSG","NKG","HT1","BCC","KSB","VGS","SMC","POM","TLH","DHA","CTI",
    "VCG","HHV","FCN","LCG","C4G","HBC","CTD","G36","DPG","HUT","CII",
    "GAS","PVD","PVS","BSR","PLX","OIL","PVC","PVB","PSH","PVT",
    "MWG","PNJ","FRT","DGW","PET","VRE","HAX",
    "MSN","VNM","SAB","KDC","SBT","QNS","MCH","MCM","PAN","VOC",
    "VHC","ANV","IDI","FMC","CMX","ASM","ACL","MPC",
    "HAG","HNG","BAF","DBC","LTG","TAR","TSC","SJF","ABS",
    "DGC","DPM","DCM","CSV","DDV","BFC","LAS","PAT",
    "GMD","HAH","VOS","VSC","SGP","TCL","PHP","DXP","VIP",
    "POW","REE","GEG","PC1","NT2","QTP","HND","TV2","VSH","TTA","SBA","KHP",
    "TNG","VGT","TCM","MSH","GIL","STK","HTG","EVE",
    "FPT","CMG","VGI","ELC","ITD","SGT","FOX","TTN","CTR",
    "DHG","IMP","TRA","DVN","DMC","JVC","TNH","AMV","PMC","DBD",
    "DPR","TRC","DRI","RTB","BRR"
]
vn_tickers = [f"{t}.VN" for t in tickers_list]

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    requests.post(url, data=payload)

def evaluate_shark(df):
    # Trích xuất phiên mới nhất
    latest = df.iloc[-1]
    
    # Check Gatekeepers
    cmf_ok = latest['CMF_20'] > 0
    # Màng lọc trend (Vượt MA20 Vol > 1.3x) hoặc RSI quá bán vòng lên (giả lập đơn giản)
    trend_confirmed = (latest['Close'] > latest['SMA_20'] and latest['Volume'] > latest['SMA_20_Vol'] * 1.3) or (latest['RSI_14'] > df.iloc[-2]['RSI_14'] and df.iloc[-2]['RSI_14'] < 35)
    is_not_blocked = cmf_ok and trend_confirmed

    if not is_not_blocked:
        return None

    # Điều kiện bắt buộc A
    A1 = latest['Low'] < latest['Support_20']
    A2 = latest['Close'] > latest['Support_20']
    if not (A1 and A2):
        return None

    # Điều kiện phụ B
    candle_range = latest['High'] - latest['Low'] if latest['High'] - latest['Low'] > 0 else 0.001
    lower_shadow = latest['Close'] - latest['Low'] if latest['Close'] >= latest['Open'] else latest['Open'] - latest['Low']
    
    B1 = (lower_shadow / candle_range) >= 0.50
    B2 = ((latest['Close'] - latest['Low']) / candle_range) >= 0.70
    vol_ratio = latest['Volume'] / latest['SMA_20_Vol'] if latest['SMA_20_Vol'] > 0 else 0
    B3 = 1.5 <= vol_ratio <= 3.0
    B4 = cmf_ok
    B5 = latest['MFI_14'] > 55
    stop_loss_risk = (latest['Close'] - latest['Low']) / latest['Close']
    B6 = stop_loss_risk <= 0.07

    # Tính điểm
    cond_count = int(A1) + int(A2) + int(B1) + int(B2) + int(B3) + int(B4) + int(B5) + int(B6)

    # Phân loại
    if cond_count >= 7:
        shark_type = "🟪 Cá Mập Tím (Score: 7-8) - MẠNH NHẤT"
    elif cond_count >= 5:
        shark_type = "🟨 Cá Mập Vàng (Score: 5-6) - RẤT MẠNH"
    else:
        shark_type = "🟩 Cá Mập Xanh (Score: <5) - TRUNG BÌNH"

    return {
        "type": shark_type,
        "score": cond_count,
        "close": latest['Close'],
        "vol_ratio": round(vol_ratio, 1),
        "cmf": round(latest['CMF_20'], 3)
    }

def main():
    print("Đang tải dữ liệu chứng khoán...")
    # Tải dữ liệu 3 tháng để đủ tính các đường MA20 và CMF
    data = yf.download(vn_tickers, period="3mo", group_by="ticker", progress=False)
    
    results = []
    for t in vn_tickers:
        try:
            df = data[t].dropna()
            if len(df) < 25:
                continue
                
            # Tính toán chỉ báo bằng pandas_ta
            df['SMA_20'] = ta.sma(df['Close'], length=20)
            df['SMA_20_Vol'] = ta.sma(df['Volume'], length=20)
            df['RSI_14'] = ta.rsi(df['Close'], length=14)
            df['MFI_14'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
            df['CMF_20'] = ta.cmf(df['High'], df['Low'], df['Close'], df['Volume'], length=20)
            
            # Tính mốc hỗ trợ (Low nhỏ nhất của 20 phiên trước đó)
            df['Support_20'] = df['Low'].shift(1).rolling(window=20).min()
            
            df = df.dropna()
            if df.empty: continue

            shark_signal = evaluate_shark(df)
            if shark_signal:
                symbol = t.replace(".VN", "")
                results.append(f"🦈 <b>{symbol}</b>: {shark_signal['type']}\nGiá: {shark_signal['close']:,.0f} | Vol: {shark_signal['vol_ratio']}x MA20 | CMF: {shark_signal['cmf']}")
                
        except Exception as e:
            continue

    # Tổng hợp và gửi tin nhắn
    today_str = datetime.now().strftime("%d/%m/%Y")
    if results:
        message = f"🎯 <b>BÁO CÁO CÁ MẬP ({today_str})</b>\n\n" + "\n\n".join(results)
    else:
        message = f"💤 <b>BÁO CÁO CÁ MẬP ({today_str})</b>\nKhông phát hiện tín hiệu Cá Mập nào hôm nay."
        
    send_telegram(message)
    print("Hoàn tất gửi báo cáo!")

if __name__ == "__main__":
    main()
