"""
Electricity daily reminder runner - v1.0.0

Run this script from cron / Windows Task Scheduler once per day to send
electricity overdue reminders for periods whose remind_start_date has arrived.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from services.logger import logger  # noqa: E402
from services.notification_service import NotificationService  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send daily electricity reminders after remind_start_date.",
    )
    parser.add_argument(
        "--date",
        dest="run_date",
        help="Override run date in YYYY-MM-DD format for testing.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    run_date = date.fromisoformat(args.run_date) if args.run_date else date.today()

    service = NotificationService()
    ok, message, summary = service.run_daily_electricity_reminders(run_date=run_date)

    if ok:
        logger.info("[LINE] %s", message)
        print(message)
        print(summary)
        return 0

    logger.error("[LINE] Electricity daily reminder runner failed: %s", message)
    print(message)
    print(summary)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
