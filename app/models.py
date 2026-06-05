from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class DeviceRecord:
    address: str
    name: str | None = None
    rssi: int | None = None
    service_uuids: list[str] = field(default_factory=list)
    manufacturer_data: dict[str, str] = field(default_factory=dict)
    first_seen: datetime = field(default_factory=_utc_now)
    last_seen: datetime = field(default_factory=_utc_now)
    seen_count: int = 1

    def update_from_advertisement(
        self,
        *,
        name: str | None,
        rssi: int | None,
        service_uuids: list[str],
        manufacturer_data: dict[str, str],
    ) -> None:
        if name:
            self.name = name
        if rssi is not None:
            self.rssi = rssi
        if service_uuids:
            self.service_uuids = list(
                dict.fromkeys(self.service_uuids + service_uuids)
            )
        if manufacturer_data:
            self.manufacturer_data.update(manufacturer_data)
        self.last_seen = _utc_now()
        self.seen_count += 1

    def to_dict(self, *, likely_scale: bool) -> dict[str, Any]:
        return {
            "address": self.address,
            "name": self.name or "(không tên)",
            "rssi": self.rssi,
            "service_uuids": self.service_uuids,
            "manufacturer_data": self.manufacturer_data,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "seen_count": self.seen_count,
            "likely_scale": likely_scale,
        }
