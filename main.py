"""Chạy API + giao diện web: python main.py [--host 127.0.0.1] [--port 8000]"""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _windows_pid_on_port(port: int) -> str | None:
    if sys.platform != "win32":
        return None
    try:
        output = subprocess.check_output(
            ["netstat", "-ano"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    for line in output.splitlines():
        if f":{port} " in line and "LISTENING" in line:
            parts = line.split()
            if parts:
                return parts[-1]
    return None


def main() -> None:
    if sys.platform == "win32":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if reconfigure is not None:
                reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="BLE Scale Scanner API")
    parser.add_argument("--host", default="127.0.0.1", help="Địa chỉ lắng nghe")
    parser.add_argument("--port", type=int, default=8000, help="Cổng HTTP")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Tự tải lại khi sửa code (dev)",
    )
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("Thiếu uvicorn. Chạy: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

    print(f"API: http://{args.host}:{args.port}/api/health")
    print(f"Web: http://{args.host}:{args.port}/")
    print("Dừng server: Ctrl+C\n")

    if _port_in_use(args.host, args.port):
        pid = _windows_pid_on_port(args.port)
        print(
            f"Lỗi: cổng {args.port} đang được dùng"
            + (f" (PID {pid})" if pid else "")
            + ".",
            file=sys.stderr,
        )
        print(
            "Cách xử lý:",
            file=sys.stderr,
        )
        if pid:
            print(
                f"  taskkill /PID {pid} /F",
                file=sys.stderr,
            )
        print(
            f"  hoặc chạy: python main.py --port {args.port + 1}",
            file=sys.stderr,
        )
        sys.exit(1)

    try:
        uvicorn.run(
            "app.main:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
        )
    except OSError as exc:
        winerror = getattr(exc, "winerror", None)
        if winerror in (10048, 10013):
            print(f"Lỗi: không bind được cổng {args.port} — {exc}", file=sys.stderr)
            print(
                f"Thử cổng khác: python main.py --port {args.port + 1}",
                file=sys.stderr,
            )
            sys.exit(1)
        raise


if __name__ == "__main__":
    main()
