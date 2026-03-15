"""
Electricity calculator tests - v1.0.1
Validate pure billing logic in services.electricity_calculator.
"""

import unittest

from services.electricity_calculator import ElectricityCalculator


EXCLUSIVE_ROOMS = ["1A", "1B"]
SHARING_ROOMS = ["2A", "2B", "3A", "3B", "3C", "3D", "4A", "4B", "4C", "4D"]
FLOOR_MAP = {
    "2A": "2F",
    "2B": "2F",
    "3A": "3F",
    "3B": "3F",
    "3C": "3F",
    "3D": "3F",
    "4A": "4F",
    "4B": "4F",
    "4C": "4F",
    "4D": "4F",
}


def _get_detail(result: dict, room_number: str) -> dict:
    return next(detail for detail in result["details"] if detail["room_number"] == room_number)


def _calculate(bills: list[dict], readings: dict[str, float]) -> dict:
    return ElectricityCalculator.calculate_all(
        taipower_bills=bills,
        room_readings=readings,
        exclusive_rooms=EXCLUSIVE_ROOMS,
        sharing_rooms=SHARING_ROOMS,
        floor_room_mapping=FLOOR_MAP,
    )


class TestFloor1Calculation(unittest.TestCase):
    def test_1f_basic_calculation(self):
        bills = [{"floor_label": "1F", "amount": 1300, "kwh": 130}]
        readings = {"1A": 50, "1B": 80}

        result = _calculate(bills, readings)

        self.assertEqual(result["taipower_amount"], 1300)
        self.assertAlmostEqual(result["shared_per_room_1f_exact"], 0.0)
        self.assertEqual(_get_detail(result, "1A")["amount_due"], 500)
        self.assertEqual(_get_detail(result, "1B")["amount_due"], 800)

    def test_1f_shared_electricity_split(self):
        bills = [{"floor_label": "1F", "amount": 1000, "kwh": 100}]
        readings = {"1A": 30, "1B": 50}

        result = _calculate(bills, readings)

        self.assertAlmostEqual(result["public_kwh_1f"], 20.0)
        self.assertAlmostEqual(result["shared_per_room_1f_exact"], 10.0)
        self.assertEqual(_get_detail(result, "1A")["amount_due"], 400)
        self.assertEqual(_get_detail(result, "1B")["amount_due"], 600)

    def test_1f_precision_no_rounding_error(self):
        bills = [{"floor_label": "1F", "amount": 1000, "kwh": 111}]
        readings = {"1A": 30, "1B": 70}

        result = _calculate(bills, readings)
        room_1a = _get_detail(result, "1A")

        self.assertAlmostEqual(result["shared_per_room_1f_exact"], 5.5)
        self.assertEqual(room_1a["amount_due"], round((30 + 5.5) * (1000 / 111)))

    def test_1f_empty_room_no_reading(self):
        bills = [{"floor_label": "1F", "amount": 120, "kwh": 12}]
        readings = {"1A": 10, "1B": 0}

        result = _calculate(bills, readings)
        room_1b = _get_detail(result, "1B")

        self.assertEqual(room_1b["used_kwh"], 0)
        self.assertEqual(room_1b["amount_due"], 10)


class TestFloor234Calculation(unittest.TestCase):
    def test_234f_combined_calculation(self):
        bills = [
            {"floor_label": "2F", "amount": 100, "kwh": 10},
            {"floor_label": "3F", "amount": 200, "kwh": 20},
            {"floor_label": "4F", "amount": 300, "kwh": 30},
        ]
        readings = {room: 5 for room in SHARING_ROOMS}

        result = _calculate(bills, readings)

        self.assertEqual(result["merged_amount"], 600)
        self.assertAlmostEqual(result["merged_kwh"], 60.0)
        self.assertAlmostEqual(result["shared_per_room_exact"], 1.0)
        self.assertEqual(result["total_charge"], 600)

    def test_234f_public_electricity_distribution(self):
        bills = [
            {"floor_label": "2F", "amount": 200, "kwh": 20},
            {"floor_label": "3F", "amount": 200, "kwh": 20},
            {"floor_label": "4F", "amount": 200, "kwh": 20},
        ]
        readings = {room: 3 for room in SHARING_ROOMS}

        result = _calculate(bills, readings)
        room_2a = _get_detail(result, "2A")

        self.assertAlmostEqual(result["total_public_kwh"], 30.0)
        self.assertAlmostEqual(result["shared_per_room_exact"], 3.0)
        self.assertEqual(room_2a["amount_due"], 60)

    def test_234f_precision_boundary(self):
        bills = [
            {"floor_label": "2F", "amount": 400, "kwh": 40},
            {"floor_label": "3F", "amount": 430, "kwh": 43},
            {"floor_label": "4F", "amount": 500, "kwh": 50},
        ]
        readings = {
            "2A": 10,
            "2B": 10,
            "3A": 10,
            "3B": 10,
            "3C": 10,
            "3D": 10,
            "4A": 10,
            "4B": 10,
            "4C": 10,
            "4D": 10,
        }

        result = _calculate(bills, readings)
        room_2a = _get_detail(result, "2A")

        self.assertAlmostEqual(result["total_public_kwh"], 33.0)
        self.assertAlmostEqual(result["shared_per_room_exact"], 3.3)
        self.assertEqual(room_2a["amount_due"], 133)

    def test_234f_one_empty_room(self):
        bills = [
            {"floor_label": "2F", "amount": 300, "kwh": 30},
            {"floor_label": "3F", "amount": 300, "kwh": 30},
            {"floor_label": "4F", "amount": 400, "kwh": 40},
        ]
        readings = {room: 10 for room in SHARING_ROOMS}
        readings["4D"] = 0

        result = _calculate(bills, readings)
        room_4d = _get_detail(result, "4D")

        self.assertAlmostEqual(result["total_public_kwh"], 10.0)
        self.assertAlmostEqual(result["shared_per_room_exact"], 1.0)
        self.assertEqual(room_4d["amount_due"], 10)


class TestEdgeCases(unittest.TestCase):
    def test_zero_usage_room(self):
        bills = [
            {"floor_label": "2F", "amount": 300, "kwh": 30},
            {"floor_label": "3F", "amount": 300, "kwh": 30},
            {"floor_label": "4F", "amount": 400, "kwh": 40},
        ]
        readings = {room: 9 for room in SHARING_ROOMS}
        readings["2A"] = 0

        result = _calculate(bills, readings)
        room_2a = _get_detail(result, "2A")

        self.assertEqual(room_2a["used_kwh"], 0)
        self.assertAlmostEqual(room_2a["shared_kwh"], 1.9)
        self.assertEqual(room_2a["amount_due"], 19)

    def test_taipower_bill_zero(self):
        bills = [
            {"floor_label": "2F", "amount": 0, "kwh": 0},
            {"floor_label": "3F", "amount": 0, "kwh": 0},
            {"floor_label": "4F", "amount": 0, "kwh": 0},
        ]
        readings = {room: 5 for room in SHARING_ROOMS}

        result = _calculate(bills, readings)

        self.assertAlmostEqual(result["merged_unit_price_exact"], 0.0)
        self.assertTrue(all(detail["amount_due"] == 0 for detail in result["details"]))

    def test_all_rooms_total_matches_taipower(self):
        bills = [
            {"floor_label": "1F", "amount": 1110, "kwh": 111},
            {"floor_label": "2F", "amount": 300, "kwh": 30},
            {"floor_label": "3F", "amount": 300, "kwh": 30},
            {"floor_label": "4F", "amount": 400, "kwh": 40},
        ]
        readings = {
            "1A": 30,
            "1B": 70,
            "2A": 8,
            "2B": 9,
            "3A": 10,
            "3B": 7,
            "3C": 10,
            "3D": 8,
            "4A": 10,
            "4B": 9,
            "4C": 10,
            "4D": 9,
        }

        result = _calculate(bills, readings)

        self.assertLessEqual(abs(result["total_charge"] - result["taipower_amount"]), 1)


if __name__ == "__main__":
    unittest.main()
