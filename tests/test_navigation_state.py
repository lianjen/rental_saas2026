import unittest

from utils import navigation_state


class FakeStreamlit:
    def __init__(self):
        self.session_state = {}


class NavigationStateTest(unittest.TestCase):
    def test_build_navigation_state_ignores_none_values(self):
        state = navigation_state.build_navigation_state(
            navigation_state.MENU_RENT,
            rent_default_tab=navigation_state.RENT_TAB_MANAGEMENT,
            current_period_id=None,
        )

        self.assertEqual(state["current_menu"], navigation_state.MENU_RENT)
        self.assertEqual(
            state["rent_default_tab"],
            navigation_state.RENT_TAB_MANAGEMENT,
        )
        self.assertNotIn("current_period_id", state)

    def test_apply_navigation_state_updates_and_clears_keys(self):
        original_streamlit = navigation_state.st
        fake_streamlit = FakeStreamlit()
        fake_streamlit.session_state["stale_key"] = "old"
        navigation_state.st = fake_streamlit

        try:
            state = navigation_state.apply_navigation_state(
                navigation_state.MENU_ELECTRICITY,
                clear_keys=["stale_key"],
                electricity_default_tab=navigation_state.ELECTRICITY_TAB_CALCULATION,
                current_period_id=9,
            )
        finally:
            navigation_state.st = original_streamlit

        self.assertNotIn("stale_key", fake_streamlit.session_state)
        self.assertEqual(
            fake_streamlit.session_state["current_menu"],
            navigation_state.MENU_ELECTRICITY,
        )
        self.assertEqual(fake_streamlit.session_state["current_period_id"], 9)
        self.assertEqual(state["current_menu"], navigation_state.MENU_ELECTRICITY)

    def test_resolve_default_label_falls_back_safely(self):
        options = ["A", "B", "C"]

        self.assertEqual(
            navigation_state.resolve_default_label(options, "B", "A"),
            "B",
        )
        self.assertEqual(
            navigation_state.resolve_default_label(options, "X", "A"),
            "A",
        )
        self.assertEqual(
            navigation_state.resolve_default_label(options, "X", None),
            "A",
        )

    def test_pending_electricity_period_summary_returns_latest_pending(self):
        periods = [
            {"id": 1, "period_year": 2025, "period_month_start": 11, "period_month_end": 12},
            {"id": 2, "period_year": 2026, "period_month_start": 1, "period_month_end": 2},
            {"id": 3, "period_year": 2026, "period_month_start": 3, "period_month_end": 4},
        ]
        existing_records = {1, 3}

        summary = navigation_state.get_pending_electricity_period_summary(
            periods,
            lambda period_id: period_id in existing_records,
        )

        self.assertEqual(summary["pending_count"], 1)
        self.assertEqual(summary["default_period_id"], 2)
