
"""Generate a read-only Session Plan attachment storage report."""

import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def main() -> int:
    try:
        from app.database import SessionLocal
        from app.services.session_plan.attachment_reconciliation import (
            build_attachment_reconciliation_report,
        )

        db = SessionLocal()
        try:
            report = build_attachment_reconciliation_report(db)
        finally:
            db.close()

        print("\nSession Plan Attachment Reconciliation")
        print("--------------------------------------")
        print(f"Storage files scanned: {report.scanned_files}")
        print(f"Database references:   {report.referenced_files}")
        print(f"Ignored files:         {report.ignored_files}")
        print(f"Orphan candidates:     {len(report.orphan_candidates)}")
        print(f"Missing files:         {len(report.missing_files)}")

        if report.orphan_candidates:
            print("\nOrphan candidates (not deleted):")
            for candidate in report.orphan_candidates:
                print(
                    f"  {candidate.storage_key} "
                    f"({candidate.file_size_bytes} bytes, "
                    f"modified {candidate.modified_at.isoformat()})"
                )

        if report.missing_files:
            print("\nDatabase references with missing files:")
            for storage_key in report.missing_files:
                print(f"  {storage_key}")

        print("\nReport only. No files or database records were modified.")
        return 0

    except Exception as error:
        print(
            f"Attachment reconciliation failed: {error}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
