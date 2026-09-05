import yfinance as yf
import pandas as pd
import pandas_ta as ta
import requests
import os
from datetime import datetime

# Lấy token từ Secrets
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Danh sách mã chứng khoán (đã thêm hậu tố .VN)
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

def find_latest_shark_in_90_days(df):
    """Quét lùi 90 phiên để tìm Cá Mập Tím hoặc Vàng gần nhất"""
    # Tính toán chỉ báo cho toàn bộ dataframe
    df['SMA_20'] = ta.sma(df['Close'], length=20)
    df['SMA_20_Vol'] = ta.sma(df['Volume'], length=20)
    df['RSI_14'] = ta.rsi(df['Close'], length=14)
    df['MFI_14'] = ta.mfi(df['High'], df['Low'], df['Close'], df['Volume'], length=14)
    df['CMF_20'] = ta.cmf(df['High'], df['Low'], df['Close'], df['Volume'], length=20)
    df['Support_20'] = df['Low'].shift(1).rolling(window=20).min()
    
    df = df.dropna()
    if df.empty:
        return None

    # Lấy đúng 90 phiên gần nhất
    df_90 = df.tail(90)
    
    # Quét ngược từ ngày mới nhất về quá khứ (trong 90 ngày đó)
    for i in range(len(df_90) - 1, -1, -1):
        row = df_90.iloc[i]
        
        # Lấy giá trị của phiên trước đó (để check RSI phân kỳ)
        if i > 0:
            prev_row = df_90.iloc[i-1]
        else:
            # Nếu là phiên đầu tiên trong tập 90 ngày, lấy dòng trước nó từ df gốc
            idx_in_original = df.index.get_loc(df_90.index[i])
            prev_row = df.iloc[idx_in_original - 1] if idx_in_original > 0 else row
            
        # 1. Gatekeepers (Màng lọc dòng tiền & Trend)
        cmf_ok = row['CMF_20'] > 0
        trend_confirmed = (row['Close'] > row['SMA_20'] and row['Volume'] > row['SMA_20_Vol'] * 1.3) or \
                          (row['RSI_14'] > prev_row['RSI_14'] and prev_row['RSI_14'] < 35)
        
        is_not_blocked = cmf_ok and trend_confirmed
        if not is_not_blocked:
            continue

        # 2. Điều kiện bắt buộc A
        A1 = row['Low'] < row['Support_20']
        A2 = row['Close'] > row['Support_20']
        if not (A1 and A2):
            continue

        # 3. Điều kiện phụ B
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

        # 4. Tính điểm
        cond_count = int(A1) + int(A2) + int(B1) + int(B2) + int(B3) + int(B4) + int(B5) + int(B6)

        # 5. Chỉ lấy Cá Mập Tím (>=7) và Vàng (>=5)
        if cond_count >= 5:
            color_type = "PURPLE" if cond_count >= 7 else "YELLOW"
            bars_ago = len(df_90) - 1 - i
            
            return {
                "color": color_type,
                "score": cond_count,
                "date": df_90.index[i],
                "date_str": df_90.index[i].strftime('%d/%m/%Y'),
                "bars_ago": bars_ago,
                "close": row['Close'],
                "vol_ratio": round(vol_ratio, 1)
            }
            
    return None

def main():
    print("Đang tải dữ liệu 6 tháng gần nhất (để lấy đủ 90 phiên sau khi cắt)...")
    data = yf.download(vn_tickers, period="6mo", group_by="ticker", progress=False)
    
    purple_sharks = []
    yellow_sharks = []
    
    for t in vn_tickers:
        try:
            df = data[t].copy()
            if len(df) < 30: # Cần tối thiểu data để tính MA20
                continue
                
            shark = find_latest_shark_in_90_days(df)
            if shark:
                shark['symbol'] = t.replace(".VN", "")
                if shark['color'] == "PURPLE":
                    purple_sharks.append(shark)
                else:
                    yellow_sharks.append(shark)
        except Exception as e:
            continue

    # Sắp xếp các danh sách theo ngày: Từ Mới Nhất -> Cũ Nhất
    purple_sharks.sort(key=lambda x: x['date'], reverse=True)
    yellow_sharks.sort(key=lambda x: x['date'], reverse=True)
    
    # Chuẩn bị tin nhắn
    today_str = datetime.now().strftime("%d/%m/%Y")
    total_purple = len(purple_sharks)
    total_yellow = len(yellow_sharks)
    
    # Trường hợp không có con nào
    if not purple_sharks and not yellow_sharks:
        msg = f"💤 <b>{total_purple} CÁ MẬP TÍM - 90 NGÀY ({today_str})</b>\nKhông phát hiện mã nào đạt chuẩn Tím/Vàng trong 90 ngày qua."
        send_telegram(msg)
        print("Đã gửi báo cáo trống.")
        return

    # Khởi tạo Tiêu đề
    msg_lines = [f"🎯 <b>{total_purple} CÁ MẬP TÍM - 90 NGÀY ({today_str})</b>\n"]
    
    # 1. In danh sách Cá Mập Tím (gom chung, ưu tiên mới nhất lên đầu)
    if purple_sharks:
        msg_lines.append("🟪 <b>NHÓM CÁ MẬP TÍM (ĐIỂM 7-8/8):</b>")
        for s in purple_sharks:
            ago_str = "Hôm nay" if s['bars_ago'] == 0 else f"Cách đây {s['bars_ago']} ngày"
            msg_lines.append(f"• <b>{s['symbol']}</b> ({s['date_str']} - {ago_str})")
            msg_lines.append(f"  Giá: {s['close']:,.0f} | Vol: {s['vol_ratio']}x | Score: {s['score']}")
        msg_lines.append("") # Xuống dòng trắng
        
    # 2. In danh sách Cá Mập Vàng (gom chung, ưu tiên mới nhất lên đầu)
    if yellow_sharks:
        msg_lines.append("🟨 <b>NHÓM CÁ MẬP VÀNG (ĐIỂM 5-6/8):</b>")
        for s in yellow_sharks:
            ago_str = "Hôm nay" if s['bars_ago'] == 0 else f"Cách đây {s['bars_ago']} ngày"
            msg_lines.append(f"• <b>{s['symbol']}</b> ({s['date_str']} - {ago_str})")
            msg_lines.append(f"  Giá: {s['close']:,.0f} | Vol: {s['vol_ratio']}x | Score: {s['score']}")

    # Gộp toàn bộ dòng thành 1 tin nhắn và gửi
    final_msg = "\n".join(msg_lines)
    send_telegram(final_msg)
    print("Hoàn tất gửi báo cáo!")

if __name__ == "__main__":
    main()
