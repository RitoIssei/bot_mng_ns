from db.initdb import mongo_manager
import logging

# Cấu hình logging
logger = logging.getLogger(__name__)

class ADSManager:
    _instance = None  # Singleton instance

    def __new__(cls, collection_name="ads"):
        """Singleton để đảm bảo chỉ có một instance ADSManager."""
        if cls._instance is None:
            cls._instance = super(ADSManager, cls).__new__(cls)
            cls._instance._initialize(collection_name)
        return cls._instance

    def _initialize(self, collection_name):
        """Khởi tạo kết nối với MongoDB và chọn collection từ MongoDBManager."""
        self.ads_collection = mongo_manager.get_collection(collection_name)
        self.collection_name = collection_name

    def switch_collection(self, new_collection):
        """Chuyển đổi collection trong khi chạy."""
        self.ads_collection = mongo_manager.get_collection(new_collection)
        self.collection_name = new_collection
        logger.info(f"🔄 Đã chuyển sang collection mới: {new_collection}")

    def add_ad(self, id_tele, username, name):
        """Thêm một quảng cáo mới vào database."""
        try:
            if self.ads_collection.find_one({"id_tele": id_tele}):
                logger.warning(f"⚠️ Quảng cáo với ID {id_tele} đã tồn tại.")
                return None

            ad_data = {
                "id_tele": id_tele,
                "username": username,
                "name": name
            }
            inserted_id = self.ads_collection.insert_one(ad_data).inserted_id
            logger.info(f"✅ Thêm quảng cáo mới thành công: {id_tele} - {username} - {name}")
            return inserted_id
        except Exception as e:
            logger.error(f"❌ Lỗi khi thêm quảng cáo: {e}")
            return None

    def get_all_ads(self):
        """Lấy danh sách tất cả quảng cáo."""
        try:
            ads = list(self.ads_collection.find({}, {"_id": 0}))
            return ads
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy danh sách quảng cáo: {e}")
            return []

    def get_ad_by_id(self, id_tele):
        """Lấy thông tin quảng cáo theo ID."""
        try:
            ad = self.ads_collection.find_one({"id_tele": id_tele}, {"_id": 0})
            return ad or None
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy thông tin quảng cáo: {e}")
            return None

    def load_ad_ids(self):
        """
        Lấy danh sách ID của các quảng cáo từ collection 'ads'.
    
        :return: Danh sách ID quảng cáo dưới dạng list hoặc rỗng nếu có lỗi
        """
        try:
            ad_ids = self.ads_collection.distinct("id_tele")
            return list(ad_ids)  # Trả về list thay vì set để tránh lỗi JSON serialization
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy danh sách quảng cáo từ ads: {e}")
            return []

ads_manager = ADSManager()