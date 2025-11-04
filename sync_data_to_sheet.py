import time
import schedule
import pymongo
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone, timedelta
import sys
import io

# Ghi đè sys.stdout và stderr để dùng UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 🔹 Cấu hình kết nối MongoDB
MONGO_URI = "mongodb://localhost:27017/BudgetManager"
DB_NAME = "BudgetManager"
COLLECTION_NAME = "ads_reports"
STATUS_COLLECTION = "sync_status"  # Bảng chứa cờ isChange

# 🔹 Cấu hình Google Sheets
SPREADSHEET_ID = "1QnoF26v95Qyo7VXLWREU6tHots-SRYWSerD6-mKLjpg"
SERVICE_ACCOUNT_FILE = "./assets/google.json"

# Kết nối MongoDB
client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]
status_collection = db[STATUS_COLLECTION]

# Kết nối Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
credentials = ServiceAccountCredentials.from_json_keyfile_name(SERVICE_ACCOUNT_FILE, scope)
gc = gspread.authorize(credentials)

# Tiêu đề cột
HEADERS = ["ID Bản Ghi", "Người gửi", "ID Quảng Cáo", "ID BC", "Chi Tiêu", "Hold", "Loại", "Ngày", "Số mess", "Thời Gian BC", "Nhóm", "Ghi Chú"]
END_COL = "L"  # Cột cuối tương ứng với HEADERS

VN_TZ = timezone(timedelta(hours=7))

def get_current_month_sheet():
    """Lấy hoặc tạo worksheet theo tháng hiện tại"""
    now = datetime.now(VN_TZ)
    
    if now.day == 1:  # ngày 1 -> vẫn tính tháng trước
        if now.month == 1:
            target_year, target_month = now.year - 1, 12
        else:
            target_year, target_month = now.year, now.month - 1
    else:
        target_year, target_month = now.year, now.month

    current_month = f"{target_year:04d}-{target_month:02d}"

    spreadsheet = gc.open_by_key(SPREADSHEET_ID)
    worksheet_list = {ws.title: ws for ws in spreadsheet.worksheets()}

    if current_month not in worksheet_list:
        worksheet = spreadsheet.add_worksheet(title=current_month, rows="1000", cols="20")
        worksheet.append_row(HEADERS)
        print(f"📌 Đã tạo sheet mới: {current_month}")
    else:
        worksheet = worksheet_list[current_month]
        try:
            if worksheet.row_values(1) != HEADERS:
                worksheet.delete_rows(1)
                worksheet.insert_row(HEADERS, 1)
        except Exception:
            worksheet.insert_row(HEADERS, 1)

    return worksheet

def get_mongo_data():
    now = datetime.now(VN_TZ)
    
    if now.day == 1:
        if now.month == 1:
            target_year, target_month = now.year - 1, 12
        else:
            target_year, target_month = now.year, now.month - 1
    else:
        target_year, target_month = now.year, now.month

    if target_month == 8:
        start_of_month = datetime(target_year, target_month, 1, tzinfo=VN_TZ)
    else:
        start_of_month = datetime(target_year, target_month, 2, tzinfo=VN_TZ)

    if target_month < 12:
        first_day_next_month = datetime(target_year, target_month + 1, 1, tzinfo=VN_TZ)
    else:
        first_day_next_month = datetime(target_year + 1, 1, 1, tzinfo=VN_TZ)

    end_of_month = first_day_next_month + timedelta(hours=23, minutes=59, seconds=59)

    print("📅 start (GMT+7):", start_of_month)
    print("📅 end   (GMT+7):", end_of_month)

    records = collection.find({
        "timestamp": {"$gte": start_of_month.timestamp(), "$lt": end_of_month.timestamp()}
    }).sort("timestamp", pymongo.DESCENDING)

    data_rows = []
    for record in records:
        ad_ids = record.get("ad_ids", []) or [""]
        ts = record.get("timestamp", 0)
        if isinstance(ts, (int, float)) and ts > 1e12:
            ts = ts / 1000.0
        time_str = datetime.fromtimestamp(ts, tz=VN_TZ).strftime("%Y-%m-%d %H:%M:%S")

        for ad_id in ad_ids:
            data_rows.append([
                str(record.get("_id", "")),
                record.get("sender") or "",
                ad_id or "",
                record.get("id_bc") or "",
                record.get("spend", 0),
                record.get("hold") or "",
                record.get("ad_type") or "",
                record.get("ad_date") or "",
                record.get("mess_num") or "",
                time_str,
                record.get("group_name") or "",
                record.get("note") or ""
            ])
    return data_rows

def update_isChange(status):
    status_collection.update_one({"_id": "sync_status"}, {"$set": {"isChange": status}}, upsert=True)

def clear_data_rows(worksheet):
    try:
        worksheet.batch_clear([f"A2:{END_COL}"])
    except Exception as e:
        print(f"⚠️ Không thể clear vùng dữ liệu A2:{END_COL}: {e}")

def ensure_capacity(worksheet, num_rows_needed):
    try:
        required = 1 + max(num_rows_needed, 1)
        if required > worksheet.row_count:
            worksheet.resize(rows=required)
    except Exception as e:
        print(f"⚠️ Không thể resize sheet: {e}")

def sync_mongodb_to_sheets():
    """Đồng bộ toàn bộ dữ liệu"""
    try:
        print("🔄 Đang đồng bộ dữ liệu...")
        worksheet = get_current_month_sheet()
        data_rows = get_mongo_data()

        clear_data_rows(worksheet)

        if data_rows:
            ensure_capacity(worksheet, len(data_rows))
            worksheet.update(data_rows, "A2", value_input_option="USER_ENTERED")
            print(f"✅ Đã ghi {len(data_rows)} dòng vào Google Sheets.")
        else:
            print("✅ Không có dữ liệu trong tháng này.")

        update_isChange(False)

    except Exception as e:
        print(f"❌ Lỗi đồng bộ: {e}")

def check_and_sync_if_needed():
    """Cứ 15s kiểm tra isChange, nếu True thì sync ngay"""
    try:
        status = status_collection.find_one({"_id": "sync_status"})
        if status and status.get("isChange", False):
            print("🚨 Phát hiện thay đổi, đồng bộ ngay...")
            sync_mongodb_to_sheets()
    except Exception as e:
        print(f"⚠️ Lỗi khi check isChange: {e}")

# Lên lịch chạy định kỳ mỗi 30 phút
schedule.every(30).minutes.do(sync_mongodb_to_sheets)
# Kiểm tra thay đổi mỗi 15 giây
schedule.every(30).seconds.do(check_and_sync_if_needed)

print("🚀 Bắt đầu đồng bộ: 30 phút/lần + check isChange mỗi 15s...")
while True:
    schedule.run_pending()
    time.sleep(1)
