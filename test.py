# file: test_timestamp.py
from datetime import datetime
from zoneinfo import ZoneInfo

# timezone Việt Nam
VN_TZ = ZoneInfo("Asia/Ho_Chi_Minh")

def timestamp_to_str(ts):
    """
    Chuyển timestamp (float/int) sang định dạng "dd/MM/yyyy HH:mm:ss"
    """
    try:
        ts = float(ts)
    except (ValueError, TypeError):
        ts = 0

    # Nếu timestamp quá lớn, tự động chia cho đúng
    if ts > 1e12:  # nanoseconds
        ts /= 1e9
    elif ts > 1e10:  # milliseconds
        ts /= 1e3

    dt = datetime.fromtimestamp(ts, tz=VN_TZ)
    return dt.strftime("%d/%m/%Y %H:%M:%S")


if __name__ == "__main__":
    ts = 1756097314.4514508
    print("Timestamp gốc:", ts)
    formatted = timestamp_to_str(ts)
    print("Chuyển sang string:", formatted)
