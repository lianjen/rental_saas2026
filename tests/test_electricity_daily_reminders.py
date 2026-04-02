import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import services.base_db as base_db
from services.notification_service import NotificationService


def _candidate(
    *,
    reading_id: int = 101,
    period_id: int = 7,
    room_number: str = "3A",
    amount_due: int = 900,
    tenant_id: str = "tenant-1",
    tenant_name: str = "Kevin",
    line_user_id: str = "U123",
    remind_start_date: date = date(2026, 4, 1),
):
    return {
        "electricity_reading_id": reading_id,
        "period_id": period_id,
        "room_number": room_number,
        "amount_due": amount_due,
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "line_user_id": line_user_id,
        "period_year": 2026,
        "period_month_start": 3,
        "period_month_end": 4,
        "remind_start_date": remind_start_date,
    }


class TestElectricityDailyReminders(unittest.TestCase):
    def setUp(self):
        fake_cursor = MagicMock()
        fake_cursor.__enter__.return_value = fake_cursor
        fake_cursor.__exit__.return_value = None
        fake_cursor.fetchone.return_value = None
        fake_cursor.fetchall.return_value = []
        fake_cursor.rowcount = 0

        fake_conn = MagicMock()
        fake_conn.cursor.return_value = fake_cursor

        self.fake_pool = MagicMock()
        self.fake_pool.get_connection.return_value = fake_conn
        self.fake_pool.return_connection.return_value = None

        self.pool_patcher = patch.object(base_db, "get_connection_pool", return_value=self.fake_pool)
        self.pool_patcher.start()

    def tearDown(self):
        self.pool_patcher.stop()

    def test_send_daily_electricity_reminder_once(self):
        service = NotificationService()
        run_date = date(2026, 4, 2)

        with (
            patch.object(
                service,
                "_get_daily_electricity_reminder_candidates",
                return_value=[_candidate()],
            ),
            patch.object(
                service,
                "_has_sent_electricity_daily_reminder_today",
                return_value=False,
            ),
            patch.object(service, "send_line_message", return_value=True) as send_mock,
            patch.object(service, "_write_notification_log") as log_mock,
            patch.object(service, "_update_electricity_last_notified") as update_mock,
        ):
            ok, _msg, summary = service.run_daily_electricity_reminders(run_date)

        self.assertTrue(ok)
        self.assertEqual(summary["checked"], 1)
        self.assertEqual(summary["sent"], 1)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(summary["failed"], 0)
        send_mock.assert_called_once()
        log_mock.assert_called_once()
        update_mock.assert_called_once_with(101)
        self.assertEqual(log_mock.call_args.args[4], "daily_reminder")

    def test_skip_when_already_sent_today(self):
        service = NotificationService()
        run_date = date(2026, 4, 2)

        with (
            patch.object(
                service,
                "_get_daily_electricity_reminder_candidates",
                return_value=[_candidate()],
            ),
            patch.object(
                service,
                "_has_sent_electricity_daily_reminder_today",
                return_value=True,
            ),
            patch.object(service, "send_line_message") as send_mock,
            patch.object(service, "_write_notification_log") as log_mock,
            patch.object(service, "_update_electricity_last_notified") as update_mock,
        ):
            ok, _msg, summary = service.run_daily_electricity_reminders(run_date)

        self.assertTrue(ok)
        self.assertEqual(summary["checked"], 1)
        self.assertEqual(summary["sent"], 0)
        self.assertEqual(summary["skipped"], 1)
        self.assertEqual(summary["failed"], 0)
        send_mock.assert_not_called()
        log_mock.assert_not_called()
        update_mock.assert_not_called()

    def test_count_failed_delivery(self):
        service = NotificationService()
        run_date = date(2026, 4, 2)

        with (
            patch.object(
                service,
                "_get_daily_electricity_reminder_candidates",
                return_value=[_candidate()],
            ),
            patch.object(
                service,
                "_has_sent_electricity_daily_reminder_today",
                return_value=False,
            ),
            patch.object(service, "send_line_message", return_value=False),
            patch.object(service, "_write_notification_log") as log_mock,
            patch.object(service, "_update_electricity_last_notified") as update_mock,
        ):
            ok, _msg, summary = service.run_daily_electricity_reminders(run_date)

        self.assertTrue(ok)
        self.assertEqual(summary["checked"], 1)
        self.assertEqual(summary["sent"], 0)
        self.assertEqual(summary["skipped"], 0)
        self.assertEqual(summary["failed"], 1)
        log_mock.assert_called_once()
        update_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
