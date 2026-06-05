"""Tests parser UNI (parseHexToType)."""

import unittest
from unittest import mock

from app.weight_parser import (
    bytes_to_hex_string,
    parse_notify_payload,
    parse_uni_compat_packet,
    parse_uni_hex_string,
)


class TestUniParser(unittest.TestCase):
    def test_weight_type_40(self):
        # byte1=0x40, value bytes 2-5 = 0x00001388 (5000) -> 10*5000/1000 = 50 kg
        data = bytes([0x00, 0x40, 0x00, 0x00, 0x13, 0x88, 0x00])
        hex_str = bytes_to_hex_string(data)
        self.assertEqual(len(hex_str), 14)
        result = parse_uni_hex_string(hex_str)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["kg"], 50.0)
        self.assertEqual(result["source"], "uni_js_weight")

    def test_weight_type_50_negative(self):
        data = bytes([0x00, 0x50, 0x00, 0x00, 0x00, 0x64, 0x00])  # 100 -> 1.0 kg neg
        result = parse_uni_compat_packet(data)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["kg"], -1.0)

    def test_type_00_invalid(self):
        data = bytes([0x00, 0x00, 0x00, 0x00, 0x00, 0x64, 0x00])
        self.assertIsNone(parse_uni_compat_packet(data))

    def test_voltage_c400(self):
        hex_str = "00XXC40001F4YY".replace("X", "0").replace("Y", "0")
        # C400 at 4-8, tail 01F4 = 500 -> 5.00 V
        hex_str = "0001c40001f400"
        result = parse_uni_hex_string(hex_str)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.get("voltage_v"), 5.0)

    def test_profile_uni_compat_priority(self):
        data = bytes([0x00, 0x40, 0x00, 0x00, 0x00, 0x64, 0x00])  # 1.0 kg
        result = parse_notify_payload(
            data,
            "0000fff4-0000-1000-8000-00805f9b34fb",
            profile="uni_compat",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["kg"], 1.0)
        self.assertEqual(result["source"], "uni_js_weight")

    def test_uuid_profile_not_ffe_salter(self):
        """ffe_salter từng đọc 1.0 kg thành 25.6 kg trên ffe1 + profile uuid."""
        data = bytes([0x00, 0x40, 0x00, 0x00, 0x00, 0x64, 0x00])
        ffe1 = "0000ffe1-0000-1000-8000-00805f9b34fb"
        result = parse_notify_payload(data, ffe1, profile="uuid")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["kg"], 1.0)
        self.assertEqual(result["source"], "uni_js_weight")

    def test_70kg_frame(self):
        # raw=7000 (0x1B58) -> kg = 10*7000/1000 = 70
        data = bytes([0x00, 0x40, 0x00, 0x00, 0x1B, 0x58, 0x00])
        result = parse_notify_payload(
            data,
            "0000ffe1-0000-1000-8000-00805f9b34fb",
            profile="uuid",
        )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["kg"], 70.0)

    @mock.patch("app.weight_parser.WEIGHT_PARSER", "uni_js_only")
    def test_uni_js_only_skips_ffe_salter(self):
        """uni_js_only: không fallback ffe_salter dù frame không giống UNI."""
        data = bytes([0x10, 0x00, 0x00, 0x00, 0x64, 0x00, 0x01])
        result = parse_notify_payload(
            data,
            "0000ffe1-0000-1000-8000-00805f9b34fb",
            profile="uuid",
        )
        self.assertIsNone(result)

    @mock.patch("app.weight_parser.WEIGHT_PARSER", "uni_js_only")
    def test_uni_js_only_default_weight(self):
        data = bytes([0x00, 0x40, 0x00, 0x00, 0x00, 0x64, 0x00])
        result = parse_notify_payload(data, "0000ffe1-0000-1000-8000-00805f9b34fb")
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["source"], "uni_js_weight")


if __name__ == "__main__":
    unittest.main()
