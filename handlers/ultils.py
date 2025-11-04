import re
import logging
import random
import string
import unicodedata
import time
import calendar
from datetime import datetime
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type ,RetryError
from telegram.error import TimedOut, NetworkError, RetryAfter , Forbidden , BadRequest
from telegram.ext import ContextTypes
from telegram import Update
from config import ADMIN_IDS
from telegram.helpers import escape_markdown
# Thiết lập logging
logger = logging.getLogger(__name__)

def normalize_text(text):
    if not text:
        return ""
    # Loại bỏ dấu bằng cách dùng unicodedata.normalize
    text = unicodedata.normalize('NFD', text)
    text = text.encode('ascii', 'ignore').decode('utf-8')
    return text.upper()

# Hàm sinh mã ngẫu nhiên
def generate_random_code(organization_prefix):
    organization_prefix_normalized = normalize_text(organization_prefix)
    while True:
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        if any(char.isdigit() for char in random_part):  # Kiểm tra nếu có ít nhất một số
            break

    return f"{organization_prefix_normalized}-{random_part}"

# Hàm xử lý ngân sách
def process_budget(budget_str):
    if not budget_str:
        return 0

    # Loại bỏ tất cả các ký tự không phải số và '-'
    # Giữ lại dấu '-' chỉ ở vị trí đầu tiên
    cleaned = re.sub(r'^(?!-)-|[^\d\-]', '', budget_str)

    # Đảm bảo chỉ có một dấu '-' ở đầu nếu có
    cleaned = '-' + re.sub(r'-', '', cleaned[1:]) if cleaned.startswith('-') else re.sub(r'-', '', cleaned)

    try:
        return int(cleaned)
    except ValueError:
        logger.warning(f"Không thể chuyển ngân sách '{budget_str}' thành số nguyên sau khi làm sạch: '{cleaned}'")
        return 0

# Hàm định dạng số với dấu chấm mỗi 3 chữ số
def format_number(num):
    try:
        return "{:,}".format(num).replace(',', '.')
    except (ValueError, TypeError):
        return num

def get_custom_today_epoch():
    """
    Trả về epoch time.
    Nếu hôm nay là ngày cuối tháng, chuyển thành 1 giờ sáng (1:00) ngày 1 của tháng kế tiếp.
    Nếu hôm nay là 31/12 thì chuyển thành 1 giờ sáng ngày 1/1 của năm kế tiếp.
    Nếu không phải ngày cuối tháng, trả về time.time() hiện tại.
    """
    now = datetime.now()
    last_day = calendar.monthrange(now.year, now.month)[1]  # Lấy ngày cuối của tháng hiện tại

    # Nếu hôm nay là ngày cuối tháng
    if now.day == last_day:
        # Xác định tháng kế tiếp
        if now.month == 12:
            new_year = now.year + 1
            new_month = 1
        else:
            new_year = now.year
            new_month = now.month + 1
        
        # Tạo datetime mới là ngày 1 của tháng kế tiếp, 1 giờ sáng
        new_date = datetime(
            new_year,
            new_month,
            1,
            1,  # hour=1
            0,  # minute=0
            0   # second=0
        )
        return new_date.timestamp()
    else:
        return time.time()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((TimedOut, NetworkError, RetryAfter))
)
async def safe_send_message(bot, chat_id, text, **kwargs):
    try:
        # Kiểm tra và chuẩn hóa tham số
        if not text or not isinstance(text, str):
            raise ValueError("Nội dung tin nhắn phải là chuỗi hợp lệ.")

        # Chuẩn hóa kwargs (chuyển đổi set -> list)
        for key, value in kwargs.items():
            if isinstance(value, set):
                kwargs[key] = list(value)
            elif isinstance(value, dict):
                kwargs[key] = {k: list(v) if isinstance(v, set) else v for k, v in value.items()}

        # Chia nhỏ tin nhắn nếu quá dài
        max_length = 4096
        chunks = [text[i:i + max_length] for i in range(0, len(text), max_length)]

        # Gửi từng phần tin nhắn
        results = []
        for chunk in chunks:
            result = await bot.send_message(chat_id=chat_id, text=chunk, **kwargs)
            results.append(result)

        return results

    except RetryError as e:
        logger.error(f"Gửi tin nhắn thất bại sau khi retry: {e}")
        await notify_admins(bot, chat_id, f"Lỗi gửi tin nhắn: {e}")

    except (BadRequest, Forbidden) as e:
        logger.error(f"Lỗi Telegram API (BadRequest hoặc Forbidden): {e}")
        await notify_admins(bot, chat_id, f"Lỗi Telegram API: {e}")

    except Exception as e:
        logger.critical(f"Lỗi không xác định khi gửi tin nhắn tới {chat_id}: {e}")
        logger.debug(f"Dữ liệu bị lỗi: text={text}, kwargs={kwargs}")
        await notify_admins(bot, chat_id, f"Lỗi không xác định: {e}")



# Hàm trợ giúp chỉnh sửa tin nhắn với retry
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((TimedOut, NetworkError, RetryAfter))
)
async def safe_edit_message(bot, chat_id, message_id, text, **kwargs):
    try:
        # Kiểm tra và chuẩn hóa tham số
        if not text or not isinstance(text, str):
            raise ValueError("Nội dung tin nhắn (text) không hợp lệ.")
        
        # Chuẩn hóa kwargs (chuyển đổi set -> list)
        for key, value in kwargs.items():
            if isinstance(value, set):
                kwargs[key] = list(value)

        # Chỉnh sửa tin nhắn
        return await bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text, **kwargs)

    except RetryError as e:
        logger.error(f"Chỉnh sửa tin nhắn thất bại sau khi retry: {e}")
        await notify_admins(bot, chat_id, f"Lỗi chỉnh sửa tin nhắn: {e}")

    except (BadRequest, Forbidden) as e:
        logger.error(f"Lỗi Telegram API (BadRequest hoặc Forbidden): {e}")
        await notify_admins(bot, chat_id, f"Lỗi Telegram API: {e}")

    except Exception as e:
        logger.critical(f"Lỗi không xác định khi chỉnh sửa tin nhắn tại chat_id {chat_id}, message_id {message_id}: {e}")
        await notify_admins(bot, chat_id, f"Lỗi không xác định: {e}")


async def notify_admins(bot, chat_id, error_message): 
    if "ADMIN_IDS" in globals() and ADMIN_IDS:
        error_list = []
        for admin_id in ADMIN_IDS:
            error_list.append(f"<b>Lỗi gửi tới Chat ID:</b> {chat_id}\n<b>Chi tiết:</b> {error_message}")
        error_message_html = "\n\n".join(error_list)  # Dùng \n để xuống dòng
        logger.error(f"Thông báo lỗi tới admin: {error_message_html}")
        try:
            for admin_id in ADMIN_IDS:
                await bot.send_message(
                    chat_id=admin_id,
                    text=f"<b>Các lỗi xảy ra:</b>\n{error_message_html}",
                    parse_mode="HTML"
                )
        except Exception as admin_error:
            logger.warning(f"Không thể gửi thông báo lỗi tới admin: {admin_error}")

async def handle_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý lệnh /info để trả về thông tin người dùng."""
    try:
        user = update.effective_user

        # Lấy thông tin người dùng
        user_id = user.id
        full_name = escape_markdown(user.full_name, version=2)  # Escape tên
        username = f"@{escape_markdown(user.username, version=2)}" if user.username else "Không có"
        language_code = user.language_code if user.language_code else "Không xác định"

        # Tạo thông điệp trả về
        info_message = (
            f"👤 *Thông tin người dùng:*\n\n"
            f"🆔 *ID Telegram:* `{user_id}`\n"
            f"📛 *Tên:* {full_name}\n"
            f"📧 *Username:* {username}\n"
            f"🌐 *Ngôn ngữ:* {language_code}"
        )

        await update.message.reply_text(info_message, parse_mode="MarkdownV2")
    except Exception as e:
        logger.error(f"Lỗi trong xử lý lệnh /info: {e}")
        await update.message.reply_text("❗ *Lỗi:* Không thể lấy thông tin. Vui lòng thử lại sau.", parse_mode="MarkdownV2")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị danh sách các lệnh bot hỗ trợ."""
    help_text = (
        "🤖 **Danh sách các lệnh:**\n\n"
        "🔹 **/start** - Bắt đầu sử dụng bot.\n"
        "🔹 **/ns** - Gửi form ngân sách để ghi vào hệ thống.\n"
        "🔹 **/info** - Hiển thị thông tin người dùng hiện tại.\n"
        "🔹 **/gettid** - Lấy Chat ID của nhóm hoặc cá nhân.\n\n"
        "🔹 Trợ Lý Commands:\n"
        "   - **/rf <tổ> <số tiền>** - Thêm một khoản hoàn tiền vào hệ thống.\n"
        "   - **/addroom <id>** - Thêm nhóm/phòng được phép.\n"
        "   - **/removeroom <id>** - Xóa nhóm/phòng.\n"
        "   - **/listrooms** - Liệt kê các nhóm/phòng được phép.\n\n"
        "🔹 **Admin Commands:**\n"
        "   - **/addtroly <id>** - Thêm trợ lý mới.\n"
        "   - **/removetroly <id>** - Xóa trợ lý.\n"
        "   - **/lstroly** - Liệt kê danh sách trợ lý.\n"
        "   - **/addhlv <id>** - Thêm HLV mới.\n"
        "   - **/rmhlv <id>** - Xóa HLV.\n"
        "   - **/lshlv** - Liệt kê danh sách HLV.\n"
        "Hãy nhập lệnh theo đúng định dạng để sử dụng bot hiệu quả! 🚀"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

