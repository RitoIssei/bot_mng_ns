import time
import logging
from pymongo import MongoClient, errors
import config

# Cấu hình logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MongoDBManager:
    _instance = None

    def __new__(cls):
        """Triển khai Singleton để chỉ có một kết nối duy nhất"""
        if cls._instance is None:
            cls._instance = super(MongoDBManager, cls).__new__(cls)
            cls._instance._init_db()
        return cls._instance

    def _init_db(self, max_retries=5, retry_delay=3):
        """Tạo một kết nối MongoDB duy nhất với cơ chế thử lại"""
        retries = 0
        while retries < max_retries:
            try:
                self.client = MongoClient(config.MONGO_URI, maxPoolSize=50, serverSelectionTimeoutMS=5000)
                self.db = self.client[config.DB_NAME]
                self.client.admin.command("ping")  # Kiểm tra kết nối
                logger.info("🔗 Kết nối MongoDB thành công!")
                return
            except errors.ServerSelectionTimeoutError as e:
                retries += 1
                logger.warning(f"⚠️ Lỗi kết nối MongoDB ({retries}/{max_retries}): {e}")
                time.sleep(retry_delay)

        logger.error("❌ Không thể kết nối đến MongoDB sau nhiều lần thử.")
        raise ConnectionError("Không thể kết nối đến MongoDB.")

    def get_collection(self, collection_name):
        """Lấy collection từ kết nối MongoDB đã mở"""
        return self.db[collection_name]

# Khởi tạo MongoDB Manager
mongo_manager = MongoDBManager()
