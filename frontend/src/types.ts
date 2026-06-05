export interface BleDevice {
  address: string;
  name: string;
  rssi: number | null;
  service_uuids: string[];
  manufacturer_data: Record<string, string>;
  first_seen: string;
  last_seen: string;
  seen_count: number;
  likely_scale: boolean;
}

export interface GattService {
  index?: number;
  uuid: string;
  uuid_short?: string;
  description: string;
  is_uni_target?: boolean;
  has_notify?: boolean;
  has_write?: boolean;
  characteristics: {
    uuid: string;
    uuid_short?: string;
    properties: string[];
  }[];
}

export type BleConnectProfile = "auto" | "uni_compat" | "uuid";
