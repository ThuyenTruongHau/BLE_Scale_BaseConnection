from __future__ import annotations

import asyncio
from typing import Any, Callable

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic

from app.ble_profiles import (
    UNI_MTU,
    UNI_SERVICE_INDEX,
    UNI_WAKE_COMMANDS,
    BleConnectProfile,
)
from app.gatt_uuids import (
    CMD_CHIPSEA_READ_HISTORY,
    CMD_FFE3_QN_MEASURE,
    CMD_FFE3_SALTER_WAKE,
    UUID_VENDOR_FFE0,
    UUID_VENDOR_FFE1_NOTIFY,
    UUID_VENDOR_FFE2_WRITE,
    UUID_VENDOR_FFE3_CMD,
    UUID_VENDOR_FFF1_CMD,
    UUID_VENDOR_FFF4_DATA,
    UUID_WEIGHT_MEASUREMENT,
    normalize_address,
    normalize_uuid,
    uuid_short,
)
from app.weight_parser import parse_notify_payload

NotifyHandler = Callable[[dict[str, Any]], None]


def _char_props(char: BleakGATTCharacteristic) -> set[str]:
    return {p.lower() for p in char.properties}


def _pick_uni_service(client: BleakClient) -> Any | None:
    services = list(client.services)
    if len(services) <= UNI_SERVICE_INDEX:
        return None
    return services[UNI_SERVICE_INDEX]


def _uni_target_ready(client: BleakClient) -> bool:
    service = _pick_uni_service(client)
    if not service:
        return False
    has_notify = False
    has_write = False
    for char in service.characteristics:
        props = _char_props(char)
        if "notify" in props or "indicate" in props:
            has_notify = True
        if "write" in props or "write-without-response" in props:
            has_write = True
    return has_notify and has_write


async def _try_request_mtu(client: BleakClient, mtu: int = UNI_MTU) -> bool:
    try:
        backend = getattr(client, "_backend", None) or getattr(
            client, "backend", None
        )
        if backend and hasattr(backend, "request_mtu"):
            await backend.request_mtu(mtu)
            return True
    except Exception:
        pass
    return False


class BleScaleClient:
    """Giữ kết nối GATT và nhận notify cân."""

    def __init__(self) -> None:
        self._client: BleakClient | None = None
        self._address: str | None = None
        self._lock = asyncio.Lock()
        self._listeners: list[NotifyHandler] = []
        self._last_reading: dict[str, Any] | None = None
        self._subscribed: list[str] = []
        self._profile_used: BleConnectProfile | None = None

    @property
    def is_connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    @property
    def address(self) -> str | None:
        return self._address

    @property
    def last_reading(self) -> dict[str, Any] | None:
        return self._last_reading

    @property
    def profile_used(self) -> str | None:
        return self._profile_used

    def subscribe(self, callback: NotifyHandler) -> None:
        self._listeners.append(callback)

    def _notify(self, payload: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(payload)
            except Exception:
                pass

    def _handler(self, char: BleakGATTCharacteristic, data: bytearray) -> None:
        raw = bytes(data)
        parsed = parse_notify_payload(
            raw,
            char.uuid,
            profile=self._profile_used,
        )
        event: dict[str, Any] = {
            "type": "weight",
            "address": self._address,
            "char_uuid": char.uuid,
            "raw_hex": raw.hex(),
            "profile": self._profile_used,
        }
        if parsed:
            event.update(parsed)
        self._last_reading = {
            "address": self._address,
            "kg": parsed.get("kg") if parsed else None,
            "stable": parsed.get("stable", False) if parsed else False,
            "source": parsed.get("source", "") if parsed else "",
            "raw_hex": raw.hex(),
            "char_uuid": char.uuid,
            "profile": self._profile_used,
        }
        if parsed:
            for key in ("voltage_v", "temperature_c", "uni_type"):
                if key in parsed:
                    self._last_reading[key] = parsed[key]
        self._notify(event)

    async def _release_connection(self, *, notify: bool) -> str | None:
        if not self._client:
            return None

        client = self._client
        for uuid in list(self._subscribed):
            try:
                await client.stop_notify(uuid)
            except Exception:
                pass
        self._subscribed.clear()

        try:
            await client.disconnect()
        except Exception:
            pass

        addr = self._address
        self._client = None
        self._address = None
        self._profile_used = None
        if notify and addr:
            self._notify({"type": "scale_disconnected", "address": addr})
        return addr

    def _resolve_profile(
        self, client: BleakClient, profile: BleConnectProfile
    ) -> BleConnectProfile:
        if profile != "auto":
            return profile
        if _uni_target_ready(client):
            return "uni_compat"
        return "uuid"

    async def connect(
        self,
        address: str,
        timeout: float = 15.0,
        profile: BleConnectProfile = "auto",
    ) -> dict[str, Any]:
        address = normalize_address(address)
        async with self._lock:
            await self._release_connection(notify=False)

            client = BleakClient(address, timeout=timeout)
            try:
                await asyncio.wait_for(client.connect(), timeout=timeout + 5)
            except asyncio.TimeoutError:
                try:
                    await client.disconnect()
                except Exception:
                    pass
                return {
                    "ok": False,
                    "message": (
                        f"Hết thời gian {timeout}s — bật cân, đặt gần PC, "
                        "tắt app cân trên điện thoại rồi thử lại."
                    ),
                }
            except Exception as exc:
                return {"ok": False, "message": f"Không kết nối được: {exc}"}

            if not client.is_connected:
                return {"ok": False, "message": "Kết nối thất bại"}

            self._client = client
            self._address = address
            self._subscribed = []

            resolved = self._resolve_profile(client, profile)
            if resolved == "uni_compat" and not _uni_target_ready(client):
                return {
                    "ok": False,
                    "message": (
                        f"Không đủ service tại index {UNI_SERVICE_INDEX} "
                        "(cần notify + write) — thử profile=uuid hoặc GATT map."
                    ),
                }

            self._profile_used = resolved
            await _try_request_mtu(client)

            try:
                if resolved == "uni_compat":
                    setup = await asyncio.wait_for(
                        self._setup_uni_compat(client), timeout=20
                    )
                else:
                    setup = await asyncio.wait_for(
                        self._setup_uuid(client), timeout=20
                    )
            except asyncio.TimeoutError:
                await self._release_connection(notify=False)
                return {
                    "ok": False,
                    "message": "Kết nối được nhưng cấu hình notify quá lâu — thử lại.",
                }

            msg = (
                "Đã kết nối (chuẩn UNI: service[3]) — gửi lệnh cân, đứng lên thử."
                if resolved == "uni_compat"
                else "Đã kết nối cân — đứng lên cân để nhận dữ liệu"
            )
            return {
                "ok": True,
                "message": msg,
                "address": address,
                "profile_used": resolved,
                "profile_requested": profile,
                **setup,
            }

    async def _setup_uni_compat(self, client: BleakClient) -> dict[str, Any]:
        service = _pick_uni_service(client)
        if not service:
            return {
                "service_index": UNI_SERVICE_INDEX,
                "service_uuid": None,
                "notify_uuid": None,
                "write_uuid": None,
                "notify_characteristics": [],
                "hint": f"Thiếu service index {UNI_SERVICE_INDEX}.",
            }

        notify_char = None
        write_char = None
        notify_chars: list[dict[str, Any]] = []

        for char in service.characteristics:
            props = _char_props(char)
            if ("notify" in props or "indicate" in props) and not notify_char:
                notify_char = char
            if ("write" in props or "write-without-response" in props) and not write_char:
                write_char = char

        if notify_char:
            try:
                await client.start_notify(notify_char.uuid, self._handler)
                self._subscribed.append(notify_char.uuid)
                notify_chars.append(
                    {
                        "uuid": notify_char.uuid,
                        "properties": list(notify_char.properties),
                    }
                )
            except Exception as exc:
                notify_chars.append(
                    {
                        "uuid": notify_char.uuid,
                        "properties": list(notify_char.properties),
                        "error": str(exc),
                    }
                )

        if write_char:
            for cmd in UNI_WAKE_COMMANDS:
                try:
                    await client.write_gatt_char(
                        write_char.uuid, cmd, response=False
                    )
                    await asyncio.sleep(0.15)
                except Exception:
                    continue

        active = [c for c in notify_chars if "error" not in c]
        return {
            "service_index": UNI_SERVICE_INDEX,
            "service_uuid": service.uuid,
            "notify_uuid": notify_char.uuid if notify_char else None,
            "write_uuid": write_char.uuid if write_char else None,
            "vendor_service": uuid_short(service.uuid),
            "notify_characteristics": notify_chars,
            "hint": (
                "UNI: đã ghi lệnh 05 A9/C4/C5 — đợi notify 14 hex (7 byte)."
                if active and write_char
                else (
                    "UNI: thiếu notify hoặc write trên service[3]."
                    if not active
                    else "UNI: có notify nhưng không ghi được lệnh wake."
                )
            ),
        }

    async def _setup_uuid(self, client: BleakClient) -> dict[str, Any]:
        notify_chars: list[dict[str, str]] = []
        chipsea_cmd = None
        chipsea_data = None
        ffe3_cmd = None
        ffe2_write = None
        ffe1_notify = None
        weight_char = None
        has_ffe0 = False

        for service in client.services:
            if uuid_short(service.uuid) == uuid_short(UUID_VENDOR_FFE0):
                has_ffe0 = True
            for char in service.characteristics:
                props = _char_props(char)
                norm = normalize_uuid(char.uuid)

                if norm == normalize_uuid(UUID_WEIGHT_MEASUREMENT):
                    weight_char = char
                if norm == normalize_uuid(UUID_VENDOR_FFF1_CMD):
                    chipsea_cmd = char
                if norm == normalize_uuid(UUID_VENDOR_FFF4_DATA):
                    chipsea_data = char
                if norm == normalize_uuid(UUID_VENDOR_FFE1_NOTIFY):
                    ffe1_notify = char
                if norm == normalize_uuid(UUID_VENDOR_FFE2_WRITE):
                    ffe2_write = char
                if norm == normalize_uuid(UUID_VENDOR_FFE3_CMD):
                    ffe3_cmd = char

                if "notify" in props or "indicate" in props:
                    try:
                        await client.start_notify(char.uuid, self._handler)
                        self._subscribed.append(char.uuid)
                        notify_chars.append(
                            {
                                "uuid": char.uuid,
                                "properties": list(char.properties),
                            }
                        )
                    except Exception as exc:
                        notify_chars.append(
                            {
                                "uuid": char.uuid,
                                "properties": list(char.properties),
                                "error": str(exc),
                            }
                        )

        if chipsea_cmd and chipsea_data:
            try:
                await client.write_gatt_char(
                    chipsea_cmd.uuid, CMD_CHIPSEA_READ_HISTORY, response=False
                )
            except Exception:
                pass

        if has_ffe0 and ffe3_cmd:
            for cmd in (CMD_FFE3_QN_MEASURE, CMD_FFE3_SALTER_WAKE):
                try:
                    await client.write_gatt_char(
                        ffe3_cmd.uuid, cmd, response=False
                    )
                    break
                except Exception:
                    continue
        elif has_ffe0 and ffe2_write:
            for cmd in UNI_WAKE_COMMANDS:
                try:
                    await client.write_gatt_char(
                        ffe2_write.uuid, cmd, response=False
                    )
                    await asyncio.sleep(0.15)
                except Exception:
                    continue

        if ffe1_notify and ffe1_notify.uuid not in self._subscribed:
            try:
                await client.start_notify(ffe1_notify.uuid, self._handler)
                self._subscribed.append(ffe1_notify.uuid)
                notify_chars.append(
                    {
                        "uuid": ffe1_notify.uuid,
                        "properties": list(ffe1_notify.properties),
                    }
                )
            except Exception as exc:
                notify_chars.append(
                    {
                        "uuid": ffe1_notify.uuid,
                        "properties": list(ffe1_notify.properties),
                        "error": str(exc),
                    }
                )

        if weight_char and weight_char.uuid not in self._subscribed:
            try:
                await client.start_notify(weight_char.uuid, self._handler)
                self._subscribed.append(weight_char.uuid)
                notify_chars.append(
                    {
                        "uuid": weight_char.uuid,
                        "properties": list(weight_char.properties),
                    }
                )
            except Exception:
                pass

        active = [c for c in notify_chars if "error" not in c]
        return {
            "service_index": None,
            "service_uuid": None,
            "notify_uuid": None,
            "write_uuid": None,
            "vendor_service": "ffe0" if has_ffe0 else None,
            "notify_characteristics": notify_chars,
            "hint": (
                "Service FFE0 có nhưng chưa bật được notify — bật cân, đứng lên thử lại."
                if has_ffe0 and not active
                else (
                    "Không có characteristic notify — cần xem GATT chi tiết."
                    if not active
                    else f"Đang lắng nghe {len(active)} characteristic (FFE0={has_ffe0})"
                )
            ),
        }

    async def disconnect(self) -> dict[str, Any]:
        async with self._lock:
            if not self._client:
                return {"ok": True, "message": "Chưa kết nối"}
            addr = await self._release_connection(notify=True)
            return {"ok": True, "message": "Đã ngắt kết nối", "address": addr}
