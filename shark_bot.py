import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import os
from datetime import datetime

# Lấy token từ Secrets
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Danh sách mã chứng khoán
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

def scan_sharks_50_days(df):
    sharks_found = []
    # Quét đúng 50 phiên cuối cùng trong Dataframe
    check_days = min(50, len(df))
    
    for i in range(len(df) - check_days, len(df)):
        row = df.iloc[i]
        prev_row = df.iloc[i-1] if i > 0 else row
        
        # Màng lọc Trend & CMF
        cmf_ok = row['CMF_20'] > 0
        trend_confirmed = (row['Close'] > row['SMA_20'] and row['Volume'] > row['SMA_20_Vol'] * 1.3) or (row['RSI_14'] > prev_row['RSI_14'] and prev_row['RSI_14'] < 35)
        is_not_blocked = cmf_ok and trend_confirmed

        if not is_not_blocked:
            continue

        # Điều kiện bắt buộc A
        A1 = row['Low'] < row['Support_20']
        A2 = row['Close'] > row['Support_20']
        if not (A1 and A2):
            continue

        # Điều kiện phụ B
        candle_range = row['High'] - row['Low'] if row['High'] - row['Low'] > 0 else 0.001
        lower_shadow = row['Close'] - row['Low'] if row['Close'] >= row['Open'] else row['Open'] - row['Low']
        
        B1 = (lower_shadow / candle_range) >= 0.50
        B2 = ((row['Close'] - row['Low']) / candle_range) >= 0.70
        vol_ratio = row['Volume'] / row['SMA_20_Vol'] if row['SMA_20_Vol'] > 0 else 0
        B3 = 1.5 <= vol_ratio <= 3.0
        B4 = cmf_ok
        B5 = row['MFI_14'] > 55
        stop_loss_risk = (row['Close'] - row['Low']) / row['Close']
        B6 = stop_loss_risk <= 0.07

        # Tính tổng điểm
        cond_count = int(A1) + int(A2) + int(B1) + int(B2) + int(B3) + int(B4) + int(B5) + int(B6)

        # Phân loại màu (Bỏ qua Xanh, chỉ lấy Tím và Vàng)
        if cond_count >= 7:
            shark_type = "🟪 Tím"
        elif cond_count >= 5:
            shark_type = "🟨 Vàng"
        else:
            continue

        # Format ngày tháng và lưu lại
        date_str = row.name.strftime('%d/%m')
        sharks_found.append(f"  • {date_str}: {shark_type} ({cond_count}đ) - Giá: {row['Close']:,.0f}")
        
    return sharks_found

def main():
    print("Đang tải dữ liệu chứng khoán...")
    # Tải 4 tháng để dư dả dữ liệu tính đường trung bình (MA20) và quét 50 ngày
    data = yf.download(vn_tickers, period="4mo", group_by="ticker", progress=False)
    
    results = []
    for t in vn_tickers:
        try:
            df = data[t].dropna().copy()
            if len(df) < 50:
                continue
                
            # Tính toán chỉ báo kỹ thuật
            df['SMA_20'] = ta.sma(df['Close'], length=20)
            df['SMA_20_Vol'] = ta.sma(df['Volume'], length=20)
            df['RSI_14'] = ta.rsi(df['Close'], length=14)
            df['MFI_14'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
            df['CMF_20'] = ta.cmf(df['High'], df['Low'], df['Close'], df['Volume'], length=20)
            df['Support_20'] = df['Low'].shift(1).rolling(window=20).min()
            
            df = df.dropna()
            if df.empty: continue

            # Quét tìm cá mập Tím/Vàng trong 50 ngày
            sharks = scan_sharks_50_days(df)
            if sharks:
                symbol = t.replace(".VN", "")
                results.append(f"🦈 <b>{symbol}</b>:\n" + "\n".join(sharks))
                
        except Exception as e:
            continue

    # Tổng hợp và gửi tin nhắn
    today_str = datetime.now().strftime("%d/%m/%Y")
    if results:
        message = f"🎯 <b>CÁ MẬP 50 NGÀY ({today_str})</b>\n\n" + "\n\n".join(results)
    else:
        message = f"💤 <b>CÁ MẬP 50 NGÀY ({today_str})</b>\nKhông có mã nào đạt Tím/Vàng trong 50 phiên qua."
        
    send_telegram(message)
    print("Hoàn tất gửi báo cáo!")

if __name__ == "__main__":
    main()
