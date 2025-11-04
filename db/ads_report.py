import logging
import time
from db.initdb import mongo_manager
from bson import ObjectId

# Cấu hình logging
logger = logging.getLogger(__name__)

class AdsReportManager:
    _instance = None  # Singleton instance

    def __new__(cls, collection_name="ads_reports", status_collection="sync_status"):
        """Singleton để đảm bảo chỉ có một instance AdsReportManager."""
        if cls._instance is None:
            cls._instance = super(AdsReportManager, cls).__new__(cls)
            cls._instance._initialize(collection_name, status_collection)
        return cls._instance

    def _initialize(self, collection_name, status_collection):
        """Khởi tạo kết nối với MongoDB và chọn collection."""
        self.ads_report_collection = mongo_manager.get_collection(collection_name)
        self.status_collection = mongo_manager.get_collection(status_collection)
        self.collection_name = collection_name

    def update_isChange(self, status=True):
        """Cập nhật trạng thái isChange để thông báo có thay đổi dữ liệu"""
        try:
            self.status_collection.update_one(
                {"_id": "sync_status"},
                {"$set": {"isChange": status}},
                upsert=True  # Nếu chưa có thì tạo mới
            )
            logger.info(f"🔄 Đã cập nhật trạng thái isChange thành {status}")
        except Exception as e:
            logger.error(f"❌ Lỗi khi cập nhật trạng thái isChange: {e}")

    def save_ad_report(self, ad_ids, spend, ad_type, note, group_name, group_id, sender, ad_date, hold, mess_num, id_bc, confirmed_by):
        """Lưu dữ liệu vào MongoDB và cập nhật cờ isChange"""
        try:
            if not ad_date:
                raise ValueError("❌ Lỗi: `ad_date` không hợp lệ!")

            data = {
                "ad_ids": ad_ids,
                "spend": spend,
                "ad_type": ad_type,
                "note": note,
                "timestamp": time.time(),
                "group_name": group_name,
                "group_id": group_id,
                "sender": sender,
                "ad_date": ad_date,
                "hold": hold,
                "mess_num": mess_num,
                "id_bc": id_bc,
                "confirmed_by": confirmed_by,
            }
            
            result = self.ads_report_collection.insert_one(data)
            # self.update_isChange(True)  # Cập nhật trạng thái
            logger.info(f"✅ Đã lưu báo cáo quảng cáo ID: {result.inserted_id}")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"❌ Lỗi khi lưu báo cáo quảng cáo: {e}")
            return None

    def get_all_reports(self):
        """Lấy danh sách tất cả báo cáo quảng cáo."""
        try:
            return list(self.ads_report_collection.find({}, {"_id": 0}))
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy danh sách báo cáo quảng cáo: {e}")
            return []

    def get_report_by_id(self, report_id):
        """Lấy báo cáo theo ID (hỗ trợ ObjectId)"""
        try:
            return self.ads_report_collection.find_one({"_id": ObjectId(report_id)}, {"_id": 0})
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy báo cáo theo ID: {e}")
            return None

    def search_reports_by_name(self, ad_name):
        """Tìm kiếm báo cáo theo tên quảng cáo."""
        try:
            return list(self.ads_report_collection.find({"ad_name": {"$regex": ad_name, "$options": "i"}}, {"_id": 0}))
        except Exception as e:
            logger.error(f"❌ Lỗi khi tìm kiếm báo cáo quảng cáo: {e}")
            return []

    def delete_report(self, report_id):
        """Xóa báo cáo theo ID và cập nhật trạng thái isChange"""
        try:
            result = self.ads_report_collection.delete_one({"_id": ObjectId(report_id)})
            if result.deleted_count:
                # self.update_isChange(True)  # Cập nhật trạng thái
                logger.info(f"✅ Đã xóa báo cáo quảng cáo có ID: {report_id}")
                return f"✅ Đã xóa báo cáo quảng cáo với ID `{report_id}`"
            else:
                logger.warning(f"⚠️ Không tìm thấy báo cáo quảng cáo để xóa: {report_id}")
                return f"❌ Không tìm thấy báo cáo quảng cáo với ID `{report_id}`"
        except Exception as e:
            logger.error(f"❌ Lỗi khi xóa báo cáo quảng cáo: {e}")
            return "❌ Lỗi khi xóa báo cáo, vui lòng thử lại!"

class HoldManager:
    _instance = None  # Singleton

    def __new__(cls, collection_name="hold"):
        if cls._instance is None:
            cls._instance = super(HoldManager, cls).__new__(cls)
            cls._instance._initialize(collection_name)
        return cls._instance

    def _initialize(self, collection_name):
        """Khởi tạo kết nối với MongoDB và chọn collection hold."""
        self.collection = mongo_manager.get_collection(collection_name)
        self.collection_name = collection_name

    def save_hold(self, id_bc, ten_tele, hold, nguoi_hanh_dong):
        try:
            data = {
                "id_bc": id_bc,
                "ten_tele": ten_tele,
                "hold": hold,
                "nguoi_hanh_dong": nguoi_hanh_dong,
                "created_at": time.time()
            }
            result = self.collection.insert_one(data)
            logger.info(f"✅ Đã lưu HOLD với ID: {result.inserted_id}")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"❌ Lỗi khi lưu HOLD: {e}")
            return None
        
class NapTienManager:
    _instance = None  # Singleton

    def __new__(cls, collection_name="nap_tien"):
        if cls._instance is None:
            cls._instance = super(NapTienManager, cls).__new__(cls)
            cls._instance._initialize(collection_name)
        return cls._instance

    def _initialize(self, collection_name):
        """Khởi tạo kết nối với MongoDB và chọn collection nap_tien."""
        self.collection = mongo_manager.get_collection(collection_name)
        self.collection_name = collection_name

    def save_naptien(self, id_bc, ten_tele, so_tien_nap, nguoi_hanh_dong):
        try:
            data = {
                "id_bc": id_bc,
                "ten_tele": ten_tele,
                "so_tien_nap": so_tien_nap,
                "nguoi_hanh_dong": nguoi_hanh_dong,
                "created_at": time.time()
            }
            result = self.collection.insert_one(data)
            logger.info(f"✅ Đã lưu NẠP TIỀN với ID: {result.inserted_id}")
            return str(result.inserted_id)
        except Exception as e:
            logger.error(f"❌ Lỗi khi lưu NẠP TIỀN: {e}")
            return None
        

ads_reports_manager = AdsReportManager()
hold_manager = HoldManager()
nap_tien_manager = NapTienManager()