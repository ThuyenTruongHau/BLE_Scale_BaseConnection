# app_backend — BLE Scale Scanner

Quét thiết bị **BLE** trên Windows để kiểm tra cân có trong vùng phủ sóng hay không.  
**Không** dùng ghép đôi Bluetooth Classic trong Cài đặt Windows.

## Yêu cầu

- Windows 10/11, Bluetooth bật
- Python 3.10+
- (Tuỳ chọn UI) Node.js 18+

## Cài đặt

```powershell
cd app_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

## Chạy nhanh — CLI (không cần React)

```powershell
python cli.py
python cli.py --seconds 20
python connect_scale.py AA:BB:CC:DD:EE:FF --profile uni_compat --listen 120
```

Chuẩn **UNI** (app `__UNI__62E474F`): quy tắc BLE, công thức kg, ma trận tính năng và hướng dẫn người dùng — xem **[docs/huong_dan_can_ble.md](docs/huong_dan_can_ble.md)**.

## Chạy API + giao diện web

**Terminal 1 — backend:**

```powershell
cd app_backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend (dev):**

```powershell
cd app_backend\frontend
npm install
npm run dev
```

Mở http://localhost:5173 → **Bắt đầu quét**.

## API

| Method | Path | Mô tả |
|--------|------|--------|
| GET | `/api/health` | Trạng thái |
| GET | `/api/devices` | Danh sách thiết bị |
| POST | `/api/scan/start` | Body: `{"duration_sec": 15}` |
| POST | `/api/scan/stop` | Dừng quét |
| POST | `/api/gatt/probe` | GATT map có **index** service (so UNI `services[3]`) |
| GET | `/api/scale/gatt-map?address=` | Cùng format probe |
| GET | `/api/scale/status` | `last_reading` kể cả khi chưa parse được `kg` |
| POST | `/api/scale/connect` | Body: `{"address":"…","profile":"auto\|uni_compat\|uuid"}` |
| POST | `/api/scale/disconnect` | Ngắt cân |
| WS | `/ws` | `type: weight` (có `raw_hex` ngay cả khi `kg` null) |

## Xác nhận đúng là cân

1. Bật cân → quét 15s → ghi **MAC**.
2. Tắt cân → quét lại → MAC **biến mất** → khả năng cao là cân.
3. Nút **GATT** trên một dòng → lưu danh sách service UUID (đối chiếu sau khi có tài liệu SDK).

## Cấu hình `.env`

- `SCAN_SECONDS` — thời gian quét mặc định
- `NAME_HINTS` — từ khóa tên (mặc định có `JS` như app UNI)
- `SERVICE_HINTS` — UUID quảng cáo (`181d`, `fff0`, `ffe0`, …)
- `WEIGHT_PARSER` — `uni_js_only` (mặc định, chỉ công thức UNI `uni_js_weight`) hoặc `auto`

## Cấu trúc

```
app_backend/
  app/           # FastAPI + bleak (+ ble_profiles, gatt_map)
  docs/          # huong_dan_can_ble.md (quy tắc BLE + hướng dẫn)
  frontend/      # React UI
  cli.py         # Quét terminal
  connect_scale.py
  tests/         # test_uni_parser.py
  requirements.txt
```
