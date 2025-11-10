from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError
from handlers.ultils import generate_random_code, process_budget , format_number , safe_send_message , safe_edit_message , normalize_text , get_custom_today_epoch
from handlers.db_helpers import init_db, add_confirmation, get_confirmation, delete_confirmation
from datetime import datetime, timezone, timedelta
from decorators import troly_only, allowed_room , troly_only
from db.budget import QuanLyABCVIP
from config import ADMIN_IDS ,EXPIRATION_TIME
from db.note import note_manager
from telegram.ext import CallbackContext, CallbackQueryHandler
import calendar
import html
import time
import uuid
import logging
import re
import json
import aiohttp
import os
import unicodedata
# Thiết lập logging
logger = logging.getLogger(__name__)

budget_manager = QuanLyABCVIP()

init_db()
BASE_URL = os.getenv("API_BASE_URL", "http://103.48.84.131")

API_URL = f"{BASE_URL}api/v1/tiktok-user/create"
API_BULK_URL = f"{BASE_URL}api/v1/tiktok-user/bulk-create"
API_CHECK_URL = f"{BASE_URL}api/v1/tiktok-user/check-exists-username"
API_BULK_CHECK = f"{BASE_URL}api/v1/tiktok-user/bulk-check"
API_BULK_SAVE  = f"{BASE_URL}api/v1/tiktok-user/bulk-save"
API_FACEBOOK_BULK_CHECK  = f"{BASE_URL}api/v1/facebook-user/bulk-check"
API_FACEBOOK_BULK_SAVE   = f"{BASE_URL}api/v1/facebook-user/bulk-save"

def escape_html(text):
    """Escape các ký tự đặc biệt trong HTML."""
    return html.escape(text, quote=True)

def clean_ma_hd(text):
    # Chuẩn hóa Unicode
    text = unicodedata.normalize("NFKC", text)
    # Chỉ giữ lại chữ, số và dấu phẩy
    text = re.sub(r'[^A-Za-z0-9,]', '', text)
    return text.upper()

@allowed_room
async def handle_ngansach(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.edited_message:
        logger.info("Bỏ qua tin nhắn đã sửa.")
        return

    try:
        await safe_send_message(
            context.bot,
            chat_id=update.effective_chat.id,
            text="⚙️ <b>Đang xử lý yêu cầu của bạn. Vui lòng chờ...</b>",
            parse_mode="HTML"
        )

        message_text = update.message.text.strip()
        logger.info(f"Nội dung tin nhắn nhận được: {message_text}")

        lines = message_text.split('\n')

        data = {
            "tên nhóm": "",
            "tổ": "",
            "mã hd": "",
            "ngân sách": "",
            "nội dung": ""
        }

        field_mapping = {
            "tên nhóm": "tên nhóm",
            "nhóm": "tên nhóm",
            "tổ": "tổ",
            "mã hd": "mã hd",
            "mã hậu đài": "mã hd",
            "ngân sách xin": "ngân sách",
            "ns": "ngân sách",
            "ngân sách": "ngân sách",
            "nội dung": "nội dung"
        }

        pattern = re.compile(r'^\+?(.*?)\s*:\s*(.*)$', re.IGNORECASE)

        for line in lines:
            line = line.strip()
            if not line or line.lower().startswith('form ngân sách'):
                continue
            match = pattern.match(line)
            if match:
                key, value = match.groups()
                key = key.strip().lower()
                value = value.strip()
                normalized_key = field_mapping.get(key)
                if normalized_key:
                    data[normalized_key] = value
                else:
                    logger.warning(f"Trường không xác định: {key}")
            else:
                logger.warning(f"Dòng không khớp với regex: {line}")

        hd_codes = data["mã hd"].split(',')

        # 🟢 Lấy danh sách hợp đồng bị bỏ qua
        ignored_codes = QuanLyABCVIP().get_ignored_contracts_by_key("ABCVIP") or []
        ignored_codes = [code.strip().upper() for code in ignored_codes]

        processed_hd_codes = []

        for code in hd_codes:
            code = code.strip().upper()

            # Nếu code nằm trong danh sách bỏ qua → giữ nguyên
            if code in ignored_codes:
                processed_hd_codes.append(code)
                logger.debug(f"✅ Giữ nguyên mã bị bỏ qua: {code}")
                continue

            # Nếu không → bỏ 1 ký tự cuối (nếu đủ dài)
            new_code = code[:5]
            processed_hd_codes.append(new_code)
            logger.debug(f"✂️ Cắt bớt 1 ký tự cuối: {code} ➝ {new_code}")

        logger.info(f"📄 Ignored contracts cho ABCVIP: {processed_hd_codes}")

        hd_codes = processed_hd_codes
        hd_counts = {code: hd_codes.count(code) for code in set(hd_codes)}
        total_occurrences = sum(hd_counts.values())

        mandatory_fields = ["tổ", "mã hd", "ngân sách"]
        missing_fields = [field for field in mandatory_fields if not data.get(field)]

        if missing_fields:
            missing_fields_formatted = ", ".join([f"<b>'{field.capitalize()}'</b>" for field in missing_fields])
            error_message_text = f"❗ <b>Lỗi:</b> Các trường sau đây không được để trống: {missing_fields_formatted}."
            await safe_send_message(
                context.bot,
                chat_id=update.effective_chat.id,
                text=error_message_text,
                parse_mode='HTML'
            )
            return

        try:
            budget_value = abs(int(re.sub(r'[^\d]', '', data["ngân sách"])))
            data["ngân sách"] = budget_value
        except ValueError:
            await safe_send_message(
                context.bot,
                chat_id=update.effective_chat.id,
                text="❗ <b>Lỗi:</b> Giá trị 'Ngân Sách' không hợp lệ. Vui lòng kiểm tra lại.",
                parse_mode='HTML'
            )
            return

        data["tên nhóm"] = data["tên nhóm"] if data["tên nhóm"] else update.effective_chat.title
        data["tổ"] = data["tổ"].upper() if data["tổ"] else "DEFAULT"

        all_contract_codes = set(hd_counts.keys())

        try:
            # 🟢 Lấy ngân sách hiện tại từ MongoDB
            chat_id = update.effective_chat.id
            current_budgets = budget_manager.get_current_budget(list(all_contract_codes),data["tổ"], chat_id)

            # 🟢 Tính toán ngân sách dự kiến trực tiếp từ current_budgets (KHÔNG gọi lại DB)
            projected_budgets = {
                code: current_budgets.get(code, 0) + round(budget_value * count / total_occurrences)
                for code, count in hd_counts.items()
            }

            logger.info(f"Ngân sách hiện tại: {current_budgets} {hd_counts} {hd_codes} {all_contract_codes}")
        except Exception as e:
            logger.error(f"Lỗi khi lấy ngân sách hiện tại: {e}")
            await safe_send_message(
                context.bot,
                chat_id=update.effective_chat.id,
                text="❗ Lỗi khi lấy thông tin ngân sách hiện tại. Vui lòng thử lại sau.",
                parse_mode="HTML"
            )
            return

        # ✅ Sử dụng hàm của bạn để tạo ID ngẫu nhiên
        random_code = generate_random_code(data["tổ"])
        confirmation_id = str(uuid.uuid4())
        add_confirmation(
            id=confirmation_id,
            data=json.dumps(data),
            code=random_code,
            created_at=datetime.now().isoformat()
        )
        confirmation_message = (
            f"📋 <b>Xác nhận ghi dữ liệu ngân sách:</b>\n\n"
            f"<b>ID:</b> <code>{random_code}</code>\n"
            f"<b>TỔ:</b> {data['tổ']}\n"
            f"<b>Tổng NS đề xuất:</b> {format_number(budget_value)} VND\n"
            f"<b>Nội dung:</b> {data['nội dung']}\n\n"
        )

        # Đếm số lần xuất hiện của mỗi mã HD khi duyệt (theo thứ tự)
        hd_sequence_count = {}

        for code, count in hd_counts.items():
            hd_sequence_count[code] = hd_sequence_count.get(code, 0) + 1

            budget_share = round(budget_value * count / total_occurrences)

            # 🔹 Log mã code hiện tại
            logger.info(f"🟢 Đang xử lý code: {code}")

            # 🔹 Nếu code bắt đầu bằng F và kết thúc là 1 hoặc 9 → lấy limit tương ứng
            limit_info = QuanLyABCVIP().get_limit_by_key(code)
            if limit_info:
                logger.info(
                    f"🔸 Giới hạn ngân sách ({key}): {limit_info['limit']} VND (Cập nhật: {limit_info['updated_at']})"
                )
            else:
                logger.warning(f"⚠️ Không tìm thấy limit cho key: {key}")

            # 🔹 Tính ngân sách hiện tại theo logic
            if code.endswith("11"):
                base_code = code[:-2]
                current_budget_show = current_budgets.get(code, 0) + current_budgets.get(base_code, 0)
            elif not re.search(r'\d+$', code):  # không có số ở cuối
                code_11 = code + "11"
                current_budget_show = current_budgets.get(code, 0) + current_budgets.get(code_11, 0)
            else:
                current_budget_show = current_budgets.get(code, 0)

            total_predicted = budget_share + current_budget_show

            # 🔹 Nếu có limit → kiểm tra vượt ngưỡng
            if limit_info and limit_info.get("limit", 0) > 0:
                remaining = limit_info["limit"] - total_predicted
                if total_predicted > limit_info["limit"]:
                    # 🚨 Gửi cảnh báo riêng
                    warning_message = (
                        f"⚠️ <b>MÃ HẬU ĐÀI:</b> {code}\n"
                        f"❌ <b>ĐÃ VƯỢT NGƯỠNG NGÂN SÁCH!</b>\n"
                        f"<b>Giới hạn:</b> {format_number(limit_info['limit'])} VND\n"
                        f"<b>Tổng chi dự kiến:</b> {format_number(total_predicted)} VND\n"
                        f"<b>Vượt quá:</b> {format_number(total_predicted - limit_info['limit'])} VND"
                    )
                    logger.warning(f"🚨 Mã {code} vượt ngưỡng ngân sách {limit_info['limit']}")
                    await safe_send_message(
                        context.bot,
                        chat_id=update.effective_chat.id,
                        text=warning_message,
                        parse_mode='HTML'
                    )
                    # ✅ Vẫn trong giới hạn
                
                confirmation_message += (
                    f"<b>Mã HD:</b> {code} - {count}\n"
                    f"<b>NGÂN SÁCH HIỆN TẠI:</b> {format_number(current_budget_show)} VND\n"
                    f"<b>ĐỀ XUẤT:</b> {format_number(budget_share)} VND\n"
                    f"<b>TỔNG CHI DỰ KIẾN:</b> {format_number(total_predicted)} VND\n"
                    f"<b>GIỚI HẠN NGÂN SÁCH ({limit_info['key']}):</b> {format_number(limit_info['limit'])} VND\n"
                    f"<b>NGƯỠNG CÒN LẠI:</b> {format_number(remaining)} VND\n\n"
                    
                )

            else:
                # 🟢 Không có limit thì vẫn chạy bình thường
                confirmation_message += (
                    f"<b>Mã HD:</b> {code} - {count}\n"
                    f"<b>NGÂN SÁCH HIỆN TẠI:</b> {format_number(current_budget_show)} VND\n"
                    f"<b>ĐỀ XUẤT:</b> {format_number(budget_share)} VND\n"
                    f"<b>TỔNG CHI DỰ KIẾN:</b> {format_number(total_predicted)} VND\n\n"
                )

        # ✅ Kết thúc message chính
        confirmation_message += f"<b>Nội dung:</b> {data['nội dung']}\n\n"
        confirmation_message += "<b>TÌNH TRẠNG:</b> <code>pending</code>\n\n"
        confirmation_message += "Bạn có chắc chắn muốn ghi dữ liệu này không?"

        # ✅ Thêm nút xác nhận
        keyboard = [
            [
                InlineKeyboardButton("✅ YES", callback_data=f"YES|{confirmation_id}"),
                InlineKeyboardButton("❌ NO", callback_data=f"NO|{confirmation_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await safe_send_message(
            context.bot,
            chat_id=update.effective_chat.id,
            text=confirmation_message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )


    except Exception as e:
        logger.error(f"Lỗi trong xử lý lệnh handle_ngansach: {e}")
    
@troly_only
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info("🟢 Đã vào hàm button_callback")

    query = update.callback_query
    await query.answer()

    user = query.from_user
    user_id = user.id
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    username = user.username or "Không có username"

    logger.info(f"📩 Người dùng: {full_name} (Username: {username}, ID: {user_id}) đã nhấn nút.")

    try:
        data_parts = query.data.split('|')
        if len(data_parts) != 2:
            await query.edit_message_text(
                text="❗ **Lỗi:** Dữ liệu không hợp lệ.",
                parse_mode='Markdown'
            )
            logger.warning(f"❌ Dữ liệu không hợp lệ: {query.data}")
            return

        action, confirmation_id = data_parts
        logger.info(f"🔍 Đang kiểm tra confirmation_id: {confirmation_id}")

        record = get_confirmation(confirmation_id)
        logger.info(f"📩 Dữ liệu lấy từ DB: {record}")

        if not record:
            await query.edit_message_text(
                text="⚠️ **Lỗi:** Yêu cầu đã hết hạn hoặc không tồn tại.",
                parse_mode='Markdown'
            )
            logger.warning(f"⚠️ confirmation_id '{confirmation_id}' không tồn tại hoặc đã hết hạn.")
            return

        # Giải mã dữ liệu JSON
        try:
            data = json.loads(record["data"])
            logger.info(f"📜 Dữ liệu JSON sau khi giải mã: {data}")
        except Exception as e:
            logger.error(f"❌ Lỗi khi giải mã JSON: {e}")
            return

        random_code = record["code"]

        if "mã hd" not in data:
            logger.error(f"❌ Không tìm thấy 'mã hd' trong dữ liệu: {data}")
            return
        
        hd_codes = data["mã hd"].split(',')
        ignored_codes = QuanLyABCVIP().get_ignored_contracts_by_key("ABCVIP") or []
        ignored_codes = [code.strip().upper() for code in ignored_codes]
        processed_hd_codes = []
        original_to_processed = {}

        for code in hd_codes:
            original_code = code.strip().upper()

            if original_code in ignored_codes:
                processed_code = original_code
            else:
                processed_code = original_code[:5]

            processed_hd_codes.append(processed_code)
            original_to_processed[processed_code] = original_code
                
        hd_counts = {code: processed_hd_codes.count(code) for code in set(processed_hd_codes)}
        total_occurrences = sum(hd_counts.values())

        # 🟢 Xử lý hành động YES
        if action == "YES":
            try:
                total_budget_by_hd = {}

                all_contract_codes = set(hd_counts.keys())

                for code in list(hd_counts.keys()):
                    # 🔄 Nếu có mã đuôi "11", thêm mã gốc vào
                    if code.endswith("11") and len(code) > 2:
                        all_contract_codes.add(code[:-2])  # FD3N11 ➝ FD3N

                    # 🔄 Nếu mã KHÔNG có số ở cuối (VD: FD3N), thêm mã + "11"
                    elif not code[-1].isdigit():
                        all_contract_codes.add(code + "11")  # FD3N ➝ FD3N11

                # 🟢 Lấy ngân sách hiện tại từ MongoDB
                chat_id = update.effective_chat.id
                current_budgets = budget_manager.get_current_budget(list(all_contract_codes), data["tổ"],chat_id)

                # 🟢 Lưu từng mã HD vào MongoDB
                for code, count in hd_counts.items():
                    budget_share = round(data["ngân sách"] * count / total_occurrences)

                    # 🟢 Lấy ngân sách hiện tại của mã hợp đồng
                    current_budget = current_budgets.get(code, 0) if current_budgets else 0

                    # 🟢 Tổng ngân sách sau khi cộng thêm đề xuất
                    projected_budget = current_budget + budget_share

                    # 🟢 Cập nhật tổng ngân sách theo mã HD
                    total_budget_by_hd[code] = projected_budget
                    custom_timestamp = get_custom_today_epoch()

                    original_code = original_to_processed.get(code, code)
                    # 🟢 Lưu vào MongoDB
                    budget_manager.add_budget(
                        budget_id=random_code,
                        team=data["tổ"],
                        contract_code=code,
                        original_contract_code=original_code,
                        group_name=data["tên nhóm"],
                        chat_id=chat_id,
                        amount=budget_share,
                        status="pending",
                        timestamp=custom_timestamp,
                        assistant=full_name,
                        note=data["nội dung"]
                    )

                    logger.info(f"✅ Đã lưu ngân sách vào MongoDB cho mã HD: {code}, số tiền: {budget_share}")

                # 🟢 Gửi thông báo thành công
                message = (
                    f"✅ **Dữ liệu đã được lưu thành công**\n\n"
                    f"**ID:** `{random_code}`\n"
                    f"**TỔ:** `{data['tổ']}`\n"
                )

                for code, count in hd_counts.items():
                    current_budget = current_budgets.get(code, 0) if current_budgets else 0
                    budget_share = round(data["ngân sách"] * count / total_occurrences)
                    
                    current_budget_show = current_budgets.get(code, 0)

                
                    message += (
                        f"**Mã HD:** `{code} - {count}`\n"
                        f"  - **Ngân sách hiện tại:** `{format_number(current_budget_show)} VND`\n"
                        f"  - **Đề xuất:** `{format_number(budget_share)} VND`\n"
                        f"  - **Tổng sau khi cộng:** `{format_number(current_budget_show + budget_share)} VND`\n\n"
                        f"NỘI DUNG: {data['nội dung']}\n\n"
                    )

                await safe_edit_message(
                    context.bot,
                    chat_id=query.message.chat.id,
                    message_id=query.message.message_id,
                    text=message,
                    parse_mode='Markdown'
                )

                # 🗑️ Xóa dữ liệu xác nhận
                delete_confirmation(confirmation_id)
                logger.info(f"🗑️ Đã xóa confirmation_id '{confirmation_id}' sau khi xử lý.")

            except Exception as e:
                logger.error(f"❌ Lỗi khi xử lý YES: {e}")
                await query.edit_message_text(
                    text="❗ Lỗi trong quá trình xử lý. Vui lòng thử lại sau.",
                    parse_mode='Markdown'
                )
                return

        # 🟢 Xử lý hành động NO
        elif action == "NO":
            logger.info(f"🔴 Xử lý NO cho confirmation_id '{confirmation_id}'.")
            await safe_edit_message(
                context.bot,
                chat_id=query.message.chat.id,
                message_id=query.message.message_id,
                text="❌ **Dữ liệu đã bị hủy bỏ.**",
                parse_mode='Markdown'
            )
            delete_confirmation(confirmation_id)
            logger.info(f"🗑️ Đã xóa confirmation_id '{confirmation_id}' sau khi xử lý.")

        else:
            await query.edit_message_text(
                text="❗ **Lỗi:** Hành động không hợp lệ.",
                parse_mode='Markdown'
            )
            logger.warning(f"❌ Hành động không hợp lệ: {action}")

    except Exception as e:
        logger.error(f"❌ Lỗi trong xử lý button_callback: {e}")
        await safe_send_message(
            context.bot,
            chat_id=ADMIN_IDS,
            text=f"❗ **Lỗi:** {e}",
            parse_mode='Markdown'
        )

@allowed_room
async def handle_done_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        chat_id = update.effective_chat.id

        if len(context.args) < 1:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text="❗ **Lỗi:** Vui lòng nhập đúng định dạng `/done <ID> <Số tiền (tùy chọn)>`.",
                parse_mode='Markdown'
            )
            return

        await safe_send_message(
            context.bot,
            chat_id=update.effective_chat.id,
            text="⚙️ **Đang xử lý yêu cầu của bạn. Vui lòng chờ...**",
            parse_mode="Markdown"
        )

        budget_id = context.args[0].strip().upper()  # ID ngân sách
        amount_str = context.args[1] if len(context.args) > 1 else None  # Số tiền (nếu có)

        amount = None
        if amount_str:
            try:
                amount = abs(int(process_budget(amount_str)))
            except ValueError:
                await safe_send_message(
                    context.bot,
                    chat_id=chat_id,
                    text="❗ **Lỗi:** Số tiền phải là một số nguyên hợp lệ.",
                    parse_mode='Markdown'
                )
                return

        # 🟢 Sử dụng hàm mới để lấy danh sách bản ghi `pending`
        pending_records = budget_manager.get_pending_budgets_by_id(budget_id)
        logger.info(f"🟢 Danh sách bản ghi `pending` với ID `{budget_id}`: {pending_records}")
        if not pending_records:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text=f"❗ **Lỗi:** Không tìm thấy bản ghi `pending` nào với ID `{budget_id}`.",
                parse_mode='Markdown'
            )
            return

        # 🟢 Nếu có số tiền, cập nhật lại `amount`
        if amount is not None:
            for record in pending_records:
                budget_manager.update_budget(record["_id"], {"amount": amount})

        # 🟢 Cập nhật trạng thái `pending` thành `done`
        updated_count = budget_manager.update_budget_status(budget_id)

        # 🟢 Tính tổng ngân sách đã chi theo từng `contract_code`
        contract_codes = {record["contract_code"] for record in pending_records}

        total_budget_by_hd = budget_manager.get_current_budget(list(contract_codes),pending_records[0]["team"],chat_id)
        amount_done = amount if amount is not None else pending_records[0].get("amount", 0)
        
        success_message = (
            f"✅ **Cập nhật thành công!**\n"
            f"**ID:** `{budget_id}`\n"
            f"**Số tiền đã DONE:** `{format_number(amount_done)} VND`\n\n"
        )
        
        for code, total in total_budget_by_hd.items():
            success_message += f"+ **MÃ HD:** `{code}`\n  - **Tổng NS:** `{format_number(total)} VND`\n"

        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=success_message,
            parse_mode='Markdown'
        )
        logger.info(f"✅ Đã cập nhật `{updated_count}` bản ghi từ `pending` thành `done` với ID `{budget_id}`.")

    except Exception as e:
        logger.error(f"❌ Lỗi trong xử lý lệnh /done: {e}")
        await safe_send_message(
            context.bot,
            chat_id=update.effective_chat.id,
            text="❗ **Lỗi:** Đã xảy ra lỗi khi xử lý lệnh. Vui lòng thử lại.",
            parse_mode='Markdown'
        )

@allowed_room
@troly_only
async def handle_rf_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # Kiểm tra nếu là sửa tin nhắn
    if update.edited_message:
        logger.info("Bỏ qua tin nhắn đã sửa.")
        return

    user = update.effective_user
    user_id = user.id
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    username = user.username or "Không có username"
    full_name = f"{first_name} {last_name}".strip()

    logger.info(f"Người dùng: {full_name} (Username: {username}, ID: {user_id}) đã gọi lệnh /rf.")

    try:
        if len(context.args) < 3 or len(context.args) > 4:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text="❗ **Lỗi:** Vui lòng nhập đúng định dạng `/rf <tổ> <mã HD> <số tiền> [modifier]`.\n"
                     "Ví dụ: `/rf 1C HD1234 1000000 +`",
                parse_mode='Markdown'
            )
            return

        # Lấy tham số từ lệnh
        organization = context.args[0].strip().upper()
        contract_code = context.args[1].strip().upper()

        # Dùng hàm mới để chuẩn hóa mã hợp đồng
        contract_code = QuanLyABCVIP.convert_to_contract_code(contract_code)

        amount_str = context.args[2]
        modifier = context.args[3] if len(context.args) == 4 else None

        # Kiểm tra số tiền hợp lệ
        try:
            cleaned_amount_str = re.sub(r'\D', '', amount_str)
            amount = int(cleaned_amount_str) if cleaned_amount_str else 0
            if amount > 0:
                amount = -amount  # Refund => số tiền phải là âm
        except ValueError:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text="❗ **Lỗi:** Số tiền phải là một số nguyên hợp lệ.",
                parse_mode='Markdown'
            )
            return

        now = datetime.now()
        current_timestamp = 0
        logging.info(f"Modifier: {modifier}")

        # Xử lý thời gian theo modifier
        if modifier == '+' and now.day >= (now.replace(day=1) - timedelta(days=1)).day - 4:
            next_month = now.replace(day=28) + timedelta(days=4)
            first_day_next_month = next_month.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            current_timestamp = first_day_next_month.timestamp()
        elif modifier == '-' and now.day <= 5:
            last_month = now.replace(day=1) - timedelta(days=1)
            last_day_last_month = last_month.replace(hour=23, minute=59, second=59, microsecond=0)
            current_timestamp = last_day_last_month.timestamp()
        else:
            current_timestamp = time.time()

        # Kiểm tra tổ hợp lệ
        chat_title = update.effective_chat.title
        # Tạo mã ngẫu nhiên cho transaction
        random_code = generate_random_code(organization)

        # Ghi dữ liệu vào MongoDB
        inserted_id = budget_manager.add_budget(
            budget_id=random_code,
            team=organization,
            contract_code=contract_code,  # ✅ Gán mã hợp đồng vào đây
            group_name=chat_title,
            chat_id=chat_id,
            amount=amount,
            status="refund",
            timestamp=current_timestamp,
            assistant=full_name,
            note="Hoàn tiền",
            end_time=current_timestamp,
        )

        if not inserted_id:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text="❗ **Lỗi:** Không thể lưu dữ liệu vào hệ thống. Vui lòng thử lại.",
                parse_mode='Markdown'
            )
            logger.error("Lỗi khi ghi dữ liệu refund vào MongoDB.")
            return


        # ✅ Lấy tổng chi của contract_code (đúng format danh sách)
        contract_budget = budget_manager.get_current_budget([contract_code],organization,chat_id, False, current_timestamp)  # Đảm bảo là danh sách
        
        # Lấy tổng chi từ MongoDB
        total_chi = contract_budget.get(contract_code, 0)  # Trả về 0 nếu không có dữ liệu

        # Format thời gian
        dt_vn = datetime.fromtimestamp(current_timestamp, tz=timezone(timedelta(hours=7)))
        formatted_time = dt_vn.strftime("%H:%M %d/%m/%Y")

        # Gửi tin nhắn thành công
        success_message = (
            f"✅ **Dữ liệu đã được ghi thành công!**\n\n"
            f"**ID:** `{random_code}`\n"
            f"**TỔ:** {organization}\n"
            f"**MÃ HĐ:** `{contract_code}`\n"
            f"**TÊN NHÓM:** {chat_title}\n"
            f"**NGÂN SÁCH:** `{format_number(amount)} VND`\n"
            f"**TRẠNG THÁI:** refund\n"
            f"**THỜI GIAN:** {formatted_time}\n\n"
            f"**TỔNG CHI HIỆN TẠI:** `{format_number(total_chi) if total_chi else '0'} VND`\n"
        )
        
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=success_message,
            parse_mode='Markdown'
        )
        logger.info(f"Dữ liệu refund đã được ghi vào MongoDB: {organization}, {contract_code}, {amount} VND.")

    except Exception as e:
        logger.error(f"Lỗi trong xử lý lệnh /rf: {e}")
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text="❗ **Lỗi:** Đã xảy ra lỗi khi xử lý lệnh. Vui lòng thử lại.",
            parse_mode='Markdown'
        )

# @allowed_room
# @troly_only
# async def handle_tiktok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     chat_id = update.effective_chat.id
#     user = update.effective_user

#     try:
#         # Kiểm tra có đúng định dạng không
#         if len(context.args) != 1:
#             await safe_send_message(
#                 context.bot,
#                 chat_id=chat_id,
#                 text="❗ <b>Lỗi:</b> Vui lòng nhập đúng định dạng <code>/tiktok <username></code>",
#                 parse_mode='HTML'
#             )
#             return

#         username = context.args[0].strip()
#         group_name = update.effective_chat.title or f"{user.first_name or ''} {user.last_name or ''}".strip()
#         assistant = user.username or "unknown"

#         # Thông báo đang xử lý
#         await safe_send_message(
#             context.bot,
#             chat_id=chat_id,
#             text=f"🔄 Đang xử lý tạo TikTok user <code>{username}</code>...",
#             parse_mode='HTML'
#         )

#         # Gọi API
#         payload = {
#             "username": username,
#             "groupName": group_name,
#             "assistant": assistant
#         }

#         async with aiohttp.ClientSession() as session:
#             async with session.post(API_URL, json=payload) as response:
#                 result = await response.json()

#         # Trả kết quả cho user
#         if response.status == 201 and "user" in result:
#             user_data = result["user"]
#             msg = (
#                 f"✅ <b>Đã tạo thành công TikTok user:</b>\n\n"
#                 f"👤 <b>Username:</b> {user_data['username']}\n"
#                 f"🆔 <b>User ID:</b> <code>{user_data['user_id']}</code>\n"
#                 f"📛 <b>Nickname:</b> {user_data['nickname']}\n"
#             )
#         else:
#             msg = f"❌ <b>Tạo user thất bại:</b> {result.get('message', 'Không rõ lỗi')}"

#         await safe_send_message(
#             context.bot,
#             chat_id=chat_id,
#             text=msg,
#             parse_mode='HTML'
#         )

#     except Exception as e:
#         await safe_send_message(
#             context.bot,
#             chat_id=chat_id,
#             text=f"❗ <b>Lỗi hệ thống:</b> {str(e)}",
#             parse_mode='HTML'
#         )
        
@allowed_room
@troly_only
async def handle_check_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    try:
        # Lấy thông tin người dùng
        user = update.effective_user
        username = user.username or "Không có username"
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
        logger.info(f"Người dùng: {full_name} (Username: {username}) đã gọi lệnh /check.")

        # Kiểm tra và lấy tham số từ lệnh
        if len(context.args) != 2:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text="❗ <b>Lỗi:</b> Vui lòng nhập đúng định dạng <code>/check &lt;tổ&gt; &lt;mã hd&gt;</code>.\n\nVí dụ: <code>/check 1C HD12345</code>",
                parse_mode='HTML'
            )
            return

        organization = context.args[0].strip().upper()  # Tổ (viết hoa)
        mhd = context.args[1].strip().upper()  # Mã hợp đồng (viết hoa)
        
        
        mhd_input = context.args[1].strip().upper()  # Mã hợp đồng gốc
        
        mhd_list = [mhd_input]
        # 🟢 Lấy tổng chi tiêu của tổ và mã hợp đồng trong tháng hiện tại

        logger.info(f"📤 Gọi get_current_budget với các tham số:")
        logger.info(f"   - mhd_list: {mhd_list}")
        logger.info(f"   - organization: {organization}")
        logger.info(f"   - chat_id: {chat_id}")
        logger.info(f"   - original_contract_code: {mhd_list[0]}")


        current_budgets = budget_manager.get_current_budget(mhd_list, organization,chat_id , original_contract_code=mhd_list[0]) or {}

        # 🟢 Lấy giá trị từ dictionary, mặc định là 0 nếu không có
        total_expenses = current_budgets.get(mhd, 0)

        # # Gửi kết quả cho người dùng
        # await safe_send_message(
        #     context.bot,
        #     chat_id=chat_id,
        #     text=(
        #         f"✅ <b>Kết quả kiểm tra:</b>\n\n"
        #         f"<b>TỔ:</b> {organization}\n"
        #         f"<b>MÃ HD:</b> <code>{mhd}</code>\n"
        #         f"<b>TỔNG CHI TIÊU:</b> <code>{format_number(total_expenses)} VND</code>"
        #     ),
        #     parse_mode='HTML'
        # )
        
        total_expenses = current_budgets.get(mhd, 0)
        response_text = (
            f"✅ <b>Kết quả kiểm tra:</b>\n\n"
            f"<b>TỔ:</b> {organization}\n"
            f"<b>MÃ HD:</b> <code>{mhd}</code>\n"
            f"<b>TỔNG CHI TIÊU:</b> <code>{format_number(total_expenses)} VND</code>"
        )
            

        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=response_text,
            parse_mode='HTML'
        )

        
        logger.info(f"Đã kiểm tra ngân sách: Tổ {organization}, Mã HD {mhd}, Tổng chi tiêu: {total_expenses}.")

    except Exception as e:
        logger.error(f"Lỗi trong xử lý lệnh /check: {e}", exc_info=True)
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text="❗ <b>Lỗi:</b> Đã xảy ra lỗi khi xử lý lệnh. Vui lòng thử lại.",
            parse_mode='HTML'
        )


@allowed_room
@troly_only
async def handle_tiktok_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    group_name = update.effective_chat.title or f"{user.first_name or ''} {user.last_name or ''}".strip()
    assistant = user.username or "unknown"

    try:
        # 1) parse args thành list uids
        if not context.args:
            return await safe_send_message(
                context.bot, chat_id,
                "❗ Vui lòng nhập ít nhất một UID, ví dụ:\n"
                "/tiktok user1,user2,user3"
            )
        args_str = " ".join(context.args)
        uids = [u.strip() for u in args_str.split(",") if u.strip()]
        if not uids:
            return await safe_send_message(
                context.bot, chat_id,
                "❗ Không tìm thấy UID hợp lệ nào trong input."
            )

        # 2) gọi API bulk-check
        await safe_send_message(
            context.bot, chat_id,
            f"🔄 Đang kiểm tra {len(uids)} user trên TikTok..."
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(API_BULK_CHECK, json={"uids": uids}, timeout=20) as resp:
                    result = await resp.json()
                    # 👇 log toàn bộ response để debug
                    logger.info(f"API_BULK_CHECK raw response: {result}")
        except aiohttp.ClientError as ce:
            logger.error(f"Lỗi mạng khi gọi API_BULK_CHECK: {ce}", exc_info=True)
            return await safe_send_message(
                context.bot, chat_id,
                "❌ Lỗi kết nối tới server kiểm tra TikTok. Vui lòng thử lại sau."
            )
            
        except Exception as je:
            logger.error(f"Lỗi khi parse JSON từ API_BULK_CHECK: {je}", exc_info=True)
            return await safe_send_message(
                context.bot, chat_id,
                "❌ Lỗi xử lý dữ liệu trả về từ server TikTok."
            )

        data = result.get("data", [])

        # lưu tạm để callback dùng tiếp
        context.user_data["tiktok_bulk_data"] = data

        # 3) build message
        lines = []
        for idx, info in enumerate(data):
            uid = uids[idx]
            logger.info(f"Xử lý UID={uid}, info={info}")

            if not info or not info.get("userInfo"):
                # không có thông tin user => chắc chắn không tồn tại trên TikTok
                msg = info.get("message", "Không tìm thấy trên TikTok")
                lines.append(f"• <b>{uid}</b>: {msg}")
            else:
                ui = info["userInfo"]
                let = (
                    f"• <b>{ui['username']}</b> (ID: <code>{ui['user_id']}</code>)\n"
                    f"    Nickname: {ui.get('nickname','–')}, Status: {ui.get('status','–')}"
                )
                if info.get("exists"):   # tồn tại trong hệ thống
                    let += "\n    ❌ <b>Đã tồn tại trong hệ thống</b>"
                else:                    # mới, chưa có trong hệ thống
                    let += "\n    ✅ <b>Chưa có trong hệ thống</b>"
                lines.append(let)

        text = (
            "🔍 <b>Kết quả kiểm tra:</b>\n"
            + "\n".join(lines)
            + "\n\nBạn có muốn lưu (hoặc cập nhật) những tài khoản này không?"
        )

        # inline keyboard Yes / No
        kb = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Có",    callback_data="tiktok_bulk_yes"),
                InlineKeyboardButton("❌ Không", callback_data="tiktok_bulk_no")
            ]
        ])
        await safe_send_message(
            context.bot, chat_id,
            text, parse_mode="HTML", reply_markup=kb
        )

    except Exception as e:
        logger.error(f"Lỗi trong xử lý lệnh /tiktok bulk-check: {e}", exc_info=True)
        await safe_send_message(
            context.bot, chat_id,
            f"❗ <b>Lỗi hệ thống:</b> {str(e)}",
            parse_mode="HTML"
        )



async def handle_tiktok_bulk_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi user bấm 'Có'"""
    query = update.callback_query
    await query.answer()

    data = context.user_data.get("tiktok_bulk_data", [])
    user = update.effective_user
    group_name = update.effective_chat.title or f"{user.first_name or ''} {user.last_name or ''}".strip()
    assistant = user.username or "unknown"

    # Lấy ra chỉ những tài khoản chưa tồn tại (exists == False) và có userInfo
    to_save = [
        {
            **info["userInfo"],
            "groupName": group_name,
            "assistant": assistant,
        }
        for info in data
        if info
        and not info.get("exists")
        and info.get("userInfo") is not None
    ]
    
    old_text = query.message.text or ""
    clean_text = old_text.split("\n\nBạn có muốn")[0].strip()
    
    
    if not to_save:
        return await query.edit_message_text(f"{clean_text}\n\n❗ Không có tài khoản mới để lưu.")

    # Gọi API bulk-save với mảng userInfo của các tài khoản mới
    async with aiohttp.ClientSession() as session:
        async with session.post(
            API_BULK_SAVE,
            json=to_save,
            headers={'Content-Type': 'application/json'}
        ) as resp:
            res = await resp.json()

    if resp.status in (200, 201):
        new_text = f"{clean_text}\n\n✅ Đã lưu thành công các tài khoản mới vào hệ thống!"
    else:
        new_text = f"{clean_text}\n\n❌ Lưu thất bại: {res.get('message','Không rõ lỗi')}"

    await query.edit_message_text(new_text, parse_mode="HTML")



async def handle_tiktok_bulk_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi user bấm 'Không'"""
    query = update.callback_query
    await query.answer()
    old_text = query.message.text or ""
    clean_text = old_text.split("\n\nBạn có muốn")[0].strip()
    await query.edit_message_text(f"{clean_text}\n\n❌ Đã hủy thao tác lưu tài khoản.")

@allowed_room
@troly_only
async def handle_facebook_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    # 1) parse args thành list uids
    if not context.args:
        return await safe_send_message(
            context.bot, chat_id,
            "❗ Vui lòng nhập ít nhất một Facebook username, ví dụ:\n"
            "/facebook truong.the.tung,nguyen.van.a,pham.thi.b"
        )
    args_str = " ".join(context.args)
    uids = [u.strip() for u in args_str.split(",") if u.strip()]
    if not uids:
        return await safe_send_message(
            context.bot, chat_id,
            "❗ Không tìm thấy username hợp lệ nào."
        )

    # 2) gọi API bulk-check
    await safe_send_message(
        context.bot, chat_id,
        f"🔄 Đang kiểm tra {len(uids)} user trên Facebook..."
    )

    async with aiohttp.ClientSession() as session:
        async with session.post(API_FACEBOOK_BULK_CHECK, json={"uids": uids}) as resp:
            result = await resp.json()
            logger.info(f"API_FACEBOOK_BULK_CHECK raw response: {result}")

    data = result.get("data", [])

    # lưu tạm để callback dùng tiếp
    context.user_data["facebook_bulk_data"] = data

    # 3) build message kết quả
    lines = []
    for idx, info in enumerate(data):
        uid = uids[idx]

        # 🧩 Nếu info None hoặc userInfo None thì hiển thị lỗi cụ thể
        if not info or not info.get("userInfo"):
            msg = info.get("message", "Không tìm thấy thông tin.")
            lines.append(f"• <b>{uid}</b>: {msg}")
            continue  # bỏ qua phần dưới

        # ✅ Nếu có userInfo thì xử lý bình thường
        ui = info["userInfo"]
        let = (
            f"• <b>{ui.get('username','(không có username)')}</b> "
            f"(ID: <code>{ui.get('user_id','–')}</code>)\n"
            f"    Nickname: {ui.get('nickname','–')}, "
            f"Type: {ui.get('type','–')}, Status: {ui.get('status','–')}"
        )

        if info.get("exists"):   # tồn tại trong hệ thống
            let += "\n    ❌ <b>Đã tồn tại trong hệ thống</b>"
        else:                    # mới, chưa có trong hệ thống
            let += "\n    ✅ <b>Chưa có trong hệ thống</b>"

        lines.append(let)

    # Nếu không có user hợp lệ nào thì dừng luôn
    if not lines:
        return await safe_send_message(context.bot, chat_id, "❗ Không có dữ liệu hợp lệ để hiển thị.")

    text = (
        "🔍 <b>Kết quả kiểm tra Facebook users:</b>\n"
        + "\n".join(lines)
        + "\n\nBạn có muốn lưu (hoặc cập nhật) những tài khoản này không?"
    )

    # 🧩 Kiểm tra: nếu không có user mới (exists == False) thì không hiện nút
    has_new_user = any(info.get("userInfo") and not info.get("exists") for info in data)
    if not has_new_user:
        return await safe_send_message(context.bot, chat_id, text, parse_mode="HTML")

    # Nếu có user mới → hiện Yes/No
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Có", callback_data="facebook_bulk_yes"),
            InlineKeyboardButton("❌ Không", callback_data="facebook_bulk_no")
        ]
    ])

    await safe_send_message(
        context.bot, chat_id,
        text, parse_mode="HTML", reply_markup=kb
    )



async def handle_facebook_bulk_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi user bấm 'Có' cho Facebook"""
    query = update.callback_query
    await query.answer()

    data = context.user_data.get("facebook_bulk_data", [])
    # chỉ lấy những record exists=False và có userInfo
    user = update.effective_user
    group_name = update.effective_chat.title or f"{user.first_name or ''} {user.last_name or ''}".strip()
    assistant = user.username or "unknown"

    # Lấy ra chỉ những tài khoản chưa tồn tại (exists == False) và có userInfo
    to_save = [
        {
            **info["userInfo"],
            "groupName": group_name,
            "assistant": assistant,
        }
        for info in data
        if info
        and not info.get("exists")
        and info.get("userInfo") is not None
    ]
    
    old_text = query.message.text or ""
    clean_text = old_text.split("\n\nBạn có muốn")[0].strip()
    
    if not to_save:
        return await query.edit_message_text(f"{clean_text}\n\n❗ Không có tài khoản mới để lưu.")

    # gọi API bulk-save
    async with aiohttp.ClientSession() as session:
        async with session.post(
            API_FACEBOOK_BULK_SAVE,
            json=to_save,
            headers={'Content-Type': 'application/json'}
        ) as resp:
            res = await resp.json()

    
    if resp.status in (200, 201):
        new_text = f"{clean_text}\n\n✅ Đã lưu thành công các tài khoản mới vào hệ thống!"
    else:
        new_text = f"{clean_text}\n\n❌ Lưu thất bại: {res.get('message','Không rõ lỗi')}"

    await query.edit_message_text(new_text, parse_mode="HTML")


async def handle_facebook_bulk_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Xử lý khi user bấm 'Không' cho Facebook"""
    query = update.callback_query
    await query.answer()
    old_text = query.message.text or ""
    clean_text = old_text.split("\n\nBạn có muốn")[0].strip()
    await query.edit_message_text(f"{clean_text}\n\n❌ Đã hủy thao tác lưu Facebook user.")


@allowed_room
@troly_only
async def handle_note_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if update.edited_message:
        logger.info("Bỏ qua tin nhắn đã sửa.")
        return

    try:
        # Lấy thông tin người dùng
        user = update.effective_user
        username = user.username or "Không có username"
        full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

        logger.info(f"Người dùng: {full_name} (Username: {username}) đã gọi lệnh /note.")

        # Kiểm tra tham số đầu vào
        if len(context.args) < 2:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text="❗ **Lỗi:** Vui lòng nhập đúng định dạng `/note <[DTN,TC,NB]> Nội dung`. Ví dụ: `/note DTN Đây là ghi chú.`",
                parse_mode='Markdown'
            )
            return

        # Kiểm tra loại ghi chú hợp lệ
        note_type = context.args[0].strip().upper()
        valid_types = {"DTN": "Đối Tác Ngoài", "TC": "Tự Chạy", "NB": "Nội Bộ"}
        if note_type not in valid_types:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text="❗ **Lỗi:** Tham số loại phải là một trong các giá trị [DTN, TC, NB].",
                parse_mode='Markdown'
            )
            return

        # Lấy nội dung ghi chú
        note_content = ' '.join(context.args[1:]).strip()
        if not note_content:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text="❗ **Lỗi:** Nội dung ghi chú không được để trống.",
                parse_mode='Markdown'
            )
            return

        # Lấy thời gian hiện tại
        current_time = datetime.now().timestamp()

        # Lấy thông tin nhóm chat
        chat_title = update.effective_chat.title or "Không rõ tên nhóm"

        # Lưu ghi chú vào MongoDB
        inserted_id = note_manager.add_note(
            chat_title=chat_title,
            note_type=valid_types[note_type],
            timestamp=current_time,
            note_content=note_content,
            assistant=f"{username} - {full_name}",
            chat_id=chat_id
        )

        if not inserted_id:
            await safe_send_message(
                context.bot,
                chat_id=chat_id,
                text="❗ **Lỗi:** Không thể lưu ghi chú vào hệ thống. Vui lòng thử lại.",
                parse_mode='Markdown'
            )
            return

        # Xóa các ghi chú quá hạn (quá 5 ngày)
        # deleted_notes = note_manager.delete_old_notes(days=5)

        # Thông báo thành công
        success_message = (
            f"✅ <b>Ghi chú đã được ghi thành công!</b>\n\n"
            f"<b>Thời Gian:</b> {datetime.fromtimestamp(current_time).strftime('%H:%M:%S - %d/%m/%Y')}\n"
        )
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text=success_message,
            parse_mode='HTML'
        )

    except Exception as e:
        logger.error(f"Lỗi trong xử lý lệnh /note: {e}", exc_info=True)
        error_message = (
            f"❗ **Lỗi:** {e}\n\n"
            f"**Người dùng:** {full_name} (Username: {username})"
        )

        await safe_send_message(
            context.bot,
            chat_id=ADMIN_IDS,
            text=error_message,
            parse_mode='Markdown'
        )
        await safe_send_message(
            context.bot,
            chat_id=chat_id,
            text="❗ **Lỗi:** Đã xảy ra lỗi khi xử lý lệnh. Vui lòng thử lại.",
            parse_mode="Markdown"
        )
        
        
@allowed_room
@troly_only
async def handle_tiktok_bulk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /tiktok_bulk nick1,nick2,nick3
    → gọi API POST /bulk-create với body { usernames: [...], groupName, assistant }
    """
    chat_id = update.effective_chat.id
    if not context.args:
        return await safe_send_message(
            context.bot, chat_id,
            "❗️ Vui lòng nhập danh sách username, ngăn cách bằng dấu phẩy.\n"
            "Ví dụ: /tiktok_bulk userA,userB,userC",
            parse_mode="HTML"
        )

    raw = " ".join(context.args)
    usernames = [u.strip() for u in raw.split(",") if u.strip()]
    payload = {
        "usernames": usernames,
        "groupName": update.effective_chat.title or "Private",
        "assistant": update.effective_user.username or update.effective_user.full_name
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(API_BULK_URL, json=payload) as resp:
            data = await resp.json()

    if resp.status not in (200, 207):
        return await safe_send_message(
            context.bot, chat_id,
            f"❌ Lỗi khi gọi bulk-create: {data.get('message','Không rõ lỗi')}"
        )

    # giả sử API trả về {"results":[{username,status,message,...},...]}
    lines = []
    for r in data.get("results", []):
        lines.append(f"{'✅' if r['status']=='created' else '❌'} {r['username']}: {r['message']}")

    await safe_send_message(
        context.bot, chat_id,
        "<b>Kết quả bulk tạo TikTok users:</b>\n" + "\n".join(lines),
        parse_mode="HTML"
    )

@allowed_room
@troly_only
async def handle_tiktok_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /tiktok_check nick
    → gọi API POST /check-exists-username với body { username }
    """
    chat_id = update.effective_chat.id
    if len(context.args) != 1:
        return await safe_send_message(
            context.bot, chat_id,
            "❗️ Vui lòng nhập đúng: /tiktok_check <username>",
            parse_mode="HTML"
        )

    username = context.args[0].strip()
    async with aiohttp.ClientSession() as session:
        async with session.post(API_CHECK_URL, json={"username": username}) as resp:
            data = await resp.json()

    if resp.status != 200:
        return await safe_send_message(
            context.bot, chat_id,
            f"❌ Lỗi khi kiểm tra: {data.get('message','Không rõ lỗi')}"
        )

    exists = data.get("exists", False)
    text = (
        f"🔍 Username <b>{username}</b> " +
        ("<b>đã tồn tại</b> trong hệ thống." if exists else "<b>chưa có</b>, có thể tạo mới.")
    )
    await safe_send_message(context.bot, chat_id, text, parse_mode="HTML")