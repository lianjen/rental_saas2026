"""
electricity_calculator.py - v1.0.0
Pure electricity billing logic with no database dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence


@dataclass(frozen=True)
class RoomCharge:
    floor: str
    room_number: str
    room_type: str
    used_kwh: float
    shared_kwh: float
    total_kwh: float
    unit_price: float
    unit_price_exact: float
    amount_due: int

    def as_dict(self) -> Dict:
        return {
            "floor": self.floor,
            "room_number": self.room_number,
            "room_type": self.room_type,
            "used_kwh": self.used_kwh,
            "shared_kwh": self.shared_kwh,
            "total_kwh": self.total_kwh,
            "unit_price": self.unit_price,
            "unit_price_exact": self.unit_price_exact,
            "amount_due": self.amount_due,
        }


class ElectricityCalculator:
    """Static helpers for 1F and 2-4F electricity calculations."""

    @staticmethod
    def calculate_unit_price(taipower_amount: float, total_kwh: float) -> float:
        if total_kwh <= 0:
            return 0.0
        return float(taipower_amount) / float(total_kwh)

    @staticmethod
    def calculate_shared_per_room(public_kwh: float, room_count: int) -> float:
        if room_count <= 0:
            return 0.0
        return float(public_kwh) / float(room_count)

    @staticmethod
    def calculate_room_amount(room_kwh: float, shared_kwh: float, unit_price: float) -> int:
        return round((float(room_kwh) + float(shared_kwh)) * float(unit_price))

    @staticmethod
    def _round_kwh(value: float) -> float:
        return round(float(value), 2)

    @classmethod
    def calculate_floor1(
        cls,
        taipower_bill: Optional[Dict],
        readings: List[Dict],
        exclusive_rooms: Sequence[str],
    ) -> Dict:
        if not taipower_bill:
            return {
                "details": [],
                "public_kwh": 0.0,
                "shared_per_room_exact": 0.0,
                "unit_price_exact": 0.0,
                "unit_price": 0.0,
                "bill_amount": 0,
                "bill_kwh": 0.0,
                "total_charge": 0,
            }

        bill_amount = int(taipower_bill.get("amount", 0) or 0)
        bill_kwh = float(taipower_bill.get("kwh", 0) or 0)
        unit_price_exact = cls.calculate_unit_price(bill_amount, bill_kwh)
        unit_price = round(unit_price_exact, 2)

        reading_map = {
            room: float(next((row.get("kwh", 0) for row in readings if row["room_number"] == room), 0) or 0)
            for room in exclusive_rooms
        }

        public_kwh = max(0.0, bill_kwh - sum(reading_map.values()))
        shared_per_room_exact = cls.calculate_shared_per_room(public_kwh, len(exclusive_rooms))

        details = []
        bill_exists = bill_amount > 0 or bill_kwh > 0
        for room in exclusive_rooms:
            used_kwh = reading_map.get(room, 0.0)
            if not bill_exists and used_kwh <= 0:
                continue

            total_kwh = used_kwh + shared_per_room_exact
            details.append(
                RoomCharge(
                    floor="1F",
                    room_number=room,
                    room_type="exclusive",
                    used_kwh=cls._round_kwh(used_kwh),
                    shared_kwh=shared_per_room_exact,
                    total_kwh=cls._round_kwh(total_kwh),
                    unit_price=unit_price,
                    unit_price_exact=unit_price_exact,
                    amount_due=cls.calculate_room_amount(used_kwh, shared_per_room_exact, unit_price_exact),
                ).as_dict()
            )

        return {
            "details": details,
            "public_kwh": public_kwh,
            "shared_per_room_exact": shared_per_room_exact,
            "unit_price_exact": unit_price_exact,
            "unit_price": unit_price,
            "bill_amount": bill_amount,
            "bill_kwh": bill_kwh,
            "total_charge": sum(item["amount_due"] for item in details),
        }

    @classmethod
    def calculate_floor234(
        cls,
        taipower_bills: List[Dict],
        readings: List[Dict],
        sharing_rooms: Sequence[str],
        floor_room_mapping: Dict[str, str],
    ) -> Dict:
        merged_amount = sum(int(bill.get("amount", 0) or 0) for bill in taipower_bills)
        merged_kwh = sum(float(bill.get("kwh", 0) or 0) for bill in taipower_bills)
        unit_price_exact = cls.calculate_unit_price(merged_amount, merged_kwh)
        unit_price = round(unit_price_exact, 2)

        reading_map = {
            room: float(next((row.get("kwh", 0) for row in readings if row["room_number"] == room), 0) or 0)
            for room in sharing_rooms
        }

        public_kwh = max(0.0, merged_kwh - sum(reading_map.values()))
        shared_per_room_exact = cls.calculate_shared_per_room(public_kwh, len(sharing_rooms))

        details = []
        bill_exists = merged_amount > 0 or merged_kwh > 0
        for room in sharing_rooms:
            used_kwh = reading_map.get(room, 0.0)
            if not bill_exists and used_kwh <= 0:
                continue

            total_kwh = used_kwh + shared_per_room_exact
            details.append(
                RoomCharge(
                    floor=floor_room_mapping.get(room, ""),
                    room_number=room,
                    room_type="sharing",
                    used_kwh=cls._round_kwh(used_kwh),
                    shared_kwh=shared_per_room_exact,
                    total_kwh=cls._round_kwh(total_kwh),
                    unit_price=unit_price,
                    unit_price_exact=unit_price_exact,
                    amount_due=cls.calculate_room_amount(used_kwh, shared_per_room_exact, unit_price_exact),
                ).as_dict()
            )

        floor_summaries = []
        for bill in taipower_bills:
            floor = bill["floor_label"]
            floor_rooms = [room for room, room_floor in floor_room_mapping.items() if room_floor == floor]
            floor_details = [detail for detail in details if detail["room_number"] in floor_rooms]
            if not floor_details:
                continue

            room_kwh = sum(detail["used_kwh"] for detail in floor_details)
            floor_summaries.append(
                {
                    "floor": floor,
                    "bill_amount": int(bill.get("amount", 0) or 0),
                    "bill_kwh": float(bill.get("kwh", 0) or 0),
                    "room_kwh": cls._round_kwh(room_kwh),
                    "public_kwh": cls._round_kwh(max(0.0, float(bill.get("kwh", 0) or 0) - room_kwh)),
                    "unit_price": unit_price,
                    "total_charge": sum(detail["amount_due"] for detail in floor_details),
                }
            )

        return {
            "details": details,
            "floor_summaries": floor_summaries,
            "public_kwh": public_kwh,
            "shared_per_room_exact": shared_per_room_exact,
            "unit_price_exact": unit_price_exact,
            "unit_price": unit_price,
            "merged_amount": merged_amount,
            "merged_kwh": merged_kwh,
            "total_charge": sum(item["amount_due"] for item in details),
        }

    @classmethod
    def calculate_all(
        cls,
        taipower_bills: List[Dict],
        room_readings: Dict[str, float],
        exclusive_rooms: Sequence[str],
        sharing_rooms: Sequence[str],
        floor_room_mapping: Dict[str, str],
    ) -> Dict:
        floor_1f = next((bill for bill in taipower_bills if bill["floor_label"] == "1F"), None)
        floors_234 = [bill for bill in taipower_bills if bill["floor_label"] != "1F"]

        reading_rows = [
            {"room_number": room, "kwh": float(kwh or 0)}
            for room, kwh in room_readings.items()
        ]

        floor1 = cls.calculate_floor1(
            taipower_bill=floor_1f,
            readings=reading_rows,
            exclusive_rooms=exclusive_rooms,
        )
        floor234 = cls.calculate_floor234(
            taipower_bills=floors_234,
            readings=reading_rows,
            sharing_rooms=sharing_rooms,
            floor_room_mapping=floor_room_mapping,
        )

        floor_summaries = list(floor234["floor_summaries"])
        if floor1["details"]:
            floor_summaries.insert(
                0,
                {
                    "floor": "1F",
                    "bill_amount": floor1["bill_amount"],
                    "bill_kwh": floor1["bill_kwh"],
                    "room_kwh": cls._round_kwh(sum(item["used_kwh"] for item in floor1["details"])),
                    "public_kwh": cls._round_kwh(floor1["public_kwh"]),
                    "unit_price": floor1["unit_price"],
                    "total_charge": floor1["total_charge"],
                },
            )

        total_charge = floor1["total_charge"] + floor234["total_charge"]
        total_taipower = sum(int(bill.get("amount", 0) or 0) for bill in taipower_bills)

        return {
            "total_charge": total_charge,
            "taipower_amount": total_taipower,
            "difference": total_charge - total_taipower,
            "details": floor1["details"] + floor234["details"],
            "floor_summaries": floor_summaries,
            "merged_unit_price": floor234["unit_price"],
            "merged_unit_price_exact": floor234["unit_price_exact"],
            "total_public_kwh": floor234["public_kwh"],
            "shared_per_room": round(floor234["shared_per_room_exact"], 1),
            "shared_per_room_exact": floor234["shared_per_room_exact"],
            "merged_kwh": floor234["merged_kwh"],
            "merged_amount": floor234["merged_amount"],
            "public_kwh_1f": floor1["public_kwh"],
            "shared_per_room_1f": round(floor1["shared_per_room_exact"], 1),
            "shared_per_room_1f_exact": floor1["shared_per_room_exact"],
        }
