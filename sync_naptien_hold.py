import time
import schedule
import pymongo
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import sys
import io

# Ghi đè sys.stdout và stderr để dùng UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

# 🔹 Cấu hình MongoDB
MONGO_URI = "mongodb://localhost:27017/BudgetManager"
DB_NAME = "BudgetManager"
NAPTIEN_COLLECTION = "nap_tien"
HOLD_COLLECTION = "hold"

# 🔹 Google Sheets config
SPREADSHEET_ID = "1ZRHiKeNdHqOC6y-i2vHTTUSjwHC7MOJRV9p8BbI9-eQ"
SERVICE_ACCOUNT_FILE = "./assets/google.json"

# Kết nối MongoDB
client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]
col_naptien = db[NAPTIEN_COLLECTION]
col_hold = db[HOLD_COLLECTION]

# Kết nối Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
gc = gspread.authorize(credentials)

# Định nghĩa cột
HEADERS_NAPTIEN = ["ID Bản Ghi", "ID BC", "Người nạp","Ngày tạo", "Số tiền nạp", "Người xác nhận" ]
HEADERS_HOLD = ["ID Bản Ghi", "ID BC", "Người hold", "Ngày tạo","Số tiền hold", "Người xác nhận" ]

NAPTIEN_START_ROW = 2  # Dòng bắt đầu cho NapTien

def get_or_create_sheet(name, headers):
    """Lấy hoặc tạo worksheet"""
    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    worksheet_list = {ws.title: ws for ws in spreadsheet.worksheets()}

    if name not in worksheet_list:
        ws = spreadsheet.add_worksheet(title=name, rows="2000", cols="20")
        ws.append_row(headers)
        print(f"📌 Tạo sheet mới: {name}")
    else:
        ws = worksheet_list[name]
        # đảm bảo hàng 1 là headers
        try:
            if ws.row_values(1) != headers:
                ws.delete_rows(1)
                ws.insert_row(headers, 1)
        except Exception:
            ws.insert_row(headers, 1)

    return ws

def fetch_data(collection, kind="naptien", month_filter=None):
    """Lấy dữ liệu từ MongoDB. Nếu month_filter là (year, month), chỉ lấy tháng đó"""
    records = collection.find().sort("created_at", pymongo.DESCENDING)
    rows = []

    for r in records:
        raw_ts = r.get("created_at", 0)

        try:
            ts = float(raw_ts)  # ép kiểu
        except (ValueError, TypeError):
            ts = 0

        if ts > 1e12:  # nanoseconds
            ts /= 1e9
        elif ts > 1e10:  # milliseconds
            ts /= 1e3

        dt = datetime.fromtimestamp(ts, tz=VN_TZ)

        # Nếu có filter tháng
        if month_filter:
            if dt.year != month_filter[0] or dt.month != month_filter[1]:
                continue

        time_str = dt.strftime("%d/%m/%Y %H:%M:%S")

        if kind == "naptien":
            rows.append([
                str(r.get("_id")),
                r.get("id_bc", ""),
                r.get("ten_tele", ""),
                time_str,
                r.get("so_tien_nap", 0),
                r.get("nguoi_hanh_dong", ""),
            ])
        else:  # hold
            rows.append([
                str(r.get("_id")),
                r.get("id_bc", ""),
                r.get("ten_tele", ""),
                time_str,
                r.get("hold", 0),
                r.get("nguoi_hanh_dong", ""),
            ])
    return rows

def sync_naptien():
    now = datetime.now(VN_TZ)
    sheet_name = f"{now.year}_{now.month:02d}"
    print(f"🔄 Sync NapTien tháng {sheet_name}...")

    ws = get_or_create_sheet(sheet_name, HEADERS_NAPTIEN)
    rows = fetch_data(col_naptien, "naptien", month_filter=(now.year, now.month))

    if rows:
        if now.month == 8:
            start_row = 533
            start_cell = f"A{start_row}"
            # Không xóa dữ liệu cũ
        else:
            start_row = 2
            start_cell = f"A{start_row}"
            ws.batch_clear([f"A{start_row}:F"])  # Xóa dữ liệu cũ cho các tháng khác

        ws.update(rows, start_cell, value_input_option="USER_ENTERED")
        print(f"✅ NapTien: {len(rows)} dòng được ghi vào sheet {sheet_name} từ dòng {start_row}")
    else:
        print(f"NapTien: không có dữ liệu tháng {sheet_name}")


def sync_hold():
    print("🔄 Sync Hold...")
    ws = get_or_create_sheet("Hold", HEADERS_HOLD)
    rows = fetch_data(col_hold, "hold")

    ws.batch_clear([f"A2:F"])
    if rows:
        ws.update(rows, "A2", value_input_option="USER_ENTERED")
        print(f"✅ Hold: {len(rows)} dòng được ghi từ dòng 2")
    else:
        print("Hold: không có dữ liệu")

# Lên lịch chạy mỗi 30s
schedule.every(30).minutes.do(sync_naptien)
schedule.every(30).minutes.do(sync_hold)

print("🚀 Bắt đầu sync NapTien & Hold (luôn chạy)...")
while True:
    schedule.run_pending()
    time.sleep(1)
