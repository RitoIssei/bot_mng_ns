import gspread
from oauth2client.service_account import ServiceAccountCredentials
import logging
import re

logger = logging.getLogger(__name__)

class GoogleSheetsManager:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize(*args, **kwargs)
        return cls._instance

    def _initialize(self, google_api_json, spreadsheet_key):
        self.google_api_json = google_api_json
        self.spreadsheet_key = spreadsheet_key
        self.client = None
        self.spreadsheet = None
        self._connect()

    def _connect(self):
        try:
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(self.google_api_json, scope)
            self.client = gspread.authorize(creds)
            self.spreadsheet = self.client.open_by_key(self.spreadsheet_key)
            logger.info("Kết nối thành công tới Google Sheets.")
        except Exception as e:
            logger.error(f"Lỗi khi kết nối tới Google Sheets: {e}")
            raise

    def get_worksheet(self, worksheet_name):
        try:
            return self.spreadsheet.worksheet(worksheet_name)
        except gspread.exceptions.WorksheetNotFound:
            logger.warning(f"Worksheet '{worksheet_name}' không tồn tại.")
            return None

    def create_worksheet(self, worksheet_name, rows=1000, cols=20):
        try:
            worksheet = self.spreadsheet.add_worksheet(title=worksheet_name, rows=str(rows), cols=str(cols))
            logger.info(f"Đã tạo worksheet mới: {worksheet_name}")
            return worksheet
        except Exception as e:
            logger.error(f"Lỗi khi tạo worksheet '{worksheet_name}': {e}")
            raise

    def write_row(self, worksheet, data):
        """
        Ghi một dòng dữ liệu vào worksheet.
        """
        try:
            worksheet.append_row(data)
            logger.info(f"Đã ghi dòng dữ liệu vào worksheet: {data}")
        except Exception as e:
            logger.error(f"Lỗi khi ghi dòng dữ liệu vào worksheet: {e}")
            raise

    def update_cell(self, worksheet, row, col, value):
        """
        Cập nhật giá trị của một ô cụ thể trong worksheet.
        """
        try:
            worksheet.update_cell(row, col, value)
            logger.info(f"Đã cập nhật ô ({row}, {col}) với giá trị: {value}")
        except Exception as e:
            logger.error(f"Lỗi khi cập nhật ô ({row}, {col}): {e}")
            raise

    def calculate_total_expenses(self, worksheet):
        """
        Tính tổng chi phí từ cột ngân sách và ô bổ sung.
        """
        try:
            # Đọc toàn bộ cột I (ngân sách) và bỏ qua tiêu đề, hàng đầu
            column_I_values = worksheet.col_values(6)[2:]  # Cột I từ hàng 3 trở đi

            # Làm sạch giá trị trong cột I và tính tổng nhanh
            total_chi = 0
            for val in column_I_values:
                if val:  # Kiểm tra không rỗng
                    cleaned_val = re.sub(r'[^\d-]', '', val)  # Chỉ giữ lại số và dấu âm
                    if re.match(r'^-?\d+$', cleaned_val):  # Kiểm tra nếu là số nguyên hợp lệ
                        total_chi += int(cleaned_val)

            # Lấy giá trị từ ô J1
            cell_J1 = worksheet.cell(1, 10).value  # J1 nằm ở hàng 1, cột 10
            logger.info(f"Giá trị ô J1 ban đầu: {cell_J1}")

            # Làm sạch giá trị ô J1
            if cell_J1:
                cleaned_cell_J1 = re.sub(r'[^\d-]', '', str(cell_J1))  # Loại bỏ ký tự không phải số và giữ dấu âm
            else:
                cleaned_cell_J1 = '0'

            # Chuyển giá trị J1 thành số nguyên
            try:
                cell_J1_value = int(cleaned_cell_J1)
            except ValueError:
                cell_J1_value = 0
                logger.warning(f"Không thể chuyển đổi giá trị ô J1 thành số nguyên. Sử dụng giá trị mặc định: {cell_J1_value}")

            logger.info(f"Giá trị số nguyên ô J1: {cell_J1_value}")

            # Tính tổng chi (bao gồm cột I và J1)
            total_expenses = total_chi + cell_J1_value
            logger.info(f"Tổng chi phí đã tính toán: {total_expenses}")

            return total_expenses
        except Exception as e:
            logger.error(f"Lỗi khi tính tổng chi phí: {e}")
            return 0
