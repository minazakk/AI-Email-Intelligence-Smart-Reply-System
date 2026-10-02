#!/usr/bin/env python3
"""Seed the database with a demo account and a realistic synthetic inbox.

Usage::

    python scripts/seed_demo.py                 # import + analyse (idempotent)
    python scripts/seed_demo.py --skip-ai       # import only, no AI calls
    python scripts/seed_demo.py --reset         # wipe the demo inbox first
    python scripts/seed_demo.py --email me@x.dev --password 'OtherPass!42'

The dataset lives in ``data/emails_seed.csv`` (63 messages across every
category the classifier knows about). Re-running the script never creates
duplicates: ingestion dedupes on a content fingerprint and analysis only runs
for messages still marked ``pending``.
"""

from __future__ import annotations

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete, func, select  # noqa: E402

import app.models  # noqa: E402,F401
from app.core.enums import EmailSource  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.models.action import ActionItem  # noqa: E402
from app.models.analysis import EmailAnalysis, ExtractedEntity  # noqa: E402
from app.models.email import Email  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services import auth_service, category_service, email_ingest  # noqa: E402
from app.services.ai.factory import get_ai_provider  # noqa: E402
from app.services.ai.pipeline import analyze_email  # noqa: E402

DATASET = ROOT / "data" / "emails_seed.csv"
DEFAULT_EMAIL = "demo@example.com"
DEFAULT_PASSWORD = "DemoPassw0rd!"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="demo account address")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="demo account password")
    parser.add_argument("--full-name", default="Demo User", help="display name for the demo account")
    parser.add_argument("--dataset", type=pathlib.Path, default=DATASET, help="CSV dataset to import")
    parser.add_argument("--reset", action="store_true", help="delete the demo inbox before importing")
    parser.add_argument("--skip-ai", action="store_true", help="import without running AI analysis")
    parser.add_argument("--create-schema", action="store_true",
                        help="run Base.metadata.create_all instead of expecting Alembic migrations")
    return parser.parse_args(argv)


def get_or_create_user(db, *, email: str, password: str, full_name: str) -> tuple[User, str]:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        user = auth_service.create_user(db, email=email, password=password, full_name=full_name)
        action = "created"
    else:
        user.password_hash = hash_password(password)
        user.full_name = full_name or user.full_name
        action = "updated"
    user.is_verified = True
    db.flush()
    return user, action


def reset_inbox(db, user_id: int) -> None:
    count = db.scalar(select(func.count(Email.id)).where(Email.user_id == user_id)) or 0
    if not count:
        return
    db.execute(delete(ExtractedEntity).where(ExtractedEntity.user_id == user_id))
    db.execute(delete(ActionItem).where(ActionItem.user_id == user_id))
    db.execute(delete(EmailAnalysis).where(EmailAnalysis.user_id == user_id))
    db.execute(delete(Email).where(Email.user_id == user_id))
    db.commit()


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if not args.dataset.exists():
        print(f"error: dataset not found at {args.dataset}", file=sys.stderr)
        return 1

    if args.create_schema:
        Base.metadata.create_all(engine)

    db = SessionLocal()
    try:
        user, user_action = get_or_create_user(
            db, email=args.email, password=args.password, full_name=args.full_name
        )
        category_service.seed_default_categories(db)
        db.commit()
        print(f"account {user_action}: {user.email} (id={user.id})")

        if args.reset:
            reset_inbox(db, user.id)
            print("demo inbox cleared")

        rows = email_ingest.parse_dataset(
            filename=args.dataset.name,
            content_type="text/csv",
            content=args.dataset.read_bytes(),
        )
        summary = email_ingest.run_dataset_import(
            db,
            user_id=user.id,
            rows=rows,
            source=EmailSource.csv,
            filename=args.dataset.name,
        )
        db.commit()
        print(
            f"import: received={summary.received} created={summary.created} "
            f"duplicates={summary.duplicates} failed={summary.failed}"
        )
        for err in summary.errors[:10]:
            print(f"  row {err.row}: {err.message}")

        analysed = failed = 0
        if not args.skip_ai:
            provider = get_ai_provider()
            pending = list(
                db.scalars(
                    select(Email).where(
                        Email.user_id == user.id,
                        Email.processing_status == "pending",
                    )
                )
            )
            for email in pending:
                try:
                    analyze_email(db, email, provider, user_timezone=user.timezone)
                    analysed += 1
                except Exception as exc:  # noqa: BLE001 - reported, then continue
                    failed += 1
                    print(f"  analysis failed for email {email.id}: {exc}")
                finally:
                    db.commit()
            print(f"analysis: processed={analysed} failed={failed}")
        else:
            print("analysis: skipped (--skip-ai)")

        _print_report(db, user.id)
        print("\nSign in with:")
        print(f"  email:    {user.email}")
        print(f"  password: {args.password}")
        print("  POST /api/v1/auth/login")
        return 0
    finally:
        db.close()


def _print_report(db, user_id: int) -> None:
    from sqlalchemy import func

    from app.core.enums import URGENT_PRIORITIES
    from app.models.action import SuggestedReply

    total = db.scalar(select(func.count(Email.id)).where(Email.user_id == user_id)) or 0
    analysed = db.scalar(
        select(func.count(EmailAnalysis.id)).where(EmailAnalysis.user_id == user_id)
    ) or 0
    urgent = db.scalar(
        select(func.count(Email.id))
        .join(EmailAnalysis, EmailAnalysis.email_id == Email.id)
        .where(
            Email.user_id == user_id,
            (EmailAnalysis.priority.in_(URGENT_PRIORITIES))
            | (EmailAnalysis.sentiment == "urgent"),
        )
    ) or 0
    actions = db.scalar(
        select(func.count(ActionItem.id)).where(ActionItem.user_id == user_id)
    ) or 0
    replies = db.scalar(
        select(func.count(SuggestedReply.id)).where(SuggestedReply.user_id == user_id)
    ) or 0

    print("\ninbox summary")
    print(f"  emails:        {total}")
    print(f"  analysed:      {analysed}")
    print(f"  urgent:        {urgent}")
    print(f"  action items:  {actions}")
    print(f"  draft replies: {replies}")

    distribution = db.execute(
        select(EmailAnalysis.category, func.count(EmailAnalysis.id))
        .where(EmailAnalysis.user_id == user_id)
        .group_by(EmailAnalysis.category)
        .order_by(func.count(EmailAnalysis.id).desc())
    ).all()
    if distribution:
        print("  by category:")
        for category, count in distribution:
            print(f"    {category:<24} {count}")


if __name__ == "__main__":
    raise SystemExit(main())
