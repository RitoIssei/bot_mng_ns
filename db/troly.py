from db.initdb import mongo_manager
import config 
import logging

# Cấu hình logging
logger = logging.getLogger(__name__)

class AssistantManager:
    _instance = None  # Singleton instance

    def __new__(cls, collection_name="tro_ly"):
        """Singleton để đảm bảo chỉ có một instance AssistantManager."""
        if cls._instance is None:
            cls._instance = super(AssistantManager, cls).__new__(cls)
            cls._instance._initialize(collection_name)
        return cls._instance

    def _initialize(self, collection_name):
        """Khởi tạo kết nối với MongoDB và chọn collection."""
        self.assistant_collection = mongo_manager.get_collection(collection_name)
        self.collection_name = collection_name

    def switch_collection(self, new_collection):
        """Chuyển đổi collection trong khi chạy."""
        self.assistant_collection = self.db.client[config.DB_NAME][new_collection]
        self.collection_name = new_collection

    def add_assistant(self, id_tele, username, name):
        """Thêm một trợ lý mới vào database."""
        try:
            if self.assistant_collection.find_one({"id_tele": id_tele}):
                logger.warning(f"⚠️ Trợ lý với ID {id_tele} đã tồn tại.")
                return None

            assistant_data = {
                "id_tele": id_tele,
                "username": username,
                "name": name
            }
            inserted_id = self.assistant_collection.insert_one(assistant_data).inserted_id
            logger.info(f"✅ Thêm trợ lý mới thành công: {id_tele} - {username} - {name}")
            return inserted_id
        except Exception as e:
            logger.error(f"❌ Lỗi khi thêm trợ lý: {e}")
            return None

    def get_all_assistants(self):
        """Lấy danh sách tất cả trợ lý."""
        try:
            assistants = list(self.assistant_collection.find({}, {"_id": 0}))
            return assistants
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy danh sách trợ lý: {e}")
            return []

    def get_assistant_by_id(self, id_tele):
        """Lấy thông tin trợ lý theo ID Telegram."""
        try:
            assistant = self.assistant_collection.find_one({"id_tele": id_tele}, {"_id": 0})
            return assistant or None
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy thông tin trợ lý: {e}")
            return None
        
    def load_troly_ids(self):
        """
        Lấy danh sách ID của các trợ lý từ collection 'tro_ly'.
    
        :return: Danh sách ID trợ lý dưới dạng list hoặc rỗng nếu có lỗi
        """
        try:
            troly_ids = self.assistant_collection.distinct("id_tele")
            return list(troly_ids)  # Trả về list thay vì set để tránh lỗi JSON serialization
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy danh sách trợ lý từ tro_ly: {e}")
            return []

assistant_manager = AssistantManager()