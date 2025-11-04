import decorators
import logging
import os

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import CallbackContext
from db.rooms import room_manager
from db.troly import assistant_manager
from db.hlv import manager
from db.ads import ads_manager

# Thiết lập logging
logger = logging.getLogger(__name__)


@decorators.troly_only
async def add_room(update: Update, context: CallbackContext):
    """Handler cho lệnh /addroom để thêm một nhóm mới vào danh sách"""
    try:
        chat = update.effective_chat
        chat_id = chat.id
        group_name = chat.title

        if chat.type not in ['group', 'supergroup']:
            await update.message.reply_text("Lệnh này chỉ có thể được sử dụng trong các nhóm hoặc supergroup.")
            logger.info(f"Người dùng từ nhóm không phải là group hoặc supergroup: chat_id={chat_id}")
            return

        # Kiểm tra xem phòng đã tồn tại chưa
        existing_room = room_manager.get_room_by_id(chat_id)
        if existing_room:
            await update.message.reply_text("Nhóm này đã tồn tại trong danh sách.")
            logger.info(f"Nhóm đã tồn tại: chat_id={chat_id}")
            return

        # Thêm phòng mới vào database
        result = room_manager.add_room(chat_id, group_name)
        if result:
            await update.message.reply_text(f"✅ Thêm nhóm thành công:\nID: {chat_id}\nTên: {group_name}")
            logger.info(f"Thêm nhóm mới thành công: ID={chat_id}, Tên={group_name}")
        else:
            await update.message.reply_text("❌ Lỗi khi thêm nhóm vào database.")
            logger.error(f"Lỗi khi thêm nhóm: chat_id={chat_id}, tên={group_name}")

        # Cập nhật cache, đảm bảo luôn là danh sách
        if 'allowed_rooms' not in context.bot_data:
            context.bot_data['allowed_rooms'] = []

        if isinstance(context.bot_data['allowed_rooms'], list):
            if chat_id not in context.bot_data['allowed_rooms']:
                context.bot_data['allowed_rooms'].append(chat_id)
        else:
            logger.warning("allowed_rooms không phải là danh sách, reset lại thành list.")
            context.bot_data['allowed_rooms'] = [chat_id]

        logger.debug(f"Cập nhật cache 'allowed_rooms' với chat_id={chat_id}")

    except Exception as e:
        logger.error(f"Lỗi trong hàm add_room: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")


@decorators.troly_only
@decorators.allowed_room
async def remove_room(update: Update, context: CallbackContext):
    """Handler cho lệnh /removeroom để xóa một nhóm khỏi danh sách"""
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text("Sử dụng: /removeroom <chat_id>")
            return
        
        chat_id_str = args[0]
        if not (chat_id_str.startswith('-') and chat_id_str[1:].isdigit()):
            await update.message.reply_text("❌ chat_id không hợp lệ. Đảm bảo rằng nó bắt đầu bằng '-' và chỉ chứa số.")
            return

        chat_id = int(chat_id_str)

        # Kiểm tra xem nhóm có tồn tại không
        existing_room = room_manager.get_room_by_id(chat_id)
        if not existing_room:
            await update.message.reply_text("❌ Không tìm thấy nhóm với chat_id này.")
            return
        
        group_name = existing_room.get("room_name", "Unknown")

        # Xóa nhóm khỏi database
        delete_result = room_manager.delete_room(chat_id)
        if delete_result:
            await update.message.reply_text(f"✅ Đã xóa nhóm:\nID: {chat_id}\nTên: {group_name}")
            logger.info(f"Xóa nhóm thành công: ID={chat_id}, Tên={group_name}")

            # Cập nhật cache nếu có
            if 'allowed_rooms' in context.bot_data:
                context.bot_data['allowed_rooms'].remove(chat_id)
                logger.debug(f"Cập nhật cache 'allowed_rooms' sau khi xóa chat_id={chat_id}")
        else:
            await update.message.reply_text("❌ Lỗi khi xóa nhóm khỏi database.")
            logger.error(f"Lỗi khi xóa nhóm: ID={chat_id}, Tên={group_name}")

    except Exception as e:
        logger.error(f"Lỗi trong hàm remove_room: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")


@decorators.troly_only
@decorators.allowed_room
async def list_rooms(update: Update, context: CallbackContext):
    """Handler cho lệnh /listrooms để hiển thị danh sách các nhóm được phép"""
    try:
        rooms = room_manager.get_all_rooms()  # Lấy danh sách từ database
        
        if not rooms:
            await update.message.reply_text("❌ Hiện không có nhóm nào được phép.")
            return

        # Tạo danh sách hiển thị
        message = "*📌 Danh sách các nhóm được phép:*\n"
        for room in rooms:
            chat_id = room.get("id_room_chat")
            group_name = room.get("room_name", "Không xác định")
            message += f"- *ID:* `{chat_id}`  |  *Tên:* {group_name}\n"

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        logger.info("Đã liệt kê danh sách rooms.")
        
    except Exception as e:
        logger.error(f"Lỗi trong hàm list_rooms: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")

@decorators.admin_only
async def add_troly(update: Update, context: CallbackContext):
    """Thêm một trợ lý mới vào danh sách"""
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Sử dụng: /addtroly <ID> [@username] <Tên Tele>")
            return

        troly_id = args[0]
        if not troly_id.isdigit():
            await update.message.reply_text("❌ ID phải là số.")
            return
        troly_id = int(troly_id)

        if args[1].startswith('@'):
            username = args[1]
            tele_name = ' '.join(args[2:]) if len(args) > 2 else ''
        else:
            username = ''
            tele_name = ' '.join(args[1:]) if len(args) > 1 else ''

        # Kiểm tra xem trợ lý đã tồn tại chưa
        existing_troly = assistant_manager.get_assistant_by_id(troly_id)
        if existing_troly:
            await update.message.reply_text("❌ Trợ lý với ID này đã tồn tại.")
            return

        # Thêm trợ lý vào database
        result = assistant_manager.add_assistant(troly_id, username, tele_name)
        if result:
            await update.message.reply_text("✅ Thêm trợ lý thành công.")
            logger.info(f"Thêm trợ lý mới: ID={troly_id}, Username={username}, Tên Tele={tele_name}")
        else:
            await update.message.reply_text("❌ Lỗi khi thêm trợ lý vào database.")
            logger.error(f"Lỗi khi thêm trợ lý: ID={troly_id}, Username={username}, Tên Tele={tele_name}")

    except Exception as e:
        logger.error(f"❌ Lỗi trong hàm add_troly: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")

@decorators.admin_only
async def remove_troly(update: Update, context: CallbackContext):
    """Xóa một trợ lý khỏi danh sách"""
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text("Sử dụng: /removetroly <ID>")
            return

        troly_id = args[0]
        if not troly_id.isdigit():
            await update.message.reply_text("❌ ID phải là số.")
            return
        troly_id = int(troly_id)

        # Kiểm tra xem trợ lý có tồn tại không
        existing_troly = assistant_manager.get_assistant_by_id(troly_id)
        if not existing_troly:
            await update.message.reply_text("❌ Trợ lý với ID này không tồn tại.")
            return

        # Xóa trợ lý khỏi database
        delete_result = assistant_manager.delete_assistant(troly_id)
        if delete_result:
            await update.message.reply_text("✅ Xóa trợ lý thành công.")
            logger.info(f"Xóa trợ lý: ID={troly_id}")
        else:
            await update.message.reply_text("❌ Lỗi khi xóa trợ lý khỏi database.")
            logger.error(f"Lỗi khi xóa trợ lý: ID={troly_id}")

    except Exception as e:
        logger.error(f"❌ Lỗi trong hàm remove_troly: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")

@decorators.admin_only
async def list_troly(update: Update, context: CallbackContext):
    """Liệt kê danh sách trợ lý"""
    try:
        troly_list = assistant_manager.get_all_assistants()
        if not troly_list:
            await update.message.reply_text("❌ Chưa có trợ lý nào.")
            return

        message = "*📌 Danh sách trợ lý:*\n"
        for t in troly_list:
            msg = f"- *ID:* `{t['id_tele']}`"
            if t.get("username"):
                msg += f"  |  *Username:* {t['username']}"
            if t.get("name"):
                msg += f"  |  *Tên Tele:* {t['name']}"
            message += msg + "\n"

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        logger.info("Đã liệt kê danh sách trợ lý.")

    except Exception as e:
        logger.error(f"❌ Lỗi trong hàm list_troly: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")

@decorators.admin_only
async def add_hlv(update: Update, context: CallbackContext):
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Sử dụng: /addhlv <ID> [@username] <Tên Tele>")
            return

        hlv_id = args[0]
        if not hlv_id.isdigit():
            await update.message.reply_text("ID phải là số.")
            return
        hlv_id = int(hlv_id)

        username = args[1] if args[1].startswith('@') else ''
        tele_name = ' '.join(args[2:]) if len(args) > 2 else (' '.join(args[1:]) if not username else '')

        # Kiểm tra xem ID đã tồn tại trong DB chưa
        existing_manager = manager.get_manager_by_id(hlv_id)
        if existing_manager:
            await update.message.reply_text("HLV với ID này đã tồn tại.")
            return

        inserted_id = manager.add_manager(hlv_id, username, tele_name)
        if inserted_id:
            await update.message.reply_text("Thêm HLV thành công.")
            logger.info(f"Thêm HLV mới: ID={hlv_id}, Username={username}, Tên Tele={tele_name}")
        else:
            await update.message.reply_text("Có lỗi xảy ra khi thêm HLV.")
    except Exception as e:
        logger.error(f"Lỗi trong hàm add_hlv: {e}")
        await update.message.reply_text(f"Lỗi: {e}")

@decorators.admin_only
async def remove_hlv(update: Update, context: CallbackContext):
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text("Sử dụng: /rmhlv <ID>")
            return

        hlv_id = args[0]
        if not hlv_id.isdigit():
            await update.message.reply_text("ID phải là số.")
            return
        hlv_id = int(hlv_id)

        # Kiểm tra xem HLV có tồn tại trước khi xóa
        existing_manager = manager.get_manager_by_id(hlv_id)
        if not existing_manager:
            await update.message.reply_text("Không tìm thấy hlv với ID này.")
            return

        deleted_count = manager.delete_manager(hlv_id)
        if deleted_count:
            await update.message.reply_text("Xóa HLV thành công.")
            logger.info(f"Xóa HLV: ID={hlv_id}")
        else:
            await update.message.reply_text("Có lỗi xảy ra khi xóa HLV.")
    except Exception as e:
        logger.error(f"Lỗi trong hàm remove_hlv: {e}")
        await update.message.reply_text(f"Lỗi: {e}")

@decorators.admin_only
async def list_hlv(update: Update, context: CallbackContext):
    try:
        hlv_list = manager.get_all_managers()
        if not hlv_list:
            await update.message.reply_text("Chưa có hlv nào.")
            return

        message = "Danh sách hlv:\n"
        for hlv in hlv_list:
            msg = f"ID: {hlv['id_tele']}"
            if hlv.get('username'):
                msg += f", Username: {hlv['username']}"
            if hlv.get('name'):
                msg += f", Tên Tele: {hlv['name']}"
            message += msg + "\n"

        await update.message.reply_text(message, parse_mode=ParseMode.MARKDOWN)
        logger.info("Liệt kê các hlv.")
    except Exception as e:
        logger.error(f"Lỗi trong hàm list_hlv: {e}")
        await update.message.reply_text(f"Lỗi: {e}")

@decorators.admin_only
async def add_ad(update: Update, context: CallbackContext):
    """Thêm một quảng cáo mới vào danh sách"""
    try:
        args = context.args
        if len(args) < 2:
            await update.message.reply_text("Sử dụng: /addad <ID> [@username] <Tên]")
            return

        id_tele = args[0]
        if not id_tele.isdigit():
            await update.message.reply_text("❌ ID phải là số.")
            return
        id_tele = int(id_tele)

        username = args[1] if args[1].startswith('@') else ''
        name = ' '.join(args[2:]) if len(args) > 2 else (' '.join(args[1:]) if not username else '')

        # Kiểm tra xem quảng cáo đã tồn tại chưa
        existing_ad = ads_manager.get_ad_by_id(id_tele)
        if existing_ad:
            await update.message.reply_text("❌ Quảng cáo với ID này đã tồn tại.")
            return

        # Thêm quảng cáo vào database
        result = ads_manager.add_ad(id_tele, username, name)
        if result:
            await update.message.reply_text("✅ Thêm quảng cáo thành công.")
            logger.info(f"Thêm quảng cáo mới: ID={id_tele}, Username={username}, Tên={name}")
        else:
            await update.message.reply_text("❌ Lỗi khi thêm quảng cáo vào database.")
            logger.error(f"Lỗi khi thêm quảng cáo: ID={id_tele}, Username={username}, Tên={name}")

    except Exception as e:
        logger.error(f"❌ Lỗi trong hàm add_ad: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")


@decorators.admin_only
async def remove_ad(update: Update, context: CallbackContext):
    """Xóa một quảng cáo khỏi danh sách"""
    try:
        args = context.args
        if len(args) != 1:
            await update.message.reply_text("Sử dụng: /removead <ID>")
            return

        id_tele = args[0]
        if not id_tele.isdigit():
            await update.message.reply_text("❌ ID phải là số.")
            return
        id_tele = int(id_tele)

        # Kiểm tra xem quảng cáo có tồn tại không
        existing_ad = ads_manager.get_ad_by_id(id_tele)
        if not existing_ad:
            await update.message.reply_text("❌ Quảng cáo với ID này không tồn tại.")
            return

        # Xóa quảng cáo khỏi database
        delete_result = ads_manager.ads_collection.delete_one({"id_tele": id_tele})
        if delete_result.deleted_count > 0:
            await update.message.reply_text("✅ Xóa quảng cáo thành công.")
            logger.info(f"Xóa quảng cáo: ID={id_tele}")
        else:
            await update.message.reply_text("❌ Lỗi khi xóa quảng cáo khỏi database.")
            logger.error(f"Lỗi khi xóa quảng cáo: ID={id_tele}")

    except Exception as e:
        logger.error(f"❌ Lỗi trong hàm remove_ad: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")


from telegram.helpers import escape as escape_html
@decorators.admin_only
async def list_ads(update: Update, context: CallbackContext):
    """Liệt kê danh sách quảng cáo (dùng HTML)"""
    try:
        ad_list = ads_manager.get_all_ads()
        if not ad_list:
            await update.message.reply_text("❌ Chưa có quảng cáo nào.")
            return

        # Thay vì Markdown, ta sử dụng thẻ HTML
        message = "<b>📌 Danh sách quảng cáo:</b>\n"
        
        for ad in ad_list:
            # escape dữ liệu trước khi ghép vào HTML
            id_tele = escape_html(str(ad.get("id_tele", "")))
            username = escape_html(str(ad.get("username", "")))
            name = escape_html(str(ad.get("name", "")))

            # Dùng <b> để in đậm, <code> để bọc đoạn mã
            msg = f"- <b>ID:</b> <code>{id_tele}</code>"
            if username:
                msg += f" | <b>Username:</b> {username}"
            if name:
                msg += f" | <b>Tên:</b> {name}"

            # Thêm xuống dòng
            message += msg + "\n"

        # Gửi tin nhắn với parse_mode=ParseMode.HTML
        await update.message.reply_text(
            text=message,
            parse_mode=ParseMode.HTML
        )
        logger.info("Đã liệt kê danh sách quảng cáo bằng HTML.")

    except Exception as e:
        logger.error(f"❌ Lỗi trong hàm list_ads: {e}")
        await update.message.reply_text(f"❌ Lỗi: {e}")