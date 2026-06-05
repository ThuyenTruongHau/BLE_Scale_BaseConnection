"""Profile kết nối BLE — đồng bộ với UNI vehicleMounted."""

from __future__ import annotations

from typing import Literal

BleConnectProfile = Literal["uuid", "uni_compat", "auto"]

UNI_SERVICE_INDEX = 3
UNI_MTU = 512

# indexNew.vue — gửi qua characteristic write (service[3])
UNI_CMD_GET_WEIGHT = bytes.fromhex("05A9000000AE")
UNI_CMD_GET_VOLTAGE = bytes.fromhex("05C4000000C9")
UNI_CMD_GET_TEMPERATURE = bytes.fromhex("05C5000000CA")

UNI_WAKE_COMMANDS: tuple[bytes, ...] = (
    UNI_CMD_GET_WEIGHT,
    UNI_CMD_GET_VOLTAGE,
    UNI_CMD_GET_TEMPERATURE,
)

# utils/bluetooth.js — lọc tên thiết bị khi quét
UNI_DEVICE_NAME_PREFIX = "JS"
