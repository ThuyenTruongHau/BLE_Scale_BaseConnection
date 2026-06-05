"""Kết nối nhanh tới cân đã biết MAC — python connect_scale.py AA:BB:CC:DD:EE:FF"""

from __future__ import annotations

import argparse
import asyncio
import sys

from cli import listen_scale


def main() -> None:
    parser = argparse.ArgumentParser(description="Kết nối BLE cân và in kg")
    parser.add_argument("address", help="MAC (vd. AA:BB:CC:DD:EE:FF)")
    parser.add_argument("--listen", type=int, default=120)
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument(
        "--profile",
        choices=("auto", "uni_compat", "uuid"),
        default="auto",
    )
    args = parser.parse_args()

    try:
        code = asyncio.run(
            listen_scale(
                args.address,
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
