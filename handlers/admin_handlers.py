import decorators
import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import CallbackContext, CommandHandler, CallbackQueryHandler
from db.rooms import room_manager
from db.troly import assistant_manager
from db.ads import ads_manager

# Thiết lập logging
logger = logging.getLogger(__name__)


@decorators.troly_only
# async def add_room(update: Update, context: CallbackContext):
#     """Handler cho lệnh /addroom để thêm một nhóm mới vào danh sách"""
#     try:
#         chat = update.effective_chat
#         chat_id = chat.id
#         group_name = chat.title

#         if chat.type not in ['group', 'supergroup']:
#             await update.message.reply_text("Lệnh này chỉ có thể được sử dụng trong các nhóm hoặc supergroup.")
#             logger.info(f"Người dùng từ nhóm không phải là group hoặc supergroup: chat_id={chat_id}")
#             return

#         # Kiểm tra xem phòng đã tồn tại chưa
#         existing_room = room_manager.get_room_by_id(chat_id)
#         if existing_room:
#             await update.message.reply_text("Nhóm này đã tồn tại trong danh sách.")
#             logger.info(f"Nhóm đã tồn tại: chat_id={chat_id}")
#             return

#         # Thêm phòng mới vào database
#         result = room_manager.add_room(chat_id, group_name)
#         if result:
#             await update.message.reply_text(f"✅ Thêm nhóm thành công:\nID: {chat_id}\nTên: {group_name}")
#             logger.info(f"Thêm nhóm mới thành công: ID={chat_id}, Tên={group_name}")
#         else:
#             await update.message.reply_text("❌ Lỗi khi thêm nhóm vào database.")
#             logger.error(f"Lỗi khi thêm nhóm: chat_id={chat_id}, tên={group_name}")

#         # Cập nhật cache, đảm bảo luôn là danh sách
#         if 'allowed_rooms' not in context.bot_data:
#             context.bot_data['allowed_rooms'] = []

#         if isinstance(context.bot_data['allowed_rooms'], list):
#             if chat_id not in context.bot_data['allowed_rooms']:
#                 context.bot_data['allowed_rooms'].append(chat_id)
#         else:
#             logger.warning("allowed_rooms không phải là danh sách, reset lại thành list.")
#             context.bot_data['allowed_rooms'] = [chat_id]

#         logger.debug(f"Cập nhật cache 'allowed_rooms' với chat_id={chat_id}")

#     except Exception as e:
#         logger.error(f"Lỗi trong hàm add_room: {e}")
#         await update.message.reply_text(f"❌ Lỗi: {e}")

# === HÀM GỬI DANH SÁCH KHU VỰC ===
async def add_room(update: Update, context: CallbackContext):
    """Khi gõ /addroom, bot sẽ hiển thị các khu để chọn"""
    chat = update.effective_chat
    chat_id = chat.id
    group_name = chat.title

    if chat.type not in ['group', 'supergroup']:
        await update.message.reply_text("⚠️ Lệnh này chỉ dùng được trong nhóm hoặc supergroup.")
        return

    # Kiểm tra nhóm đã tồn tại chưa
    existing_room = room_manager.get_room_by_id(chat_id)
    if existing_room:
        await update.message.reply_text("❗ Nhóm này đã tồn tại trong danh sách.")
        return

    # Lưu thông tin nhóm tạm vào context để callback query xử lý
    context.user_data["pending_add_room"] = {
        "chat_id": chat_id,
        "group_name": group_name
    }

    # Tạo danh sách nút chọn khu vực
    areas = [
        ("Khu A", "khu_a"),
        ("Khu B", "khu_b"),
        ("Khu C", "khu_c"),
        ("Khu D", "khu_d"),
    ]

    keyboard = [
        [InlineKeyboardButton(text=name, callback_data=f"addroom_area|{code}")]
        for name, code in areas
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("🏗️ Vui lòng chọn khu vực cho nhóm này:", reply_markup=reply_markup)


# === HÀM XỬ LÝ KHI NGƯỜI DÙNG CHỌN KHU VỰC ===
async def add_room_area_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()

    data = query.data.split("|")
    if len(data) != 2:
        await query.edit_message_text("❌ Dữ liệu callback không hợp lệ.")
        return

    area_name = data[1]  # ví dụ: khu_a, khu_b, ...

    pending = context.user_data.get("pending_add_room")
    if not pending:
        await query.edit_message_text("⚠️ Không có nhóm nào đang chờ được thêm.")
        return

    chat_id = pending["chat_id"]
    group_name = pending["group_name"]

    # Gọi hàm add_room trong room_manager (thêm vào DB)
    result = room_manager.add_room(chat_id, group_name, area_name)

    if result:
        await query.edit_message_text(
            f"✅ Đã thêm nhóm **{group_name}** (ID: `{chat_id}`)\n"
            f"📍 Khu vực: *{area_name.replace('_', ' ').title()}*",
            parse_mode="Markdown"
        )
        logger.info(f"Thêm nhóm thành công: {group_name} - {chat_id} - {area_name}")
    else:
        await query.edit_message_text("❌ Lỗi khi thêm nhóm vào cơ sở dữ liệu.")

    # Dọn dẹp dữ liệu tạm
    context.user_data.pop("pending_add_room", None)



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