import websocket
import json
import time
import threading
import config
import queue
import sys
import io

# Ghi đè sys.stdout và stderr để dùng UTF-8
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

class WebSocketClient:
    def __init__(self, url, reconnect_delay=1, ping_interval=30):
        self.url = url
        self.reconnect_delay = reconnect_delay
        self.ping_interval = ping_interval  # Khoảng thời gian gửi ping
        self.ws = None
        self.should_reconnect = True
        self.message_queue = queue.Queue()  # Hàng đợi để gửi dữ liệu WebSocket
        self.send_thread = threading.Thread(target=self._process_queue, daemon=True)
        self.ping_thread = threading.Thread(target=self._send_ping, daemon=True)  # Luồng ping riêng
        self.send_thread.start()
        self.ping_thread.start()  # Bắt đầu luồng gửi ping

    def connect(self):
        """Kết nối WebSocket và duy trì trong một luồng riêng."""
        while self.should_reconnect:
            try:
                print(f"🔌 Đang kết nối tới {self.url}...")

                self.ws = websocket.WebSocketApp(
                    self.url,
                    on_open=self.on_open,
                    on_message=self.on_message,
                    on_error=self.on_error,
                    on_close=self.on_close
                )

                # Chạy WebSocket trong một luồng riêng
                self.ws.run_forever()

            except Exception as e:
                print(f"❌ Lỗi kết nối WebSocket: {e}")

            print(f"⏳ Thử kết nối lại sau {self.reconnect_delay} giây...")
            time.sleep(self.reconnect_delay)

    def on_open(self, ws):
        print("✅ Kết nối WebSocket thành công!")

    def on_message(self, ws, message):
        print(f"📩 Nhận dữ liệu từ server: {message}")

    def on_error(self, ws, error):
        print(f"❌ Lỗi WebSocket: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("🔌 Kết nối WebSocket đã đóng. Đang thử kết nối lại...")

    def send_data(self, data):
        """Thêm dữ liệu vào hàng đợi để gửi trên luồng riêng."""
        self.message_queue.put(json.dumps(data))
        print(f"📤 Đã xếp hàng gửi dữ liệu: {data}")

    def _process_queue(self):
        """Xử lý hàng đợi gửi dữ liệu, chạy trên một luồng riêng."""
        while True:
            data = self.message_queue.get()
            if self.ws and self.ws.sock and self.ws.sock.connected:
                try:
                    self.ws.send(data)
                    print(f"✅ Đã gửi dữ liệu: {data}")
                except Exception as e:
                    print(f"❌ Lỗi khi gửi dữ liệu WebSocket: {e}")
                    self.message_queue.put(data)  # Gửi lại nếu lỗi
            else:
                print("⚠️ WebSocket chưa kết nối, xếp lại dữ liệu để gửi sau.")
                time.sleep(2)  # Chờ kết nối lại rồi gửi tiếp
                self.message_queue.put(data)  # Đưa lại vào hàng đợi

    def _send_ping(self):
        """Gửi ping định kỳ để duy trì kết nối."""
        while True:
            if self.ws and self.ws.sock and self.ws.sock.connected:
                try:
                    self.ws.send(json.dumps({"action": "ping"}))
                    print("🏓 Ping sent to server")
                except Exception as e:
                    print(f"❌ Lỗi khi gửi ping: {e}")
            time.sleep(self.ping_interval)  # Gửi lại sau 30 giây

    def start(self):
        """Khởi động WebSocket trong một luồng riêng."""
        thread = threading.Thread(target=self.connect, daemon=True)
        thread.start()

    def stop(self):
        """Dừng WebSocket."""
        self.should_reconnect = False
        if self.ws:
            self.ws.close()

# Tạo WebSocket client
ws_client = WebSocketClient(config.WS_URL)
ws_client.start()  # Chạy WebSocket trong một luồng riêng
