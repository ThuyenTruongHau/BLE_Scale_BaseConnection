"""Chuẩn hoá UUID BLE (16-bit → 128-bit)."""

from __future__ import annotations

BLUETOOTH_BASE = "00001000-8000-00805f9b34fb"

# Dịch vụ / đặc tính cân phổ biến
UUID_WEIGHT_SCALE_SERVICE = "0000181d-0000-1000-8000-00805f9b34fb"
UUID_WEIGHT_MEASUREMENT = "00002a9d-0000-1000-8000-00805f9b34fb"
UUID_VENDOR_FFF0 = "0000fff0-0000-1000-8000-00805f9b34fb"
UUID_VENDOR_FFF1_CMD = "0000fff1-0000-1000-8000-00805f9b34fb"
UUID_VENDOR_FFF4_DATA = "0000fff4-0000-1000-8000-00805f9b34fb"

# Nhiều cân TQ / Salter / QN dùng FFE0 (như MAC AB:0B:BE:93:8C:29)
UUID_VENDOR_FFE0 = "0000ffe0-0000-1000-8000-00805f9b34fb"
UUID_VENDOR_FFE1_NOTIFY = "0000ffe1-0000-1000-8000-00805f9b34fb"
UUID_VENDOR_FFE2_WRITE = "0000ffe2-0000-1000-8000-00805f9b34fb"
UUID_VENDOR_FFE3_CMD = "0000ffe3-0000-1000-8000-00805f9b34fb"
UUID_VENDOR_FFE4_NOTIFY = "0000ffe4-0000-1000-8000-00805f9b34fb"

CMD_CHIPSEA_READ_HISTORY = bytes([0xF2, 0x00])
# Salter-style wake; QN-scale request kg (ghi vào FFE3 nếu có)
CMD_FFE3_SALTER_WAKE = bytes([9, 3, 5])
CMD_FFE3_QN_MEASURE = bytes([0x13, 0x09, 0x15, 0x01, 0x10, 0x00, 0x00, 0x00, 0x42])


def normalize_address(address: str) -> str:
    """AB:0B:BE:93:8C:29 hoặc có dấu : thừa ở cuối."""
    parts = [p for p in address.strip().upper().split(":") if p]
    if len(parts) == 6 and all(len(p) == 2 for p in parts):
        return ":".join(parts)
    return address.strip().upper().rstrip(":")


def normalize_uuid(uuid: str) -> str:
    raw = uuid.strip().lower().replace("-", "")
    if len(raw) == 4:
        return f"0000{raw}-0000-1000-8000-00805f9b34fb"
    if len(raw) == 8:
        return f"{raw[:8]}-{raw[8:12]}-0000-1000-8000-00805f9b34fb"
    if len(raw) == 32:
        return (
            f"{raw[0:8]}-{raw[8:12]}-{raw[12:16]}-"
            f"{raw[16:20]}-{raw[20:32]}"
        )
    return uuid.strip().lower()


def uuid_short(uuid: str) -> str:
    """Lấy 4 ký tự hex giữa (vd. 2a9d, fff4)."""
    n = normalize_uuid(uuid).replace("-", "")
    if len(n) >= 8:
        return n[4:8]
    return n
