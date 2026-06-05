"""Giải mã gói BLE thành khối lượng (kg)."""

from __future__ import annotations

from app.config import WEIGHT_PARSER
from app.gatt_uuids import uuid_short

WEIGHT_MEASUREMENT_SHORT = "2a9d"
VENDOR_DATA_SHORT = "fff4"
VENDOR_NOTIFY_SHORTS = frozenset({"fff4", "ffe1", "ffe4", "ffe2"})

# UNI indexNew.vue — byte[1] hex
UNI_WEIGHT_TYPE_BYTES = frozenset({0x40, 0x50})
UNI_WEIGHT_TYPE_HEX = frozenset({"40", "50", "00"})
UNI_FRAME_HEX_LEN = 14


def is_uni_js_weight_frame(data: bytes) -> bool:
    """Nhận diện frame 7 byte JS/UNI (indexNew parseHexToType)."""
    return len(data) >= 7 and data[1] in UNI_WEIGHT_TYPE_BYTES


def bytes_to_hex_string(data: bytes) -> str:
    return "".join(f"{b:02x}" for b in data)


def parse_uni_hex_string(hex_str: str) -> dict | None:
    """parseHexToType — frame 7 byte (14 hex) từ app UNI."""
    cleaned = hex_str.replace(" ", "").strip()
    if len(cleaned) != UNI_FRAME_HEX_LEN:
        return None

    type_hex = cleaned[2:4]
    mid = cleaned[4:8].upper()
    tail = cleaned[8:12]

    if type_hex in UNI_WEIGHT_TYPE_HEX:
        value_hex = cleaned[4:12]
        if not all(c in "0123456789abcdefABCDEF" for c in value_hex):
            return None
        raw = int(value_hex, 16)
        kg = 10 * raw / 1000.0
        if type_hex == "50":
            kg = -kg
        if type_hex == "00":
            return None
        if kg == 0 or abs(kg) > 500:
            return None
        return {
            "kg": round(kg, 2),
            "stable": True,
            "source": "uni_js_weight",
            "uni_type": type_hex,
        }

    if mid == "C400" and len(tail) == 4:
        volts = int(tail, 16) / 100.0
        return {
            "kg": None,
            "stable": False,
            "source": "uni_js_voltage",
            "voltage_v": round(volts, 2),
        }

    if mid == "C500" and len(tail) == 4:
        temp_c = int(tail, 16) / 10.0
        return {
            "kg": None,
            "stable": False,
            "source": "uni_js_temperature",
            "temperature_c": round(temp_c, 1),
        }

    return None


def parse_uni_compat_packet(data: bytes) -> dict | None:
    """Chuyển notify bytes → hex 14 ký tự → parser UNI."""
    if len(data) < 7:
        return None
    hex_str = bytes_to_hex_string(data[:7])
    result = parse_uni_hex_string(hex_str)
    if result and result.get("kg") is not None:
        return result
    return None


def try_parse_uni_js(data: bytes) -> dict | None:
    """Ưu tiên parser UNI khi frame khớp chữ ký JS (byte[1]=0x40/0x50)."""
    if not is_uni_js_weight_frame(data):
        return None
    return parse_uni_compat_packet(data)


def parse_weight_measurement(data: bytes) -> float | None:
    """Bluetooth Weight Measurement (0x2A9D)."""
    if len(data) < 3:
        return None
    flags = data[0]
    raw = int.from_bytes(data[1:3], "little")
    if (flags & 0x01) == 0:
        return round(raw * 0.005, 3)
    return round(raw * 0.05 * 0.453592, 3)


def parse_chipsea_packet(data: bytes) -> dict | None:
    """Chipsea / FFF0 (Lenovo HS11, nhiều cân TQ)."""
    if is_uni_js_weight_frame(data):
        return None
    if len(data) == 2 and data[0] == 0xF2 and data[1] == 0x00:
        return None
    if len(data) < 7:
        return None
    b5, b6 = data[5], data[6]
    if (b5 & 0xF0) != 0xF0:
        return None
    kg = (((b5 & 0x0F) << 8) + b6) * 0.1
    if kg <= 0 or kg > 500:
        return None
    return {"kg": round(kg, 2), "stable": True, "source": "chipsea"}


def parse_ffe_salter(data: bytes) -> dict | None:
    """Salter / FFE1: byte5 * 256 + byte6 (gram hoặc 0.1g tùy firmware)."""
    if is_uni_js_weight_frame(data):
        return None
    if len(data) < 7:
        return None
    b5, b6 = data[5], data[6]
    for div in (1000.0, 100.0, 10.0):
        kg = (b5 * 256 + b6) / div
        if 0.5 <= kg <= 300:
            return {"kg": round(kg, 2), "stable": True, "source": "ffe_salter"}
    return None


def parse_ffe_qn(data: bytes) -> dict | None:
    """QN-scale: header 0x10, kg = BE(bytes[3:5]) / 100."""
    if len(data) < 6 or data[0] != 0x10:
        return None
    raw = (data[3] << 8) | data[4]
    kg = raw / 100.0
    if kg <= 0 or kg > 300:
        return None
    stable = len(data) > 5 and data[5] == 0x01
    return {"kg": round(kg, 2), "stable": stable, "source": "ffe_qn"}


def parse_generic(data: bytes) -> dict | None:
    """Thử UINT16 LE * 0.1 hoặc * 0.01 tại các offset."""
    if is_uni_js_weight_frame(data):
        return None
    best: dict | None = None
    for scale, label in ((0.1, "x0.1"), (0.01, "x0.01"), (0.005, "x0.005")):
        for offset in range(0, max(0, len(data) - 1)):
            raw = int.from_bytes(data[offset : offset + 2], "little")
            kg = raw * scale
            if 0.5 <= kg <= 300:
                if best is None or abs(kg - round(kg, 1)) < abs(
                    best["kg"] - round(best["kg"], 1)
                ):
                    best = {
                        "kg": round(kg, 2),
                        "stable": False,
                        "source": f"generic_{label}@{offset}",
                    }
    return best


def parse_uni_notify(data: bytes) -> dict | None:
    """Chỉ dùng parseHexToType UNI (7 byte đầu)."""
    if len(data) < 7:
        return None
    return parse_uni_hex_string(bytes_to_hex_string(data[:7]))


def parse_notify_payload(
    data: bytes,
    char_uuid: str,
    *,
    profile: str | None = None,
) -> dict | None:
    if not data:
        return None

    if WEIGHT_PARSER == "uni_js_only":
        return parse_uni_notify(data)

    # auto: UNI trước, fallback parser khác cho cân không dùng frame JS
    uni = try_parse_uni_js(data)
    if uni:
        return uni

    short = uuid_short(char_uuid)
    if short == WEIGHT_MEASUREMENT_SHORT:
        kg = parse_weight_measurement(data)
        if kg is not None:
            return {"kg": kg, "stable": True, "source": "wss_2a9d"}

    if short in VENDOR_NOTIFY_SHORTS:
        for parser in (parse_ffe_qn, parse_ffe_salter):
            result = parser(data)
            if result:
                return result

    chipsea = parse_chipsea_packet(data)
    if chipsea:
        return chipsea

    generic = parse_generic(data)
    if generic:
        return generic

    return None
