from __future__ import annotations

import asyncio
from typing import Callable

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from bleak.exc import BleakBluetoothNotAvailableError, BleakError

from app.ble_profiles import UNI_DEVICE_NAME_PREFIX
from app.config import NAME_HINTS, SERVICE_HINTS
from app.gatt_uuids import uuid_short
from app.models import DeviceRecord


def _format_manufacturer_data(data: dict[int, bytes]) -> dict[str, str]:
    return {str(company_id): value.hex() for company_id, value in data.items()}


def _service_hints_match(service_uuids: list[str]) -> bool:
    shorts = {uuid_short(u) for u in service_uuids}
    return any(uuid_short(h) in shorts for h in SERVICE_HINTS)


def is_likely_scale(record: DeviceRecord) -> bool:
    name = record.name or ""
    if name.upper().startswith(UNI_DEVICE_NAME_PREFIX):
        return True
    if _service_hints_match(record.service_uuids):
        return True
    lower = name.lower()
    if not lower:
        return False
    return any(hint.lower() in lower for hint in NAME_HINTS)


class BleScannerService:
    """Quét BLE LE — không ghép đôi Bluetooth Classic."""

    def __init__(self) -> None:
        self._devices: dict[str, DeviceRecord] = {}
        self._scanner: BleakScanner | None = None
        self._scan_task: asyncio.Task | None = None
        self._running = False
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[dict], None]] = []

    @property
    def is_scanning(self) -> bool:
        return self._running

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        self._listeners.append(callback)

    def _notify_listeners(self, payload: dict) -> None:
        for listener in list(self._listeners):
            try:
                listener(payload)
            except Exception:
                pass

    def _on_detection(
        self, device: BLEDevice, advertisement_data: AdvertisementData
    ) -> None:
        address = device.address
        name = device.name or advertisement_data.local_name
        service_uuids = list(advertisement_data.service_uuids or [])
        manufacturer = _format_manufacturer_data(
            advertisement_data.manufacturer_data or {}
        )
        rssi = advertisement_data.rssi

        existing = self._devices.get(address)
        if existing:
            existing.update_from_advertisement(
                name=name,
                rssi=rssi,
                service_uuids=service_uuids,
                manufacturer_data=manufacturer,
            )
            record = existing
        else:
            record = DeviceRecord(
                address=address,
                name=name,
                rssi=rssi,
                service_uuids=service_uuids,
                manufacturer_data=manufacturer,
            )
            self._devices[address] = record

        self._notify_listeners(
            {
                "type": "device",
                "device": record.to_dict(likely_scale=is_likely_scale(record)),
            }
        )

    def list_devices(self) -> list[dict]:
        items = list(self._devices.values())
        items.sort(
            key=lambda d: (
                not is_likely_scale(d),
                -(d.rssi if d.rssi is not None else -999),
            ),
        )
        return [d.to_dict(likely_scale=is_likely_scale(d)) for d in items]

    async def start_scan(self, duration_sec: int | None = None) -> dict:
        async with self._lock:
            if self._running:
                return {"ok": False, "message": "Đang quét rồi"}

            self._devices.clear()
            self._scanner = BleakScanner(detection_callback=self._on_detection)
            try:
                await self._scanner.start()
            except BleakBluetoothNotAvailableError:
                self._scanner = None
                return {
                    "ok": False,
                    "message": (
                        "Không tìm thấy Bluetooth trên máy. "
                        "Bật Bluetooth trong Cài đặt Windows → Bluetooth & thiết bị, "
                        "kiểm tra driver adapter (Device Manager), "
                        "rồi thử lại."
                    ),
                }
            except BleakError as exc:
                self._scanner = None
                return {"ok": False, "message": f"Lỗi Bluetooth: {exc}"}
            except Exception as exc:
                self._scanner = None
                return {"ok": False, "message": f"Không bắt đầu quét được: {exc}"}

            self._running = True

            if duration_sec and duration_sec > 0:

                async def _auto_stop() -> None:
                    await asyncio.sleep(duration_sec)
                    if self._running:
                        await self.stop_scan()

                self._scan_task = asyncio.create_task(_auto_stop())

            self._notify_listeners({"type": "status", "scanning": True})
            return {"ok": True, "message": "Đã bắt đầu quét BLE"}

    async def stop_scan(self) -> dict:
        async with self._lock:
            if not self._running:
                return {"ok": True, "message": "Không có phiên quét đang chạy"}

            if self._scan_task and not self._scan_task.done():
                self._scan_task.cancel()
                try:
                    await self._scan_task
                except asyncio.CancelledError:
                    pass
            self._scan_task = None

            if self._scanner:
                await self._scanner.stop()
                self._scanner = None

            self._running = False
            self._notify_listeners({"type": "status", "scanning": False})
            return {
                "ok": True,
                "message": "Đã dừng quét",
                "count": len(self._devices),
            }

    async def probe_gatt(self, address: str, timeout: float = 12.0) -> dict:
        """Kết nối GATT tạm để liệt kê service UUID (có index cho UNI)."""
        from app.gatt_map import fetch_gatt_map

        return await fetch_gatt_map(address, timeout=timeout)
