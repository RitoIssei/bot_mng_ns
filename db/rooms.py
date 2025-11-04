from db.initdb import mongo_manager
import config 
import logging
from bson.int64 import Int64

# Cấu hình logging
logger = logging.getLogger(__name__)

class RoomManager:
    _instance = None  # Singleton instance

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RoomManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """Khởi tạo kết nối với collection 'rooms'."""
        self.rooms_collection = mongo_manager.get_collection(config.ALLOW_ROOM)

    def add_room(self, id_room_chat, room_name, area_name):
        try:
            if self.rooms_collection.find_one({"id_room_chat": id_room_chat}):
                logger.warning(f"⚠️ Phòng với ID {id_room_chat} đã tồn tại.")
                return None
    
            room_data = {
                "id_room_chat": id_room_chat,
                "room_name": room_name,
                "area": area_name  # Chỉ thêm bản ghi trong khu vực hiện tại
            }
            inserted_id = self.rooms_collection.insert_one(room_data).inserted_id
            logger.info(f"✅ Thêm phòng mới thành công: {id_room_chat} - {room_name}")
            return inserted_id
        except Exception as e:
            logger.error(f"❌ Lỗi khi thêm phòng: {e}")
            return None
    

    def update_room(self, id_room_chat, new_room_name):
        try:
            result = self.rooms_collection.update_one(
                {"id_room_chat": id_room_chat},
                {"$set": {"room_name": new_room_name}}
            )
    
            if result.modified_count:
                logger.info(f"✅ Cập nhật phòng {id_room_chat} thành công: {new_room_name}")
            else:
                logger.warning(f"⚠️ Không tìm thấy phòng {id_room_chat} hoặc không có thay đổi.")
            return result.modified_count
        except Exception as e:
            logger.error(f"❌ Lỗi khi cập nhật phòng: {e}")
            return 0
    

    def delete_room(self, id_room_chat):
        try:
            result = self.rooms_collection.delete_one({"id_room_chat": id_room_chat})
            if result.deleted_count:
                logger.info(f"✅ Xoá phòng {id_room_chat} thành công.")
            else:
                logger.warning(f"⚠️ Không tìm thấy phòng {id_room_chat}.")
            return result.deleted_count
        except Exception as e:
            logger.error(f"❌ Lỗi khi xoá phòng: {e}")
            return 0
    
    
    def get_all_rooms(self):
        try:
            rooms = list(self.rooms_collection.find({}, {"_id": 0}))
            return rooms
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy danh sách phòng: {e}")
            return []
    
        
    def get_all_room_ids(self):
        """
        Lấy danh sách ID phòng chỉ trong khu vực hiện tại.
        """
        try:
            room_ids = self.rooms_collection.distinct("id_room_chat")
            return [room_id for room_id in room_ids if room_id is not None]
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy danh sách ID phòng: {e}")
            return []
    
        
    def get_room_by_id(self, id_room_chat):
        try:
            # Ép kiểu để đảm bảo trùng với MongoDB
            if isinstance(id_room_chat, str):
                try:
                    id_room_chat = int(id_room_chat)
                except ValueError:
                    logger.error(f"❌ ID không hợp lệ (không thể chuyển sang int): {id_room_chat}")
                    return None

            query = {"id_room_chat": Int64(id_room_chat)}  # 👈 ép kiểu Int64
            logger.debug(f"🔍 Truy vấn MongoDB với: {query}")

            room = self.rooms_collection.find_one(query, {"_id": 0})
            if room:
                logger.info(f"✅ Tìm thấy phòng: {room}")
                return room
            else:
                logger.warning(f"⚠️ Không tìm thấy phòng với ID {id_room_chat}.")
                return None
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy thông tin phòng: {e}")
            return None
        
    def get_room_by_name(self, name_room_chat):
        try:
            room = self.rooms_collection.find_one({"room_name": name_room_chat}, {"_id": 0})
            if room:
                return room
            else:
                logger.warning(f"⚠️ Không tìm thấy phòng với tên {name_room_chat}.")
                return None
        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy thông tin phòng trong khu vực: {e}")
            return None
    
        
room_manager = RoomManager()