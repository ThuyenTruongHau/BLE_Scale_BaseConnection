import { useCallback, useMemo, useState } from "react";
import type { BleConnectProfile, BleDevice, GattService } from "./types";
import {
  useBleWebSocket,
  type BleWsPayload,
  type WeightReading,
} from "./useBleWebSocket";

export default function App() {
  const [devices, setDevices] = useState<BleDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [seconds, setSeconds] = useState(15);
  const [message, setMessage] = useState("");
  const [gattResult, setGattResult] = useState<string | null>(null);
  const [probing, setProbing] = useState<string | null>(null);
  const [scaleConnected, setScaleConnected] = useState(false);
  const [scaleAddress, setScaleAddress] = useState<string | null>(null);
  const [connecting, setConnecting] = useState<string | null>(null);
  const [lastWeight, setLastWeight] = useState<WeightReading | null>(null);
  const [connectProfile, setConnectProfile] =
    useState<BleConnectProfile>("auto");
  const [scaleProfile, setScaleProfile] = useState<string | null>(null);

  const mergeDevice = useCallback((device: BleDevice) => {
    setDevices((prev) => {
      const rest = prev.filter((d) => d.address !== device.address);
      return [...rest, device].sort((a, b) => {
        if (a.likely_scale !== b.likely_scale) return a.likely_scale ? -1 : 1;
        return (b.rssi ?? -999) - (a.rssi ?? -999);
      });
    });
  }, []);

  const onWsMessage = useCallback(
    (data: BleWsPayload) => {
      if (data.type === "device" && data.device) {
        mergeDevice(data.device);
      }
      if (data.type === "status") {
        if (typeof data.scanning === "boolean") setScanning(data.scanning);
        if (Array.isArray(data.devices)) setDevices(data.devices);
        if (typeof data.scale_connected === "boolean") {
          setScaleConnected(data.scale_connected);
        }
        if (data.scale_address !== undefined) {
          setScaleAddress(data.scale_address ?? null);
        }
        if (data.last_reading !== undefined) {
          setLastWeight(data.last_reading ?? null);
        }
      }
      if (data.type === "weight") {
        setLastWeight({
          address: data.address,
          kg: data.kg ?? null,
          stable: data.stable,
          source: data.source,
          raw_hex: data.raw_hex,
          char_uuid: data.char_uuid,
        });
      }
      if (data.type === "scale_disconnected") {
        setScaleConnected(false);
        setScaleAddress(null);
      }
    },
    [mergeDevice]
  );

  const onWsConnectionChange = useCallback((connected: boolean) => {
    setMessage((prev) => {
      if (connected) return prev.startsWith("WebSocket") ? "" : prev;
      return "WebSocket lỗi — backend đã chạy chưa? (python main.py)";
    });
  }, []);

  useBleWebSocket(onWsMessage, onWsConnectionChange);

  const likelyCount = useMemo(
    () => devices.filter((d) => d.likely_scale).length,
    [devices]
  );

  async function startScan() {
    setMessage("");
    setGattResult(null);
    try {
      const res = await fetch("/api/scan/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_sec: seconds }),
      });
      const data = await res.json();
      setMessage(
        data.message ||
          (res.ok ? "" : `Lỗi server (${res.status}) — xem log backend.`)
      );
      if (data.ok) {
        setScanning(true);
        setDevices([]);
      } else {
        setScanning(false);
      }
    } catch {
      setMessage("Không gọi được API — backend đã chạy chưa?");
      setScanning(false);
    }
  }

  async function stopScan() {
    const res = await fetch("/api/scan/stop", { method: "POST" });
    const data = await res.json();
    setScanning(false);
    setMessage(data.message || "");
    if (data.devices) setDevices(data.devices);
  }

  async function connectScale(address: string) {
    setConnecting(address);
    setMessage("");
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 45000);
    try {
      const res = await fetch("/api/scale/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          address,
          timeout: 20,
          profile: connectProfile,
        }),
        signal: controller.signal,
      });
      const data = await res.json();
      setMessage(data.message || "");
      if (data.ok) {
        setScaleConnected(true);
        setScaleAddress(address);
        setScaleProfile(data.profile_used ?? connectProfile);
        setScanning(false);
      }
    } catch (err) {
      const aborted = err instanceof DOMException && err.name === "AbortError";
      setMessage(
        aborted
          ? "Kết nối quá lâu — bật cân gần PC, dừng quét, thử lại."
          : "Không gọi được API — backend đã chạy chưa?"
      );
    } finally {
      window.clearTimeout(timer);
      setConnecting(null);
    }
  }

  async function disconnectScale() {
    try {
      const res = await fetch("/api/scale/disconnect", { method: "POST" });
      const data = await res.json();
      setMessage(data.message || "");
      setScaleConnected(false);
      setScaleAddress(null);
    } catch {
      setMessage("Không ngắt kết nối được.");
    }
  }

  async function probeGatt(address: string) {
    setProbing(address);
    setGattResult(null);
    try {
      const res = await fetch("/api/gatt/probe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address }),
      });
      const data = await res.json();
      if (!data.ok) {
        setGattResult(`Lỗi ${address}: ${data.message}`);
        return;
      }
      const services = (data.services as GattService[]) || [];
      const lines: string[] = [];
      if (data.uni_target_ready === false && data.uni_target) {
        lines.push(
          "  ⚠ service[3] thiếu notify hoặc write — profile uni_compat có thể lỗi."
        );
      }
      for (const s of services) {
        const tag = s.is_uni_target ? " [UNI index 3]" : "";
        const caps = [
          s.has_notify ? "notify" : "",
          s.has_write ? "write" : "",
        ]
          .filter(Boolean)
          .join(",");
        lines.push(
          `  [${s.index ?? "?"}] ${s.uuid_short || s.uuid}${tag}${
            s.description ? ` (${s.description})` : ""
          }${caps ? ` {${caps}}` : ""}`
        );
        for (const c of s.characteristics || []) {
          lines.push(
            `    └ ${c.uuid_short || c.uuid} [${(c.properties || []).join(", ")}]`
          );
        }
      }
      const hasFfe0 = data.has_ffe0 ?? services.some((s) =>
        (s.uuid_short || s.uuid).toLowerCase().includes("ffe0")
      );
      const hint = hasFfe0
        ? "\n→ Có FFE0. Thử profile auto/uni_compat hoặc uuid."
        : "\n→ So index 3 với app UNI (services[3]).";
      setGattResult(
        `GATT ${address} (${data.service_count ?? services.length} services):\n${
          lines.join("\n") || "  (không có service)"
        }${hint}`
      );
    } finally {
      setProbing(null);
    }
  }

  return (
    <div className="page">
      <header>
        <h1>BLE Scale Scanner</h1>
        <p className="hint">
          Quét BLE (không ghép đôi Bluetooth Classic). Bật cân, đặt gần PC 1–2 m.
        </p>
      </header>

      <section className="toolbar">
        <label>
          Thời gian (giây)
          <input
            type="number"
            min={5}
            max={120}
            value={seconds}
            disabled={scanning}
            onChange={(e) => setSeconds(Number(e.target.value))}
          />
        </label>
        <button type="button" disabled={scanning} onClick={startScan}>
          Bắt đầu quét
        </button>
        <button type="button" disabled={!scanning} onClick={stopScan}>
          Dừng
        </button>
        <label>
          Profile kết nối
          <select
            value={connectProfile}
            disabled={scaleConnected || !!connecting}
            onChange={(e) =>
              setConnectProfile(e.target.value as BleConnectProfile)
            }
          >
            <option value="auto">auto (ưu tiên UNI)</option>
            <option value="uni_compat">uni_compat (service[3])</option>
            <option value="uuid">uuid (FFE0/FFF0)</option>
          </select>
        </label>
        {scanning && <span className="badge scanning">Đang quét…</span>}
      </section>

      {message && <p className="message">{message}</p>}

      <section className="stats">
        <span>Tổng: {devices.length}</span>
        <span>Gợi ý cân: {likelyCount}</span>
        {scaleConnected && (
          <span className="badge scanning">
            Đã kết nối: {scaleAddress}
            {scaleProfile ? ` (${scaleProfile})` : ""}
          </span>
        )}
      </section>

      {lastWeight && (
        <section className="weight-live">
          {lastWeight.kg != null ? (
            <p>
              Cân: <strong>{lastWeight.kg} kg</strong>
              {lastWeight.stable ? " (ổn định)" : " (đang đo)"}
              {lastWeight.source ? ` — ${lastWeight.source}` : ""}
            </p>
          ) : (
            <p>
              Chưa parse được kg — có gói BLE (xem gói thô bên dưới).
            </p>
          )}
          {lastWeight.raw_hex && (
            <p className="hint mono">
              Gói thô: {lastWeight.raw_hex}
              {lastWeight.char_uuid ? ` @ ${lastWeight.char_uuid}` : ""}
            </p>
          )}
        </section>
      )}

      {scaleConnected && (
        <button type="button" onClick={disconnectScale}>
          Ngắt kết nối cân
        </button>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Tên</th>
              <th>MAC</th>
              <th>RSSI</th>
              <th>Service UUID</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {devices.length === 0 ? (
              <tr>
                <td colSpan={5} className="empty">
                  Chưa có thiết bị — nhấn Bắt đầu quét
                </td>
              </tr>
            ) : (
              devices.map((d) => (
                <tr
                  key={d.address}
                  className={d.likely_scale ? "likely" : undefined}
                >
                  <td>
                    {d.name}
                    {d.likely_scale && (
                      <span className="tag">Gợi ý cân</span>
                    )}
                  </td>
                  <td className="mono">{d.address}</td>
                  <td>{d.rssi ?? "—"}</td>
                  <td className="uuids">
                    {d.service_uuids.length
                      ? d.service_uuids.join(", ")
                      : "—"}
                  </td>
                  <td className="actions">
                    <button
                      type="button"
                      className="small"
                      disabled={
                        scanning ||
                        scaleConnected ||
                        connecting === d.address
                      }
                      onClick={() => connectScale(d.address)}
                    >
                      {connecting === d.address ? "…" : "Kết nối"}
                    </button>
                    <button
                      type="button"
                      className="small secondary"
                      disabled={scanning || probing === d.address}
                      onClick={() => probeGatt(d.address)}
                    >
                      {probing === d.address ? "…" : "GATT"}
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {gattResult && (
        <pre className="gatt">{gattResult}</pre>
      )}

      <footer>
        <strong>Xác nhận đúng cân:</strong> quét khi cân bật → ghi MAC → tắt cân →
        quét lại; MAC biến mất thì khả năng cao là cân.
      </footer>
    </div>
  );
}
