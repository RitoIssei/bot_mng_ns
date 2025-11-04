import sqlite3
import logging
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

# Khởi tạo cơ sở dữ liệu
def init_db(db_path="bot_data.db"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS confirmation_data (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            code TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        # Bảng pending_rp_data
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_rp_data (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        # Bảng pending_hold_data
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_hold_data (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        # Bảng pending_naptien_data
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS pending_naptien_data (
            id TEXT PRIMARY KEY,
            data TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        conn.commit()
        logger.info("Cơ sở dữ liệu đã được khởi tạo.")

# Thêm confirmation_id
def add_confirmation(id, data, code, created_at, db_path="bot_data.db"):
    data_json = json.dumps(data)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT INTO confirmation_data (id, data, code, created_at)
        VALUES (?, ?, ?, ?)
        """, (id, data_json, code, created_at))
        conn.commit()
        logger.info(f"Đã thêm confirmation_id: {id}")

# Lấy confirmation_id
def get_confirmation(id, db_path="bot_data.db"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        SELECT id, data, code, created_at FROM confirmation_data WHERE id = ?
        """, (id,))
        result = cursor.fetchone()
        if result:
            return {
                "id": result[0],
                "data": json.loads(result[1]),
                "code": result[2],
                "created_at": result[3]
            }
        return None

# Xóa confirmation_id
def delete_confirmation(id, db_path="bot_data.db"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        DELETE FROM confirmation_data WHERE id = ?
        """, (id,))
        conn.commit()
        logger.info(f"Đã xóa confirmation_id: {id}")

# Xóa các confirmation_id đã hết hạn
def cleanup_expired_confirmations(expiration_seconds=86400, db_path="bot_data.db"):
    try:
        expiration_time = (datetime.now() - timedelta(seconds=expiration_seconds)).isoformat()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM confirmation_data WHERE created_at < ?
            """, (expiration_time,))
            rows_deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Đã xóa {rows_deleted} confirmation_id hết hạn.")
    except Exception as e:
        logger.error(f"Lỗi khi dọn dẹp confirmation_id: {e}", exc_info=True)

def add_pending_rp(id, data, created_at, db_path="bot_data.db"):
    data_json = json.dumps(data)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO pending_rp_data (id, data, created_at)
        VALUES (?, ?, ?)
        """, (id, data_json, created_at))
        conn.commit()
        logger.info(f"Đã thêm pending_rp: {id}")

def get_pending_rp(id, db_path="bot_data.db"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM pending_rp_data WHERE id = ?", (id,))
        result = cursor.fetchone()
        if result:
            data = json.loads(result[0])
            # 🔹 Chỉ giữ các field hợp lệ
            return {
                "ad_ids": data.get("ad_ids"),
                "spend": data.get("spend"),
                "ad_type": data.get("ad_type"),
                "note": data.get("note"),
                "group_name": data.get("group_name"),
                "group_id": data.get("group_id"),
                "sender": data.get("sender"),
                "ad_date": data.get("ad_date"),
                "hold": data.get("hold"),
                "mess_num": data.get("mess_num"),
                "id_bc": data.get("id_bc"),
            }
        return None

def delete_pending_rp(id, db_path="bot_data.db"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_rp_data WHERE id = ?", (id,))
        conn.commit()
        logger.info(f"Đã xóa pending_rp: {id}")


# =========================
# pending_hold_data
# =========================
def add_pending_hold(id, data, created_at, db_path="bot_data.db"):
    data_json = json.dumps(data)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO pending_hold_data (id, data, created_at)
        VALUES (?, ?, ?)
        """, (id, data_json, created_at))
        conn.commit()
        logger.info(f"Đã thêm pending_hold: {id}")

def get_pending_hold(id, db_path="bot_data.db"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM pending_hold_data WHERE id = ?", (id,))
        result = cursor.fetchone()
        if result:
            data = json.loads(result[0])
            return {
                "id_bc": data.get("id_bc"),
                "hold": data.get("hold"),
                "ten_tele": data.get("ten_tele"),  
                # 👆 chỉ lưu tên tele ở bước này
                # KHÔNG có nguoi_hanh_dong ở đây
            }
        return None

def delete_pending_hold(id, db_path="bot_data.db"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_hold_data WHERE id = ?", (id,))
        conn.commit()
        logger.info(f"Đã xóa pending_hold: {id}")


# =========================
# pending_naptien_data
# =========================
def add_pending_naptien(id, data, created_at, db_path="bot_data.db"):
    data_json = json.dumps(data)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO pending_naptien_data (id, data, created_at)
        VALUES (?, ?, ?)
        """, (id, data_json, created_at))
        conn.commit()
        logger.info(f"Đã thêm pending_naptien: {id}")

def get_pending_naptien(id, db_path="bot_data.db"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT data FROM pending_naptien_data WHERE id = ?", (id,))
        result = cursor.fetchone()
        if result:
            data = json.loads(result[0])
            return {
                "id_bc": data.get("id_bc"),
                "so_tien_nap": data.get("so_tien_nap"),
                "ten_tele": data.get("ten_tele"),
                "ads": data.get("ads"),  # dùng để kiểm tra người confirm
            }
        return None

def delete_pending_naptien(id, db_path="bot_data.db"):
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_naptien_data WHERE id = ?", (id,))
        conn.commit()
        logger.info(f"Đã xóa pending_naptien: {id}")
        
# Xóa các pending_rp_data hết hạn
def cleanup_expired_rp(expiration_seconds=86400, db_path="bot_data.db"):
    try:
        expiration_time = (datetime.now() - timedelta(seconds=expiration_seconds)).isoformat()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM pending_rp_data WHERE created_at < ?
            """, (expiration_time,))
            rows_deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Đã xóa {rows_deleted} pending_rp_data hết hạn.")
    except Exception as e:
        logger.error(f"Lỗi khi dọn dẹp pending_rp_data: {e}", exc_info=True)


# Xóa các pending_hold_data hết hạn
def cleanup_expired_hold(expiration_seconds=86400, db_path="bot_data.db"):
    try:
        expiration_time = (datetime.now() - timedelta(seconds=expiration_seconds)).isoformat()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM pending_hold_data WHERE created_at < ?
            """, (expiration_time,))
            rows_deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Đã xóa {rows_deleted} pending_hold_data hết hạn.")
    except Exception as e:
        logger.error(f"Lỗi khi dọn dẹp pending_hold_data: {e}", exc_info=True)


# Xóa các pending_naptien_data hết hạn
def cleanup_expired_naptien(expiration_seconds=86400, db_path="bot_data.db"):
    try:
        expiration_time = (datetime.now() - timedelta(seconds=expiration_seconds)).isoformat()
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM pending_naptien_data WHERE created_at < ?
            """, (expiration_time,))
            rows_deleted = cursor.rowcount
            conn.commit()
            logger.info(f"Đã xóa {rows_deleted} pending_naptien_data hết hạn.")
    except Exception as e:
        logger.error(f"Lỗi khi dọn dẹp pending_naptien_data: {e}", exc_info=True)
