# decorators.py

from functools import wraps
from telegram import Update
from telegram.ext import CallbackContext
from config import ADMIN_IDS
import os
import logging
from db.rooms import RoomManager 
from db.troly import AssistantManager 
from db.ads import ADSManager 
import time

room_manager = RoomManager() 
assistant_manager= AssistantManager()
ads_manager= ADSManager()
# Thiết lập logging
logger = logging.getLogger(__name__)

CACHE_EXPIRATION = 300

def cache_data(context: CallbackContext, key: str, load_function):
    if key not in context.bot_data or not isinstance(context.bot_data[key], dict) or \
            time.time() - context.bot_data[key].get("timestamp", 0) > CACHE_EXPIRATION:
        data = load_function()
        if isinstance(data, set):
            data = list(data)
        context.bot_data[key] = {"data": data, "timestamp": time.time()}
        logging.info(f"🔄 Cache làm mới: key={key}, data={data}")
    else:
        logging.info(f"✅ Lấy từ cache: key={key}, data={context.bot_data[key]['data']}")
    return context.bot_data[key]["data"]


def troly_only(func):
    """Chỉ cho trợ lý hoặc admin sử dụng."""
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if update.edited_message:
           logger.info("Bỏ qua tin nhắn đã sửa.")
           return
        
        troly_ids = cache_data(context, 'troly_ids', assistant_manager.load_troly_ids)

        if user_id not in troly_ids and user_id not in ADMIN_IDS:
            await send_no_permission(update)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def ads_only(func):
    """Chỉ cho admin hoặc người quản lý quảng cáo sử dụng."""
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        if update.edited_message:
           logger.info("Bỏ qua tin nhắn đã sửa.")
           return
        user_id = update.effective_user.id
        ads_ids = cache_data(context, 'ads_ids', ads_manager.load_ad_ids)

        if user_id not in ads_ids and user_id not in ADMIN_IDS:
            await send_no_permission(update)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

def ads_only_rp(func):
    """Chỉ cho admin hoặc người quản lý quảng cáo sử dụng."""
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        if update.edited_message:
           logger.info("Bỏ qua tin nhắn đã sửa.")
           return
        message = update.message
        if not message:
            return
        text = message.text or message.caption  # Lấy nội dung tin nhắn hoặc caption

        # Kiểm tra nếu text không tồn tại hoặc không bắt đầu bằng "/rp"
        if not text or not text.startswith("/rp"):
            return  # Dừng xử lý ngay nếu không có "/rp"

        user_id = update.effective_user.id
        ads_ids = cache_data(context, 'ads_ids', ads_manager.load_ad_ids)

        if user_id not in ads_ids and user_id not in ADMIN_IDS:
            await send_no_permission(update)
            return

        return await func(update, context, *args, **kwargs)

    return wrapped

def allowed_room(func):
    """Chỉ cho phép bot xử lý lệnh trong nhóm được duyệt."""
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        chat_id = update.effective_chat.id
        allowed_rooms = cache_data(context, 'allowed_rooms', room_manager.get_all_room_ids)

        # Nếu `allowed_rooms` không phải là danh sách, thì chuyển đổi
        if not isinstance(allowed_rooms, list):
            allowed_rooms = list(allowed_rooms) if isinstance(allowed_rooms, set) else [allowed_rooms]

        if chat_id not in allowed_rooms:
            logging.error(f"❌ Chat ID {chat_id} không có trong allowed_rooms: {allowed_rooms}")
            await update.message.reply_text("Bot không hoạt động trong nhóm này.")
            return

        return await func(update, context, *args, **kwargs)
    return wrapped


def admin_only(func):
    """Chỉ admin có thể thực hiện lệnh."""
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id not in ADMIN_IDS:
            await send_no_permission(update)
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

async def send_no_permission(update: Update):
    """Gửi thông báo không có quyền."""
    try:
        if update.callback_query:
            await update.callback_query.answer("Bạn không có quyền thực hiện hành động này.", show_alert=True)
        elif update.message:
            await update.message.reply_text("❌ Bạn không có quyền thực hiện hành động này.")
    except Exception as e:
        logging.error(f"Lỗi khi gửi phản hồi quyền hạn: {e}")
        
def ads_or_troly_rp(func):
    """Chỉ cho admin, trợ lý, hoặc người quản lý quảng cáo sử dụng."""
    @wraps(func)
    async def wrapped(update: Update, context: CallbackContext, *args, **kwargs):
        if update.edited_message:
            logger.info("Bỏ qua tin nhắn đã sửa.")
            return

        message = update.message
        if not message:
            return
        text = message.text or message.caption  # Lấy nội dung tin nhắn hoặc caption

        # Nếu có text và bắt đầu bằng /rp thì mới kiểm tra ads_ids (giữ nguyên logic cũ của ads_only_rp)
        check_ads_rp = bool(text and text.startswith("/rp"))

        user_id = update.effective_user.id

        # Lấy danh sách từ cache
        troly_ids = cache_data(context, 'troly_ids', assistant_manager.load_troly_ids)
        ads_ids = cache_data(context, 'ads_ids', ads_manager.load_ad_ids)

        # Kiểm tra quyền (OR logic)
        if (
            user_id in ADMIN_IDS
            or user_id in troly_ids
            or (check_ads_rp and user_id in ads_ids)
        ):
            return await func(update, context, *args, **kwargs)

        # Nếu không có quyền
        await send_no_permission(update)
        return

    return wrapped