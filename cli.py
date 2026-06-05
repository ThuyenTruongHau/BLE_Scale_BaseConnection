"""CLI: quét BLE hoặc kết nối cân nhận dữ liệu.

  python cli.py
  python cli.py --seconds 20
  python cli.py --connect AA:BB:CC:DD:EE:FF --listen 120
  python cli.py --auto --listen 120
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.ble_profiles import BleConnectProfile
from app.config import SCAN_SECONDS
from app.scale_client import BleScaleClient
from app.scanner import BleScannerService


def _print_reading(event: dict) -> None:
    if event.get("type") != "weight":
        return
    kg = event.get("kg")
    src = event.get("source", "")
    raw = event.get("raw_hex", "")
    if kg is not None:
        stable = "ổn định" if event.get("stable") else "đang đo"
        print(f"  → {kg} kg ({stable}) [{src}] raw={raw}")
    else:
        print(f"  → raw: {raw} [{src or 'unparsed'}]")


async def scan_devices(seconds: int) -> list[dict]:
    service = BleScannerService()
    print(f"Quét BLE trong {seconds}s — bật cân và đặt gần máy...")
    print("(Không cần ghép đôi Bluetooth trong Cài đặt Windows)\n")

    await service.start_scan(duration_sec=seconds)
    while service.is_scanning:
        await asyncio.sleep(0.3)
    return service.list_devices()


def print_device_list(devices: list[dict]) -> int:
    if not devices:
        print("Không thấy thiết bị BLE nào.")
        print("Kiểm tra: Bluetooth bật, cân ở chế độ discoverable.")
        return 1

    print(f"Tìm thấy {len(devices)} thiết bị:\n")
    for index, dev in enumerate(devices, 1):
        flag = " [GỢI Ý CÂN]" if dev["likely_scale"] else ""
        print(f"{index}. {dev['name']}{flag}")
        print(f"   MAC: {dev['address']}")
        print(f"   RSSI: {dev['rssi']}")
        if dev["service_uuids"]:
            print(f"   Services: {', '.join(dev['service_uuids'])}")
        if dev["manufacturer_data"]:
            print(f"   Mfr data: {dev['manufacturer_data']}")
        print()

    likely = [d for d in devices if d["likely_scale"]]
    if likely:
        print(f"Có {len(likely)} thiết bị khớp NAME_HINTS.")
    else:
        print("Không có tên khớp gợi ý — thử bật/tắt cân và so MAC xuất hiện/biến mất.")
    return 0


async def listen_scale(
    address: str,
    seconds: int,
    timeout: float,
    profile: BleConnectProfile,
) -> int:
    client = BleScaleClient()
    client.subscribe(_print_reading)

    print(f"Kết nối {address} (profile={profile}) …")
    result = await client.connect(address, timeout=timeout, profile=profile)
    if not result.get("ok"):
        print(result.get("message", "Lỗi kết nối"))
        return 1

    print(result.get("message", ""))
    print(f"  Profile dùng: {result.get('profile_used')}")
    if result.get("service_uuid"):
        print(
            f"  Service[{result.get('service_index')}]: {result.get('service_uuid')}"
        )
    for ch in result.get("notify_characteristics") or []:
        print(f"  Notify: {ch['uuid']}")
    if not result.get("notify_characteristics"):
        print("  Cảnh báo: không tìm thấy characteristic notify.")

    print(f"\nĐứng lên cân — lắng nghe {seconds}s (Ctrl+C dừng)\n")

    try:
        await asyncio.sleep(seconds)
    finally:
        await client.disconnect()
    return 0


async def run(
    seconds: int,
    connect: str | None,
    auto: bool,
    listen: int,
    timeout: float,
    profile: BleConnectProfile,
) -> int:
    if connect:
        return await listen_scale(connect, listen, timeout, profile)

    if auto:
        devices = await scan_devices(seconds)
        code = print_device_list(devices)
        if code != 0:
            return code
        likely = [d for d in devices if d["likely_scale"]]
        pick = likely[0] if likely else devices[0]
        print(f"\nTự kết nối: {pick['name']} ({pick['address']})\n")
        return await listen_scale(pick["address"], listen, timeout, profile)

    devices = await scan_devices(seconds)
    return print_device_list(devices)


def main() -> None:
    parser = argparse.ArgumentParser(description="BLE scale scanner / reader CLI")
    parser.add_argument("-s", "--seconds", type=int, default=SCAN_SECONDS)
    parser.add_argument("-c", "--connect", metavar="MAC", help="MAC đã quét")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Quét xong tự kết nối thiết bị gợi ý cân đầu tiên",
    )
    parser.add_argument("--listen", type=int, default=120)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--profile",
        choices=("auto", "uni_compat", "uuid"),
        default="auto",
        help="Chuẩn kết nối: auto (ưu tiên UNI service[3]), uni_compat, uuid",
    )
    args = parser.parse_args()

    try:
        code = asyncio.run(
            run(
                args.seconds,
                args.connect,
                args.auto,
                args.listen,
                args.timeout,
                args.profile,
            )
        )
    except KeyboardInterrupt:
        code = 130
    except Exception as exc:
        print(f"Lỗi: {exc}", file=sys.stderr)
        code = 1
    sys.exit(code)


if __name__ == "__main__":
    main()
