from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel, Field

from app.ble_profiles import BleConnectProfile
from app.config import CORS_ORIGINS, SCAN_SECONDS
from app.gatt_map import fetch_gatt_map
from app.scale_client import BleScaleClient
from app.scanner import BleScannerService

scanner = BleScannerService()
scale = BleScaleClient()
_ws_clients: set[WebSocket] = set()


def _broadcast(payload: dict[str, Any]) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    async def _send_all() -> None:
        dead: list[WebSocket] = []
        for ws in list(_ws_clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            _ws_clients.discard(ws)

    loop.create_task(_send_all())


scanner.subscribe(_broadcast)
scale.subscribe(_broadcast)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    if scale.is_connected:
        await scale.disconnect()
    if scanner.is_scanning:
        await scanner.stop_scan()


app = FastAPI(
    title="BLE Scale Scanner",
    description="Quét thiết bị BLE trên Windows",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ScanStartBody(BaseModel):
    duration_sec: int = Field(default=SCAN_SECONDS, ge=1, le=120)


class GattProbeBody(BaseModel):
    address: str
    timeout: float = Field(default=12.0, ge=3.0, le=60.0)


class ScaleConnectBody(BaseModel):
    address: str
    timeout: float = Field(default=15.0, ge=5.0, le=60.0)
    profile: BleConnectProfile = Field(
        default="auto",
        description="auto | uni_compat | uuid",
    )


@app.get("/api/health")
async def health() -> dict:
    return {
        "ok": True,
        "scanning": scanner.is_scanning,
        "scale_connected": scale.is_connected,
        "scale_address": scale.address,
        "scale_profile": scale.profile_used,
    }


@app.get("/api/devices")
async def get_devices() -> dict:
    return {"scanning": scanner.is_scanning, "devices": scanner.list_devices()}


@app.post("/api/scan/start")
async def start_scan(body: ScanStartBody | None = None) -> dict:
    duration = body.duration_sec if body else SCAN_SECONDS
    return await scanner.start_scan(duration_sec=duration)


@app.post("/api/scan/stop")
async def stop_scan() -> dict:
    result = await scanner.stop_scan()
    result["devices"] = scanner.list_devices()
    return result


@app.post("/api/gatt/probe")
async def gatt_probe(body: GattProbeBody) -> dict:
    return await scanner.probe_gatt(body.address, timeout=body.timeout)


@app.get("/api/scale/status")
async def scale_status() -> dict:
    return {
        "connected": scale.is_connected,
        "address": scale.address,
        "profile_used": scale.profile_used,
        "last_reading": scale.last_reading,
    }


@app.get("/api/scale/gatt-map")
async def scale_gatt_map(
    address: str,
    timeout: float = 12.0,
) -> dict:
    return await fetch_gatt_map(address, timeout=timeout)


@app.post("/api/scale/connect")
async def scale_connect(body: ScaleConnectBody) -> dict:
    if scanner.is_scanning:
        await scanner.stop_scan()
    await asyncio.sleep(0.4)
    return await scale.connect(
        body.address,
        timeout=body.timeout,
        profile=body.profile,
    )


@app.post("/api/scale/disconnect")
async def scale_disconnect() -> dict:
    return await scale.disconnect()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    _ws_clients.add(websocket)
    try:
        await websocket.send_json(
            {
                "type": "status",
                "scanning": scanner.is_scanning,
                "devices": scanner.list_devices(),
                "scale_connected": scale.is_connected,
                "scale_address": scale.address,
                "scale_profile": scale.profile_used,
                "last_reading": scale.last_reading,
            }
        )
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)


_static = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _static.is_dir():
    app.mount("/", StaticFiles(directory=str(_static), html=True), name="static")
