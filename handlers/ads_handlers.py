import re
import decorators
import logging
from db.ads_report import ads_reports_manager, hold_manager, nap_tien_manager
from telegram import Update
from telegram.ext import CallbackContext
from bson import ObjectId
from datetime import datetime, timezone, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackQueryHandler
from decorators import troly_only, allowed_room , hlv_or_troly
import uuid
from handlers.db_helpers import add_pending_rp, get_pending_rp, delete_pending_rp, add_pending_hold, get_pending_hold, delete_pending_hold, add_pending_naptien, get_pending_naptien, delete_pending_naptien

logger = logging.getLogger(__name__)
# pending_rp_data = {}
# pending_hold_data = {}
# pending_naptien_data = {}

import re

def format_tele(user) -> str:
    """Ưu tiên fullname, rơi về id nếu không có."""
    if user.first_name or user.last_name:
        fullname = f"{user.first_name} {user.last_name or ''}".strip()
        return fullname
    return f"id_{user.id}"


def clean_and_parse_text(text):
    """Làm sạch dữ liệu và trích xuất thông tin"""
    patterns = {
        # Bỏ date và ad_type ra khỏi patterns vì không còn lấy từ input
        "ad_ids": r"id\s*:\s*([\d, ]+)",  
        "spend": r"chi tiêu\s*:\s*([\d,.]+)",  
        "hold": r"hold\s*:\s*([\d,.]+)",  
        "mess_num": r"số mess\s*:\s*([\d,.]+)",  
        "id_bc": r"ID BC\s*:\s*(\S+)",
        "note": r"note\s*:\s*(.+)",  # Nếu có ghi chú
    }

    data = {
        "ad_ids": [],
        "spend": None,
        "hold": 0,
        "note": None,
        "mess_num": None,
        "id_bc": None
    }
    lines = text.split("\n")

    for line in lines:
        line = line.strip()
        for key, pattern in patterns.items():
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if key == "ad_ids":
                    data[key] = [id_.strip() for id_ in value.split(",") if id_.strip().isdigit()]
                elif key in ["spend", "hold", "mess_num"]:
                    spend_clean = re.sub(r"[^\d]", "", value)
                    data[key] = int(spend_clean) if spend_clean.isdigit() else None
                else:
                    data[key] = value
    return data


def parse_hold_text(text: str):
    """Parse dữ liệu từ /hold"""
    data = {"id_bc": None, "hold": None}

    id_match = re.search(r"ID BC\s*:\s*(\S+)", text, re.IGNORECASE)
    hold_match = re.search(r"Số tiền\s*:\s*([\d,.]+)", text, re.IGNORECASE)

    if id_match:
        data["id_bc"] = id_match.group(1).strip()
    if hold_match:
        clean = re.sub(r"[^\d]", "", hold_match.group(1))
        data["hold"] = int(clean) if clean else None

    return data


def parse_naptien_text(text: str):
    """Parse dữ liệu từ /naptien"""
    data = {"id_bc": None, "so_tien_nap": None, "ads": None}

    id_match = re.search(r"ID BC\s*:\s*(\S+)", text, re.IGNORECASE)
    nap_match = re.search(r"Số tiền nạp\s*:\s*([\d,.]+)", text, re.IGNORECASE)
    ads_match = re.search(r"ADS\s*:\s*@?(\S+)", text, re.IGNORECASE)

    if id_match:
        data["id_bc"] = id_match.group(1).strip()
    if nap_match:
        clean = re.sub(r"[^\d]", "", nap_match.group(1))
        data["so_tien_nap"] = int(clean) if clean else None
    if ads_match:
        data["ads"] = ads_match.group(1).strip()

    return data


async def handle_rp_command(message):
    """Xử lý lệnh /rp và yêu cầu xác nhận trước khi lưu"""
    user = message.from_user
    chat = message.chat
    text = message.caption if (message.video or message.photo or message.document) else message.text

    if not text:
        await message.reply_text("⚠ Vui lòng nhập nội dung báo cáo kèm theo lệnh /rp!")
        return

    parsed_data = clean_and_parse_text(text)

    # Tạo ad_date = hôm nay - 1 ngày (dd/mm)
    yesterday = datetime.now() - timedelta(days=1)
    ad_date = yesterday.strftime("%d/%m")

    # Tạo ad_type = Tiktok nếu có id_bc, ngược lại là Facebook
    ad_type = "Tiktok" if parsed_data["id_bc"] else "Facebook"

    # Kiểm tra trường bắt buộc (trừ date, ad_type)
    missing_fields = []
    if not parsed_data["ad_ids"]:
        missing_fields.append("ID Quảng Cáo")
    if not parsed_data["spend"]:
        missing_fields.append("Chi Tiêu")

    if missing_fields:
        error_message = "❌ Lỗi: Các trường sau đang bị thiếu:\n"
        error_message += "\n".join([f"- {field}" for field in missing_fields])
        await message.reply_text(error_message)
        return

    # Lưu tạm dữ liệu
    temp_id = str(uuid.uuid4())[:8]
    # pending_rp_data[temp_id] = {
    #     "ad_ids": parsed_data["ad_ids"],
    #     "spend": parsed_data["spend"],
    #     "ad_type": ad_type,
    #     "note": parsed_data["note"],
    #     "group_name": chat.title if chat.title else "Private",
    #     "group_id": chat.id,
    #     "sender": f"{user.full_name} (@{user.username})" if user.username else user.full_name,
    #     "ad_date": ad_date,
    #     "hold": parsed_data["hold"],
    #     "mess_num": parsed_data["mess_num"],
    #     "id_bc": parsed_data["id_bc"],
    # }
    
    add_pending_rp(temp_id, {
        "ad_ids": parsed_data["ad_ids"],
        "spend": parsed_data["spend"],
        "ad_type": ad_type,
        "note": parsed_data["note"],
        "group_name": chat.title if chat.title else "Private",
        "group_id": chat.id,
        "sender": f"{user.full_name} (@{user.username})" if user.username else user.full_name,
        "ad_date": ad_date,
        "hold": parsed_data["hold"],
        "mess_num": parsed_data["mess_num"],
        "id_bc": parsed_data["id_bc"],
        },
        datetime.now(timezone.utc).timestamp() 
    )

    # Tạo tin nhắn xác nhận
    lines = [
        "**Xác nhận lưu báo cáo?**\n",
        f"📅 Ngày: `{ad_date}`",
        f"🆔 ID QC: `{parsed_data['ad_ids']}`",
        f"💰 Chi tiêu: `{parsed_data['spend']:,}`",
        f"📂 Loại QC: `{ad_type}`"
    ]

    # Thêm các mục tùy điều kiện
    if parsed_data.get('id_bc'):
        lines.append(f"📝 ID BC: `{parsed_data['id_bc']}`")
    if parsed_data.get('mess_num'):
        lines.append(f"📝 Số mess: `{parsed_data['mess_num']}`")
    if parsed_data.get('note'):
        lines.append(f"📝 Ghi chú: `{parsed_data['note']}`")

    confirm_text = "\n".join(lines)

    keyboard = [
        [
            InlineKeyboardButton("✅ Yes", callback_data=f"rp_yes|{temp_id}"),
            InlineKeyboardButton("❌ No", callback_data=f"rp_no|{temp_id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(confirm_text, parse_mode="Markdown", reply_markup=reply_markup)


@decorators.troly_only
async def check_record(update: Update, context: CallbackContext):
    """Lệnh /check để kiểm tra bản ghi theo ID"""
    if len(context.args) == 0:
        await update.message.reply_text("⚠ Vui lòng nhập ID bản ghi để kiểm tra!", parse_mode="Markdown")
        return

    record_id = context.args[0]
    record = ads_reports_manager.get_report_by_id(record_id)

    if not record:
        await update.message.reply_text("❌ Không tìm thấy bản ghi với ID này!")
        return

    dt_vn = datetime.fromtimestamp(record["timestamp"], tz=timezone(timedelta(hours=7)))
    formatted_time = dt_vn.strftime("%H:%M %d/%m/%Y")

    formatted_spend = f"{record['spend']:,}".replace(",", ".")
    await update.message.reply_text(
        f"📌 **Chi tiết bản ghi:**\n🆔 **ID Quảng Cáo:** {', '.join(record['ad_ids'])}\n"
        f"💰 **Chi tiêu:** {formatted_spend}\n📅 **Thời gian:** {formatted_time}\n",
        parse_mode="Markdown"
    )


@decorators.troly_only
async def delete_record(update: Update, context: CallbackContext):
    """Lệnh /delete để ADMIN xóa bản ghi theo ID"""
    user = update.effective_user
    admin_name = f"{user.full_name} (@{user.username})" if user.username else user.full_name

    if len(context.args) == 0:
        await update.message.reply_text(
            "⚠ Vui lòng nhập ID bản ghi để xóa! Ví dụ: `/delete 65dc7f9a2c9c1a00124a63b5`",
            parse_mode="Markdown"
        )
        return

    record_id = context.args[0]  # Lấy ID từ câu lệnh

    # Kiểm tra xem ID có hợp lệ không
    try:
        object_id = ObjectId(record_id)
    except Exception:
        await update.message.reply_text("❌ ID bản ghi không hợp lệ! Vui lòng kiểm tra lại.")
        return

    # Gọi hàm xóa bản ghi
    response = ads_reports_manager.delete_report(object_id)

    # Nếu không tìm thấy bản ghi để xóa
    if "Không tìm thấy" in response:
        await update.message.reply_text(response, parse_mode="Markdown")
        return

    # Ghi log vào MongoDB
    logger.info(f"🗑 ADMIN đã xóa bản ghi:\n👤 Người xóa: {admin_name}\n🆔 ID bản ghi: {record_id}")

    # Gửi phản hồi về Telegram
    await update.message.reply_text(response, parse_mode="Markdown")

@troly_only 
async def handle_rp_callback(update, context):
    query = update.callback_query
    await query.answer()

    action, temp_id = query.data.split("|", 1)

    if action == "rp_yes":
        # data = pending_rp_data.pop(temp_id, None)
        data = get_pending_rp(temp_id)
        if not data:
            await query.edit_message_text("❌ Dữ liệu xác nhận đã hết hạn.")
            return

        # Lấy username người bấm YES
        username = query.from_user.username or f"id_{query.from_user.id}"
        full_name = update.effective_user.full_name
        data["confirmed_by"] = username  # thêm vào dữ liệu
        record_id = ads_reports_manager.save_ad_report(**data)
        if record_id:
            delete_pending_rp(temp_id)
            await query.edit_message_text(
                f"✅ <b>Dữ liệu đã được lưu vào hệ thống!</b>\n"
                f"🆔 <b>ID bản ghi:</b> <code>{record_id}</code>\n"
                f"👤 <b>Người xác nhận:</b> <code>{full_name}</code>",
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text("❌ Lỗi: Không thể lưu báo cáo vào hệ thống.")

    elif action == "rp_no":
        # pending_rp_data.pop(temp_id, None)
        delete_pending_rp(temp_id)
        await query.edit_message_text("🚫 Đã hủy lưu báo cáo.")
        
async def hold_command(update: Update, context: CallbackContext):
    """Xử lý lệnh /hold để lưu dữ liệu hold"""
    message = update.message
    text = message.text

    parsed = parse_hold_text(text)
    if not parsed["id_bc"] or not parsed["hold"]:
        await message.reply_text("⚠ Vui lòng nhập đúng cú pháp:\n/hold\nID BC: ...\nSố tiền: ...")
        return

    ten_tele = format_tele(message.from_user)  # 👈 người chat lệnh

    temp_id = str(uuid.uuid4())[:8]
    # pending_hold_data[temp_id] = {
    #     "id_bc": parsed["id_bc"],
    #     "hold": parsed["hold"],
    #     "ten_tele": ten_tele,            # 👈 lưu tên tele ở bước này
    #     # KHÔNG set nguoi_hanh_dong ở đây
    # }
    
    add_pending_hold(temp_id, {
        "id_bc": parsed["id_bc"],
        "hold": parsed["hold"],
        "ten_tele": ten_tele,  # chỉ lưu tên tele ở đây
    }, datetime.now(timezone.utc).timestamp() )

    confirm_text = (
        f"<b>Xác nhận lưu HOLD?</b>\n"
        f"👤 Tên tele: <code>{ten_tele}</code>\n"
        f"🆔 ID BC: <code>{parsed['id_bc']}</code>\n"
        f"💰 Số tiền: <code>{parsed['hold']:,}</code>"
    )

    keyboard = [[
        InlineKeyboardButton("✅ Yes", callback_data=f"hold_yes|{temp_id}"),
        InlineKeyboardButton("❌ No",  callback_data=f"hold_no|{temp_id}")
    ]]
    
    await message.reply_text(
        confirm_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# @decorators.troly_only
async def handle_hold_callback(update: Update, context: CallbackContext):
    """Xử lý callback xác nhận hold"""
    query = update.callback_query
    await query.answer()

    action, temp_id = query.data.split("|", 1)

    if action == "hold_yes":
        # data = pending_hold_data.pop(temp_id, None)
        data = get_pending_hold(temp_id)
        if not data:
            await query.edit_message_text("❌ Dữ liệu xác nhận đã hết hạn.")
            return

        # 👇 người hành động là người bấm YES
        full_name = update.effective_user.full_name
        nguoi_hanh_dong = full_name

        # Lưu đủ 4 trường vào MongoDB thông qua hold_manager
        record_id = hold_manager.save_hold(
            id_bc=data["id_bc"],
            ten_tele=data["ten_tele"],     # người chat lệnh
            hold=data["hold"],
            nguoi_hanh_dong=nguoi_hanh_dong  # người bấm YES
        )

        if record_id:
            delete_pending_hold(temp_id)
            await query.edit_message_text(
                f"✅ <b>Đã lưu HOLD thành công!</b>\n"
                f"🪪 ID bản ghi: <code>{record_id}</code>\n"
                f"🆔 ID BC: <code>{data['id_bc']}</code>\n"
                f"👤 Tên tele: <code>{data['ten_tele']}</code>\n"
                f"💰 Hold: <code>{data['hold']:,}</code>\n"
                f"✍️ Người hành động: <code>{nguoi_hanh_dong}</code>",
                parse_mode="HTML"
            )
        else:
            await query.edit_message_text("❌ Lỗi khi lưu HOLD vào hệ thống.")

    elif action == "hold_no":
        delete_pending_hold(temp_id)
        # pending_hold_data.pop(temp_id, None)
        await query.edit_message_text("🚫 Đã hủy lưu HOLD.")
        
async def naptien_command(update: Update, context: CallbackContext):
    """Xử lý lệnh /naptien để lưu dữ liệu nạp tiền"""
    try:
        message = update.message
        text = message.text

        logging.info(f"[NAPTIEN] Nhận lệnh: {text} từ {message.from_user.username}")

        parsed = parse_naptien_text(text)
        logging.info(f"[NAPTIEN] Parsed data: {parsed}")

        if not parsed["id_bc"] or not parsed["so_tien_nap"] or not parsed["ads"]:
            await message.reply_text(
                "⚠ Vui lòng nhập đúng cú pháp:\n"
                "/naptien\nSố tiền nạp: ...\nID BC: ...\nADS: @username"
            )
            return

        ten_tele = format_tele(message.from_user)  # 👈 người chat lệnh
        temp_id = str(uuid.uuid4())[:8]

        # pending_naptien_data[temp_id] = {
        #     "id_bc": parsed["id_bc"],
        #     "so_tien_nap": parsed["so_tien_nap"],
        #     "ten_tele": ten_tele,
        #     "ads": parsed["ads"],  # để kiểm tra người confirm
        # }
        
        add_pending_naptien(temp_id, {
            "id_bc": parsed["id_bc"],
            "so_tien_nap": parsed["so_tien_nap"],
            "ten_tele": ten_tele,
            "ads": parsed["ads"],
        }, datetime.now(timezone.utc).timestamp() )

        # ✅ Dùng HTML thay vì Markdown
        confirm_text = (
            f"<b>Xác nhận NẠP TIỀN?</b>\n"
            f"🆔 ID BC: <code>{parsed['id_bc']}</code>\n"
            f"👤 Người nạp: <code>{message.from_user.username or message.from_user.full_name}</code>\n"
            f"💰 Số tiền: <code>{parsed['so_tien_nap']:,} VNĐ</code>\n"
            f"📢 Ads: @{parsed['ads']}"
        )

        keyboard = [
            [
                InlineKeyboardButton("✅ Yes", callback_data=f"naptien_yes|{temp_id}"),
                InlineKeyboardButton("❌ No", callback_data=f"naptien_no|{temp_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(confirm_text, parse_mode="HTML", reply_markup=reply_markup)

    except Exception as e:
        logging.exception("[NAPTIEN] Lỗi khi xử lý lệnh /naptien")
        await update.message.reply_text(f"❌ Lỗi khi xử lý lệnh /naptien: {e}")


async def handle_naptien_callback(update: Update, context: CallbackContext):
    """Xử lý callback xác nhận NẠP TIỀN"""
    query = update.callback_query
    await query.answer()

    action, temp_id = query.data.split("|", 1)

    # data = pending_naptien_data.get(temp_id)
    data = get_pending_naptien(temp_id)
    if not data:
        await query.edit_message_text("❌ Dữ liệu xác nhận đã hết hạn.")
        return

    user = query.from_user
    

    if action == "naptien_yes":
        if (user.username or "").lower() != data["ads"].lower():
            await query.answer("🚫 Bạn không có quyền xác nhận lệnh này!", show_alert=True)
            return
        # Lưu vào MongoDB qua manager
        record_id = nap_tien_manager.save_naptien(
            id_bc=data["id_bc"],
            ten_tele=data["ten_tele"],
            so_tien_nap=data["so_tien_nap"],
            nguoi_hanh_dong=user.full_name or user.username,
        )

        # pending_naptien_data.pop(temp_id, None)
        
        if record_id:
            delete_pending_naptien(temp_id)
            await query.edit_message_text(
                f"✅ <b>ĐÃ LƯU NẠP TIỀN thành công!</b>\n"
                f"🪪 ID bản ghi: <code>{record_id}</code>\n"
                f"🆔 ID BC: <code>{data['id_bc']}</code>\n"
                f"👤 Người nạp: <code>{data['ten_tele']}</code>\n"
                f"💰 Số tiền: <code>{data['so_tien_nap']:,} VNĐ</code>\n"
                f"✍️ Người xác nhận: <code>{user.full_name or user.username}</code>",
                parse_mode="HTML"
            )

    elif action == "naptien_no":
        # pending_naptien_data.pop(temp_id, None)
        delete_pending_naptien(temp_id)
        await query.edit_message_text(
            f"🚫 Lệnh nạp tiền đã bị <b>@{user.username or user.full_name}</b> hủy.",
            parse_mode="HTML"
        )