"""GATT map có index service — so sánh với UNI services[3]."""

from __future__ import annotations

from typing import Any

from bleak import BleakClient

from app.ble_profiles import UNI_SERVICE_INDEX
from app.gatt_uuids import normalize_address, uuid_short


def build_gatt_map(client: BleakClient) -> list[dict[str, Any]]:
    services: list[dict[str, Any]] = []
    for index, service in enumerate(client.services):
        chars = []
        has_notify = False
        has_write = False
        for char in service.characteristics:
            props = {p.lower() for p in char.properties}
            if "notify" in props or "indicate" in props:
                has_notify = True
            if "write" in props or "write-without-response" in props:
                has_write = True
            chars.append(
                {
                    "uuid": char.uuid,
                    "uuid_short": uuid_short(char.uuid),
                    "properties": list(char.properties),
                }
            )
        services.append(
            {
                "index": index,
                "uuid": service.uuid,
                "uuid_short": uuid_short(service.uuid),
                "description": service.description or "",
                "has_notify": has_notify,
                "has_write": has_write,
                "is_uni_target": index == UNI_SERVICE_INDEX,
                "characteristics": chars,
            }
        )
    return services


def gatt_map_summary(services: list[dict[str, Any]]) -> dict[str, Any]:
    uni_target = next(
        (s for s in services if s.get("is_uni_target")),
        None,
    )
    has_ffe0 = any(s.get("uuid_short") == "ffe0" for s in services)
    return {
        "service_count": len(services),
        "uni_service_index": UNI_SERVICE_INDEX,
        "uni_target": uni_target,
        "has_ffe0": has_ffe0,
        "uni_target_ready": bool(
            uni_target
            and uni_target.get("has_notify")
            and uni_target.get("has_write")
        ),
    }


async def fetch_gatt_map(address: str, timeout: float = 12.0) -> dict[str, Any]:
    address = normalize_address(address)
    try:
        async with BleakClient(address, timeout=timeout) as client:
            if not client.is_connected:
                return {"ok": False, "address": address, "message": "Không kết nối được GATT"}
            services = build_gatt_map(client)
            return {
                "ok": True,
                "address": address,
                "services": services,
                **gatt_map_summary(services),
            }
    except Exception as exc:
        return {"ok": False, "address": address, "message": str(exc)}
