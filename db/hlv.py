from db.initdb import mongo_manager
import config 
import logging

# Cấu hình logging
logger = logging.getLogger(__name__)

class Manager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Manager, cls).__new__(cls)
            cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        """Khởi tạo kết nối với collection 'quan_ly'."""
        self.manager_collection = mongo_manager.get_collection(config.HLV)

    def add_manager(self, id_tele, username, name):
        try:
            if self.manager_collection.find_one({"id_tele": id_tele, "area": config.AREA_NAME}):
                logger.warning(f"Quản lý với ID {id_tele} đã tồn tại trong khu vực {config.AREA_NAME}.")
                return None
            
            manager_data = {
                "id_tele": id_tele,
                "username": username,
                "name": name,
                "area": config.AREA_NAME  # Chỉ thêm bản ghi với area hiện tại
            }
            inserted_id = self.manager_collection.insert_one(manager_data).inserted_id
            logger.info(f"Thêm quản lý mới thành công: {id_tele} - {username} - {name} trong khu vực {config.AREA_NAME}")
            return inserted_id
        except Exception as e:
            logger.error(f"Lỗi khi thêm quản lý: {e}")
            return None
    

    def update_manager(self, id_tele, new_username, new_name):
        try:
            result = self.manager_collection.update_one(
                {"id_tele": id_tele, "area": config.AREA_NAME},  # Chỉ cập nhật nếu thuộc khu vực hiện tại
                {"$set": {"username": new_username, "name": new_name}}
            )
            
            if result.modified_count:
                logger.info(f"Cập nhật quản lý {id_tele} thành công: {new_username} - {new_name} trong khu vực {config.AREA_NAME}")
            else:
                logger.warning(f"Không tìm thấy quản lý {id_tele} hoặc không có thay đổi trong khu vực {config.AREA_NAME}.")
            return result.modified_count
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật quản lý: {e}")
            return 0
    

    def delete_manager(self, id_tele):
        try:
            result = self.manager_collection.delete_one({"id_tele": id_tele, "area": config.AREA_NAME})
            if result.deleted_count:
                logger.info(f"Xoá quản lý {id_tele} thành công trong khu vực {config.AREA_NAME}.")
            else:
                logger.warning(f"Không tìm thấy quản lý {id_tele} trong khu vực {config.AREA_NAME}.")
            return result.deleted_count
        except Exception as e:
            logger.error(f"Lỗi khi xoá quản lý: {e}")
            return 0
    

    def get_all_managers(self):
        try:
            managers = list(self.manager_collection.find({"area": config.AREA_NAME}, {"_id": 0}))
            return managers
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách quản lý trong khu vực {config.AREA_NAME}: {e}")
            return []
    
    
    def load_hlv_ids(self):
        try:
            hlv_ids = self.manager_collection.distinct("id_tele", {"area": config.AREA_NAME})
            return [hlv_id for hlv_id in hlv_ids if hlv_id is not None]
        except Exception as e:
            logger.error(f"Lỗi khi lấy danh sách HLV từ khu vực {config.AREA_NAME}: {e}")
            return []
    
        
    def get_manager_by_id(self, id_tele):
        """Lấy thông tin quản lý dựa trên id_tele trong khu vực hiện tại."""
        try:
            manager = self.manager_collection.find_one({"id_tele": id_tele, "area": config.AREA_NAME}, {"_id": 0})
            if manager:
                return manager
            else:
                logger.warning(f"Không tìm thấy quản lý với ID {id_tele} trong khu vực {config.AREA_NAME}.")
                return None
        except Exception as e:
            logger.error(f"Lỗi khi lấy thông tin quản lý trong khu vực {config.AREA_NAME}: {e}")
            return None
    
        
manager = Manager()