# bot.py
from dotenv import load_dotenv
import os
import logging
# Lấy ENV_PATH từ biến môi trường ENV_PATH
env_path = os.getenv("ENV_PATH", ".env.khu_a")  # fallback về .env nếu không có

load_dotenv(dotenv_path=env_path)

# Tiếp tục load config như thường
import config
import handlers.admin_handlers as admin_h
import handlers.data_handlers as data_h
import handlers.ads_handlers as ads_h
from logging.handlers import TimedRotatingFileHandler
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
    MessageHandler,
    CallbackContext,
    filters
)
from decorators import ads_or_troly_rp
from handlers.ultils import handle_info_command, help_command
from db.rooms import RoomManager
from telegram.request import HTTPXRequest

room_manager = RoomManager()
# Thiết lập logging
# Tạo thư mục logs nếu chưa có
if not os.path.exists("logs"):
    os.makedirs("logs")

# Cấu hình ghi log mỗi ngày 1 file, giữ tối đa 7 ngày
log_file = "logs/bot.log"
file_handler = TimedRotatingFileHandler(
    filename=log_file,
    when='midnight',       # tạo log mới vào lúc 00:00 mỗi ngày
    interval=1,
    backupCount=7,         # giữ lại 7 file log cũ
    encoding='utf-8',
    delay=True
)

file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

# Ghi ra console
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Gắn các handler vào root logger
logging.basicConfig(
    level=logging.INFO,
    handlers=[file_handler, stream_handler],
    force=True
)

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị thông tin giới thiệu khi người dùng nhấn bắt đầu."""
    introduction_text = (
        "🤖 **Chào mừng bạn đến với Bot Quản Lý Ngân Sách!**\n\n"
        "🔹 **Chức năng chính:**\n"
        "- Quản lý ngân sách, hoàn tiền, theo dõi chi tiêu dễ dàng.\n"
        "- Hỗ trợ quản lý phòng ban và trợ lý.\n\n"
        "🔹 **Hướng dẫn sử dụng:**\n"
        "Sử dụng lệnh /h hoặc /help để xem danh sách các lệnh hỗ trợ.\n\n"
    )
    await update.message.reply_text(introduction_text, parse_mode="Markdown")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    # Trường hợp đặc biệt: lỗi ở polling layer, không có update
    if update is None:
        # In cả error message và traceback
        logger.critical(
            "Error handler called without update; exception detail below:",
            exc_info=context.error
        )
        return
    
    try:
        logger.error("Exception while handling an update:", exc_info=context.error)

        user_info = "Không xác định"
        chat_info = "Không xác định"
        message_text = "Không có tin nhắn"

        if update.effective_user:
            user = update.effective_user
            user_info = f"{user.full_name or user.username or 'No username'} (ID: {user.id})"
        if update.effective_chat:
            chat = update.effective_chat
            chat_info = f"{chat.title or 'Private Chat'} (ID: {chat.id})"
        if update.effective_message:
            message_text = update.effective_message.text or "Không có nội dung"

        admin_message = (
            f"❗ <b>Error occurred</b>:\n"
            f"• <b>Người dùng:</b> {user_info}\n"
            f"• <b>Nhóm/Chat:</b> {chat_info}\n"
            f"• <b>Tin nhắn:</b> <code>{message_text}</code>\n"
            f"• <b>Lỗi:</b> <code>{str(context.error)}</code>"
        )

        for admin_id in config.ADMIN_IDS:
            await context.bot.send_message(
                chat_id=admin_id,
                text=admin_message,
                parse_mode="HTML"
            )

        if update.effective_message:
            await update.effective_message.reply_text(
                "Đã xảy ra lỗi trong quá trình xử lý. Vui lòng thử lại sau.",
                quote=True
            )
    except Exception as e:
        logger.critical(f"Exception in error handler: {e}", exc_info=True)
async def ns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.edited_message:
        logger.info("Bỏ qua tin nhắn đã sửa.")
        return
    message_text = update.message.text
    # Loại bỏ phần lệnh /ns để lấy phần form
    form_text = message_text.partition('/ns')[2].strip()
    if not form_text:
        await update.message.reply_text("Vui lòng gửi form ngân sách sau lệnh /ns")
        return
    # Gọi hàm xử lý form ngân sách
    await data_h.handle_ngansach(update, context)

async def get_chat_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Chat ID: {chat_id}")

async def rp(update: Update, context: CallbackContext):
    """Xử lý lệnh /rp từ văn bản hoặc tin nhắn kèm media (video có caption)"""
    message = update.message
    # 👉 Bỏ qua nếu là tin nhắn đã chỉnh sửa
    if update.edited_message:
        return
    # Lấy nội dung từ tin nhắn hoặc caption nếu có file media
    text = message.caption if message.caption else message.text

    # Nếu tin nhắn không chứa /rp, thoát ra và để handler khác xử lý
    if not text or not text.strip().startswith("/rp"):
        return  

    # Nếu có /rp, gọi `handle_rp_command`
    response = await ads_h.handle_rp_command(message)

    # Nếu `handle_rp_command` có phản hồi, gửi lại cho user
    if response:
        await message.reply_text(response)

    # Ghi log thông tin người gửi
    user = update.effective_user
    user_id = user.id
    full_name = user.full_name
    username = f"@{user.username}" if user.username else "(Không có username)"
    logger.info(f"User ID: {user_id}, Tên: {full_name}, Username: {username} đã gửi lệnh /rp")


def main():
    logger.info(f"🔌 Đang kết nối tới {config.BOT_TOKEN}...")
    request = HTTPXRequest(
        connect_timeout=10,
        read_timeout=60,
        write_timeout=10,
        pool_timeout=10
    )
    application = ApplicationBuilder().token(config.BOT_TOKEN).request(request).build()

    # Tải danh sách các chat_id được phép và lưu vào bot_data
    allowed_rooms = room_manager.get_all_room_ids()
    application.bot_data['allowed_rooms'] = allowed_rooms
    logger.info(f"Loaded allowed_rooms: {allowed_rooms}")

    # Thêm handler cho lệnh /start
    application.add_handler(CommandHandler("start", start))

    # Thêm handler cho lệnh /ns để xử lý ngân sách
    application.add_handler(CommandHandler("ns", ns_command))
    application.add_handler(CommandHandler("rf", data_h.handle_rf_command))
    application.add_handler(CommandHandler("done", data_h.handle_done_command))
    application.add_handler(CommandHandler("note", data_h.handle_note_command))
    application.add_handler(CommandHandler("check", data_h.handle_check_command))
    application.add_handler(CommandHandler("xn", data_h.handle_xn_command))

    # Thêm handler cho lệnh /tiktok để xử lý
    application.add_handler(CommandHandler("tiktok", data_h.handle_tiktok_command))
    application.add_handler(CallbackQueryHandler(data_h.handle_tiktok_bulk_yes, pattern="^tiktok_bulk_yes$"))
    application.add_handler(CallbackQueryHandler(data_h.handle_tiktok_bulk_no,  pattern="^tiktok_bulk_no$"))

    application.add_handler(CommandHandler("facebook", data_h.handle_facebook_command))
    application.add_handler(CallbackQueryHandler(data_h.handle_facebook_bulk_yes, pattern="^facebook_bulk_yes$"))
    application.add_handler(CallbackQueryHandler(data_h.handle_facebook_bulk_no,  pattern="^facebook_bulk_no$"))

    # Thêm handler cho lệnh /chatid để xác nhận chat ID
    application.add_handler(CommandHandler("gettid", get_chat_id))
    application.add_handler(CommandHandler("info", handle_info_command))

    # Thêm các lệnh Admin commands trực tiếp vào application
    application.add_handler(CommandHandler("addtroly", admin_h.add_troly))
    application.add_handler(CommandHandler("removetroly", admin_h.remove_troly))
    application.add_handler(CommandHandler("lstroly", admin_h.list_troly))
    
    # Thêm các lệnh Room management commands trực tiếp vào application
    application.add_handler(CommandHandler("ad", admin_h.add_room))
    application.add_handler(CallbackQueryHandler(admin_h.add_room_area_callback, pattern=r"^addroom_area\|"))
    application.add_handler(CommandHandler("re", admin_h.remove_room))
    application.add_handler(CommandHandler("listrooms", admin_h.list_rooms))

    application.add_handler(CommandHandler(["h","help"], help_command))

    # Thêm CallbackQueryHandler cho các nút bấm
    # Pattern: "YES|<uuid>" hoặc "NO|<uuid>"
    button_handler = CallbackQueryHandler(
        data_h.button_callback,
        pattern=r"^(YES|NO)\|[0-9a-f\-]{36}$"
    )
    application.add_handler(button_handler)
    
    
    # Thêm error handler
    application.add_error_handler(error_handler)

    # Chạy bot
    application.run_polling()

if __name__ == "__main__":
    main()
