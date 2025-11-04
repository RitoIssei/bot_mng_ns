import time
import schedule
import pymongo
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timezone, timedelta
import sys, io

# Ghi đè sys.stdout và stderr để dùng UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# --- Config ---
MONGO_URI = "mongodb://localhost:27017/BudgetManager"
DB_NAME = "BudgetManager"
STATUS_COLLECTION = "sync_status"
SPREADSHEET_ID = "1zQQMLoDtbBRwqFQvkzj9_90OUAah4Efa6fKEf42NYDA"
GOOGLE_CRED = "./assets/google.json"
VN_TZ = timezone(timedelta(hours=7))
ADSREPORT_COLLECTION = "ads_reports"
NAPTIEN_COLLECTION = "nap_tien"
HOLD_COLLECTION = "hold"

# --- Kết nối Mongo ---
client = pymongo.MongoClient(MONGO_URI)
db = client[DB_NAME]
status_collection = db[STATUS_COLLECTION]
col_adsreport = db[ADSREPORT_COLLECTION]
col_naptien = db[NAPTIEN_COLLECTION]
col_hold = db[HOLD_COLLECTION]

# --- Kết nối Google Sheets ---
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CRED, scope)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SPREADSHEET_ID)

# --- Helper: Tính mốc thời gian 2 tháng trước ---
def get_two_months_ago():
    dt = datetime.now(VN_TZ) - timedelta(days=60)
    return dt.timestamp()

# ======== CÁC HÀM XUẤT ========

def export_ads_report():
    ws = sheet.worksheet("BÁO CÁO THẤT LẠC")
    ws.batch_clear(["A3:E"])
    data = []

    two_months_ago = get_two_months_ago()

    for doc in col_adsreport.find({
        "lost": True,
        "timestamp": {"$gte": two_months_ago}
    }).sort("timestamp", -1):
        ad_ids = doc.get("ad_ids", [])
        for ad_id in ad_ids:
            data.append([
                str(doc.get("_id", "")),
                doc.get("ad_date", ""),
                doc.get("id_bc", ""),
                ad_id,
                doc.get("spend", 0)
            ])

    if data:
        ws.update(data, "A3")
    print(f"✅ AdsReport: ghi {len(data)} dòng.")


def export_nap_tien():
    ws = sheet.worksheet("NẠP TIỀN THẤT LẠC")
    ws.batch_clear(["A3:D"])
    data = []

    two_months_ago = get_two_months_ago()

    for doc in col_naptien.find({
        "lost": True,
        "created_at": {"$gte": two_months_ago}
    }).sort("timestamp", -1):
        created_at = doc.get("created_at")
        if created_at:
            # Nếu là float (timestamp) → chuyển sang datetime
            if isinstance(created_at, (float, int)):
                created_at = datetime.fromtimestamp(created_at, tz=VN_TZ)
            # Lùi 1 ngày và định dạng dd/MM
            date_str = (created_at - timedelta(days=1)).strftime("%d/%m")
        else:
            date_str = ""
            
        data.append([
            str(doc.get("_id", "")),
            doc.get("id_bc", ""),
            doc.get("so_tien_nap", 0),
            date_str
        ])

    if data:
        ws.update(data, "A3")
    print(f"✅ NapTien: ghi {len(data)} dòng.")


def export_hold():
    ws = sheet.worksheet("HOLD THẤT LẠC")
    ws.batch_clear(["A3:D"])
    data = []

    two_months_ago = get_two_months_ago()

    for doc in col_hold.find({
        "lost": True,
        "created_at": {"$gte": two_months_ago}
    }).sort("timestamp", -1):
        created_at = doc.get("created_at")
        if created_at:
            if isinstance(created_at, (float, int)):
                created_at = datetime.fromtimestamp(created_at, tz=VN_TZ)
            date_str = (created_at - timedelta(days=1)).strftime("%d/%m")
        else:
            date_str = ""
            
        data.append([
            str(doc.get("_id", "")),
            doc.get("id_bc", ""),
            doc.get("hold", 0),
            date_str
        ])

    if data:
        ws.update(data, "A3")
    print(f"✅ Hold: ghi {len(data)} dòng.")


def update_isChange(status):
    status_collection.update_one({"_id": "sync_status"}, {"$set": {"isChange": status}}, upsert=True)


def sync_lost_to_sheets():
    try:
        print("🔄 Bắt đầu đồng bộ dữ liệu thất lạc...")
        export_ads_report()
        export_nap_tien()
        export_hold()
        # update_isChange(False)
        print(f"🎯 Hoàn tất xuất dữ liệu {datetime.now(VN_TZ).strftime('%H:%M:%S')}")
    except Exception as e:
        print(f"❌ Lỗi đồng bộ: {e}")


def check_and_sync_if_needed():
    """Cứ 15s kiểm tra flag isChange"""
    try:
        status = status_collection.find_one({"_id": "sync_status"})
        if status and status.get("isChange", False):
            print("🚨 Phát hiện thay đổi, đồng bộ ngay...")
            sync_lost_to_sheets()
    except Exception as e:
        print(f"⚠️ Lỗi khi check isChange: {e}")


# ======== LÊN LỊCH ========

schedule.every(30).minutes.do(sync_lost_to_sheets)
schedule.every(15).seconds.do(check_and_sync_if_needed)

print("🚀 Bắt đầu: Đồng bộ thất lạc mỗi 3 phút + check isChange mỗi 15s...")

while True:
    schedule.run_pending()
    time.sleep(1)
