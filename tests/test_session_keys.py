import unittest

from utils.session_keys import SessionKeys


class SessionKeysTest(unittest.TestCase):
    def test_static_auth_keys_match_expected_values(self):
        self.assertEqual(SessionKeys.ACCESS_TOKEN, "access_token")
        self.assertEqual(SessionKeys.REFRESH_TOKEN, "refresh_token")
        self.assertEqual(SessionKeys.USER_ID, "user_id")
        self.assertEqual(SessionKeys.CURRENT_MENU, "current_menu")

    def test_dynamic_electricity_keys_keep_backward_compatible_format(self):
        self.assertEqual(
            SessionKeys.taipower_amount(12, "2F"),
            "tp_12_2F_amt",
        )
        self.assertEqual(
            SessionKeys.taipower_kwh(12, "2F"),
            "tp_12_2F_kwh",
        )
        self.assertEqual(
            SessionKeys.taipower_db_loaded(12),
            "tp_12_db_loaded",
        )

    def test_dynamic_keys_for_delete_and_calculation(self):
        self.assertEqual(SessionKeys.confirm_delete("abc"), "confirm_delete_abc")
        self.assertEqual(SessionKeys.calc_result(9), "calc_result_9")
        self.assertEqual(SessionKeys.calc_details(9), "calc_details_9")
        self.assertEqual(SessionKeys.custom("memo"), "custom_memo")


if __name__ == "__main__":
    unittest.main()
