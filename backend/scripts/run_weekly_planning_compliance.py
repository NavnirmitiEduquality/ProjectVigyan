from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.planning_notification_service import (
    PlanningNotificationService,
)


TIMEZONE = ZoneInfo("Asia/Kolkata")

# Stable PostgreSQL advisory-lock key reserved for this job.
ADVISORY_LOCK_KEY = 7310420261117

logger = logging.getLogger("weekly_planning_compliance")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate weekly Para Teacher planning compliance notifications."
    )
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        help=(
            "Override the local execution date for testing. "
            "Must be a Saturday, format YYYY-MM-DD."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Evaluate compliance and roll back all notification changes.",
    )
    return parser.parse_args()


def get_execution_date(date_override: date | None = None) -> date:
    execution_date = (
        date_override
        if date_override is not None
        else datetime.now(TIMEZONE).date()
    )

    if execution_date.weekday() != 5:
        raise ValueError(
            f"Execution date must be a Saturday; received {execution_date}."
        )

    return execution_date


def get_target_week_start(execution_date: date) -> date:
    if execution_date.weekday() != 5:
        raise ValueError("Execution date must be a Saturday.")

    return execution_date + timedelta(days=2)


def run_compliance_job(
    db: Session,
    *,
    execution_date: date,
    dry_run: bool = False,
) -> int:
    target_week_start = get_target_week_start(execution_date)

    try:
        lock_acquired = db.execute(
            text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
            {"lock_key": ADVISORY_LOCK_KEY},
        ).scalar_one()

        if not lock_acquired:
            logger.warning(
                "Another planning compliance job is already running. "
                "This execution will be skipped."
            )
            db.rollback()
            return 0

        notifications = (
            PlanningNotificationService().generate_weekly_noncompliance(
                db,
                week_start_date=target_week_start,
            )
        )

        notification_count = len(notifications)

        if dry_run:
            db.rollback()
            logger.info(
                "Planning compliance dry-run completed; all changes rolled "
                "back. Execution date: %s; target week: %s to %s; "
                "notifications that would be created or updated: %s",
                execution_date,
                target_week_start,
                target_week_start + timedelta(days=6),
                notification_count,
            )
            return notification_count

        db.commit()

        logger.info(
            "Planning compliance completed. Execution date: %s; "
            "target week: %s to %s; notifications created or updated: %s",
            execution_date,
            target_week_start,
            target_week_start + timedelta(days=6),
            notification_count,
        )

        return notification_count

    except Exception:
        db.rollback()
        logger.exception("Weekly planning compliance job failed.")
        raise


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    args = parse_args()

    try:
        execution_date = get_execution_date(args.date)
    except ValueError as exc:
        logger.error("%s", exc)
        return 2

    target_week_start = get_target_week_start(execution_date)

    logger.info(
        "Starting Saturday planning compliance. "
        "Execution date: %s; target week starts: %s; dry-run: %s",
        execution_date,
        target_week_start,
        args.dry_run,
    )

    db = SessionLocal()

    try:
        run_compliance_job(
            db,
            execution_date=execution_date,
            dry_run=args.dry_run,
        )
        return 0
    except Exception:
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
