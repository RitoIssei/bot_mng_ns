import config 
import logging
import time
import pytz
from bson import ObjectId
from db.initdb import mongo_manager
from ws_client import ws_client
import re
from handlers.ultils import generate_random_code, process_budget , format_number , safe_send_message , safe_edit_message , normalize_text , get_custom_today_epoch
from datetime import datetime, timezone, timedelta
import calendar
from db.rooms import RoomManager

room_manager = RoomManager()

# Cấu hình logging
logger = logging.getLogger(__name__)

class BudgetManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BudgetManager, cls).__new__(cls)
            cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        """Khởi tạo kết nối với collection 'budget' và 'budget_threshold' từ MongoDBManager."""
        self.budget_collection = mongo_manager.get_collection(config.BUDGET)
        self.threshold_collection = mongo_manager.get_collection(config.BUDGET_THRESHOLD)

    def add_budget(
        self,
        budget_id,
        team,
        contract_code,
        group_name,
        chat_id,
        amount,
        status,
        timestamp=None,
        assistant=None,
        note=None,
        end_time=None  # thêm tham số mới
    ):
        try:
            # Kiểm tra và chuyển đổi `amount` thành số nguyên
            try:
                amount = int(amount)
            except ValueError:
                logger.error(f"Invalid amount value: {amount}")
                return None
            
            # Dùng timestamp hiện tại nếu không có truyền vào
            ts = timestamp if timestamp else time.time()

            # 🔍 Lấy thông tin phòng để xác định khu vực
            room_info = room_manager.get_room_by_id(chat_id)
            if not room_info:
                logger.warning(f"⚠️ Không tìm thấy phòng với ID {chat_id}. Không thể xác định khu vực.")
                area_name = "unknown"
            else:
                area_name = room_info.get("area", "unknown")

            budget_data = {
                "budget_id": budget_id,
                "team": team.upper(),
                "contract_code": contract_code,
                "group_name": group_name,
                "amount": amount,
                "status": status,
                "timestamp": ts,
                "assistant": assistant,
                "note": note,
                "end_time": end_time if end_time is not None else 0,  # 👈 xử lý end_time
                "area": area_name  # Chỉ lưu bản ghi với area hiện tại
            }

            # Thêm dữ liệu vào MongoDB và lấy `_id`
            inserted = self.budget_collection.insert_one(budget_data)
            budget_data["_id"] = str(inserted.inserted_id)  # Chuyển `_id` thành chuỗi để tránh lỗi JSON
            budget_data["key"] = "budget"

            # Kiểm tra WebSocket trước khi gửi dữ liệu
            if ws_client and hasattr(ws_client, 'send_data'):
                ws_client.send_data(budget_data)
            else:
                logger.warning("WebSocket client is not available. Data was not sent.")

            logger.info(
                f"✅ Successfully added new budget: {budget_id} - {team.upper()} - {amount}"
            )
            return inserted.inserted_id

        except Exception as e:
            logger.error(f"❌ Error adding budget: {e}")
            return None

        
    def update_budget_status(self, budget_id):
        """
        Cập nhật trạng thái của tất cả bản ghi có `budget_id` trong cùng `area` từ "pending" thành "done".
        - Nếu timestamp > thời gian hiện tại → dùng timestamp làm end_time.
        - Ngược lại → dùng thời gian hiện tại (múi giờ VN).
        """
        try:
            query = {
                "budget_id": budget_id,
                "status": "pending"
            }

            pending_records = list(self.budget_collection.find(query))

            if not pending_records:
                logger.warning(f"⚠️ Không có bản ghi nào cần cập nhật với budget_id: {budget_id}")
                return 0

            updated_count = 0
            now_vn = datetime.now(timezone(timedelta(hours=7)))
            now_ts = int(now_vn.timestamp())

            for record in pending_records:
                ts = record.get("timestamp")
                if not ts:
                    continue

                # 🟢 Nếu thời gian hiện tại nhỏ hơn timestamp → lấy timestamp
                if now_ts < ts:
                    end_time = ts
                else:
                    end_time = now_ts

                # 🟢 Cập nhật bản ghi
                result = self.budget_collection.update_one(
                    {"_id": record["_id"]},
                    {"$set": {"status": "done", "end_time": end_time}}
                )

                if result.modified_count > 0:
                    updated_count += 1

                    # 🟢 Gửi qua WebSocket
                    updated_record = self.budget_collection.find_one(
                        {"_id": record["_id"]},
                        {"_id": 0}
                    )
                    if updated_record:
                        updated_record["key"] = "budget"
                        if ws_client and hasattr(ws_client, 'send_data'):
                            ws_client.send_data(updated_record)
                        else:
                            logger.warning("⚠️ WebSocket client is not available. Data was not sent.")

            logger.info(f"✅ Đã cập nhật {updated_count} bản ghi từ 'pending' thành 'done' với budget_id: {budget_id}")
            return updated_count

        except Exception as e:
            logger.error(f"❌ Lỗi khi cập nhật trạng thái budget: {e}")
            return 0

        
    def get_pending_budgets_by_id(self, budget_id):
        """
        Truy vấn tất cả các bản ghi có `budget_id` đang ở trạng thái `pending` trong khu vực hiện tại.
        :param budget_id: ID ngân sách cần tìm
        :return: Danh sách các bản ghi `pending`
        """
        try:
            query = {
                "budget_id": budget_id,
                "status": "pending"
            }
            pending_records = list(self.budget_collection.find(query))
    
            if not pending_records:
                logger.warning(f"⚠️ Không tìm thấy bản ghi `pending` nào với budget_id `{budget_id}`.")
            
            return pending_records
        except Exception as e:
            logger.error(f"❌ Lỗi khi truy vấn ngân sách pending: {e}")
            return []
       
        
    def update_budget(self, record_id, new_data):
        try:
            if not isinstance(new_data, dict):
                logger.error("❌ Dữ liệu cập nhật không hợp lệ, cần là dictionary.")
                return False
    
            if "amount" in new_data:
                try:
                    new_data["amount"] = int(new_data["amount"])
                except ValueError:
                    logger.error(f"❌ 'amount' không hợp lệ: {new_data['amount']}")
                    return False
    
            # Kiểm tra nếu record_id chưa phải ObjectId thì convert
            if not isinstance(record_id, ObjectId):
                try:
                    record_id = ObjectId(record_id)
                except Exception as e:
                    logger.error(f"❌ record_id không phải ObjectId hợp lệ: {record_id} - {e}")
                    return False
    
            # Cập nhật trong MongoDB
            result = self.budget_collection.update_one(
                {"_id": record_id},
                {"$set": new_data}
            )
    
            if result.modified_count:
                updated_data = self.budget_collection.find_one(
                    {"_id": record_id},
                    {"_id": 0}
                )
    
                if updated_data and ws_client and hasattr(ws_client, 'send_data'):
                    updated_data["key"] = "budget"
                    ws_client.send_data(updated_data)
                else:
                    logger.warning("⚠️ WebSocket không khả dụng, không gửi được dữ liệu.")
    
                logger.info(f"✅ Đã cập nhật bản ghi {record_id} thành công")
                return True
            else:
                logger.warning(f"⚠️ Không tìm thấy bản ghi {record_id} hoặc không có thay đổi.")
                return False
    
        except Exception as e:
            logger.error(f"❌ Lỗi khi cập nhật budget: {e}")
            return False
        
    @staticmethod
    def convert_to_contract_code(hd_code):
        """
        Chuyển đổi Mã HD sang contract_code nếu cần.
        - Nếu mã kết thúc bằng số, loại bỏ số cuối cùng (trừ khi kết thúc bằng "A10").
        :param hd_code: Mã HD đầu vào
        :return: contract_code chuẩn hóa
        """
        hd_code = hd_code.strip().upper()

        if hd_code.endswith(("A10", "9", "11", "1")):
            return hd_code

        if hd_code.startswith("F"):
            while hd_code and hd_code[-1].isdigit():
                hd_code = hd_code[:-1]
            return hd_code

        return hd_code
    
    def get_current_budget(self, contract_codes, team, chat_id ,is_prefix_search=False, current_timestamp=None):
        """
        Lấy tổng ngân sách hiện tại của danh sách contract_code từ MongoDB.
        Nếu hôm nay là ngày cuối tháng (theo giờ Việt Nam), thì lấy ngân sách của tháng sau.
        """
        try:
            # 🇻🇳 Giờ Việt Nam
            vn_tz = pytz.timezone("Asia/Ho_Chi_Minh")
            if current_timestamp:
                # Nếu timestamp truyền vào → convert sang datetime theo VN timezone
                now_vn = datetime.fromtimestamp(current_timestamp, tz=pytz.utc).astimezone(vn_tz)
            else:
                # Mặc định lấy thời điểm hiện tại
                now_vn = datetime.now(vn_tz)

            # 🟢 Kiểm tra nếu hôm nay là ngày cuối tháng (theo giờ VN)
            last_day = calendar.monthrange(now_vn.year, now_vn.month)[1]
            if now_vn.day == last_day:
                # 👉 Chuyển sang tháng sau
                if now_vn.month == 12:
                    next_month = datetime(now_vn.year + 1, 1, 1, tzinfo=vn_tz)
                else:
                    next_month = datetime(now_vn.year, now_vn.month + 1, 1, tzinfo=vn_tz)
                first_day_of_month_vn = next_month
            else:
                first_day_of_month_vn = datetime(now_vn.year, now_vn.month, 1, tzinfo=vn_tz)

            # 🟢 Ngày cuối tháng theo giờ VN
            year = first_day_of_month_vn.year
            month = first_day_of_month_vn.month
            last_day_of_target_month = calendar.monthrange(year, month)[1]
            last_day_of_month_vn = datetime(year, month, last_day_of_target_month, 23, 59, 59, tzinfo=vn_tz)

            # 👉 Chuyển sang UTC để truy vấn theo timestamp (Mongo lưu UTC)
            timestamp_start = int(first_day_of_month_vn.astimezone(pytz.utc).timestamp())
            timestamp_end = int(last_day_of_month_vn.astimezone(pytz.utc).timestamp())

            if is_prefix_search:
                prefix = contract_codes[0]
                contract_code_query = {
                    "$in": [prefix, prefix + '9', prefix + '10', prefix + '11']
                }
            else:
                logger.info(f"Ngân sách hiện: {contract_codes}")
                
                contract_code_query = {
                    "$in": contract_codes
                }
            # 🔍 Lấy thông tin phòng để xác định khu vực
            room_info = room_manager.get_room_by_name(chat_id)
            if not room_info:
                logger.warning(f"⚠️ Không tìm thấy phòng với ID {chat_id}. Không thể xác định khu vực.")
                area_name = "unknown"
            else:
                area_name = room_info.get("area", "unknown")
                
            query = {
                "contract_code": contract_code_query,
                "area": area_name,
                "team": team,
                "timestamp": {"$gte": timestamp_start, "$lte": timestamp_end}
            }

            pipeline = [
                {"$match": query},
                {"$group": {
                    "_id": "$contract_code",
                    "total_amount": {"$sum": "$amount"}
                }}
            ]

            records = self.budget_collection.aggregate(pipeline)
            current_budgets = {record["_id"]: record["total_amount"] for record in records}

            logger.info(f"📊 Ngân sách tổng hợp: {current_budgets}")
            return current_budgets

        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy tổng ngân sách: {e}")
            return {}
        
    
    def get_limit_by_key(self, key: str):
        """
        Lấy thông tin giới hạn ngân sách (limit) theo key từ collection 'budget_limits'.
        :param key: tên key (ví dụ 'HD1', 'HD9', ...)
        :return: dict chứa thông tin limit hoặc None nếu không tìm thấy
        """
        try:
            if not key:
                raise ValueError("Key không được để trống")

            record = self.threshold_collection.find_one({"key": key})

            if record:
                return {
                    "key": record.get("key"),
                    "limit": record.get("limit"),
                    "updated_at": record.get("updated_at"),
                }

            logger.warning(f"⚠️ Không tìm thấy limit cho key: {key}")
            return None

        except Exception as e:
            logger.error(f"❌ Lỗi khi lấy limit theo key '{key}': {e}")
            return None


budget_manager = BudgetManager()