from db.initdb import mongo_manager
import config
import logging
from datetime import datetime
from db.rooms import RoomManager

room_manager = RoomManager()
# Cấu hình logging
logger = logging.getLogger(__name__)

class NoteManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(NoteManager, cls).__new__(cls)
            cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        """Khởi tạo kết nối với collection 'notes'."""
        self.note_collection = mongo_manager.get_collection('notes')

    def add_note(self, chat_title, note_type, timestamp, note_content, assistant, chat_id):
        """
        Lưu ghi chú vào MongoDB.
        :param chat_title: Tên nhóm chat
        :param note_type: Loại ghi chú (DTN, TC, NB)
        :param timestamp: Thời gian ghi chú
        :param note_content: Nội dung ghi chú
        :param assistant: Người tạo ghi chú
        :return: ID của ghi chú được thêm vào hoặc None nếu thất bại
        """
        
        room_info = room_manager.get_room_by_id(chat_id)

        if not room_info:
            logger.warning(f"⚠️ Không tìm thấy phòng với ID {chat_id}. Không thể xác định khu vực.")
            area_name = "unknown"
        else:
            area_name = room_info.get("area", "unknown")
            
        try:
            note_data = {
                "chat_title": chat_title,
                "note_type": note_type,
                "timestamp": timestamp,
                "note_content": note_content,
                "assistant": assistant,
                "area": area_name
            }
            inserted_id = self.note_collection.insert_one(note_data).inserted_id
            logger.info(f"Thêm ghi chú thành công vào MongoDB: {note_data}")
            return inserted_id
        except Exception as e:
            logger.error(f"Lỗi khi thêm ghi chú vào MongoDB: {e}")
            return None

    def delete_old_notes(self, days=5):
        """
        Xóa các ghi chú đã quá số ngày quy định (mặc định là 5 ngày).
        """
        try:
            now = datetime.now()
            cutoff_date = now.timestamp() - (days * 86400)  # 5 ngày trước

            result = self.note_collection.delete_many({"timestamp": {"$lt": cutoff_date}})
            logger.info(f"Đã xóa {result.deleted_count} ghi chú cũ quá {days} ngày.")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Lỗi khi xóa ghi chú cũ: {e}")
            return 0

# Khởi tạo NoteManager
note_manager = NoteManager()
