"""Offline evaluation of the AI module against the synthetic dataset.

Runs ``analyze_email`` (mock provider by default, so no API key or network
access is required) over every record in the dataset and measures the
outputs against the stored expected labels.

Usage:
    python scripts/evaluate.py
    python scripts/evaluate.py --dataset tests/fixtures/sample_emails.json --report docs/EVALUATION_REPORT.md
    python scripts/evaluate.py --provider openai        # needs OPENAI_API_KEY

Every number in the generated report is measured by this script; nothing is
estimated or hardcoded.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ai_email import Settings, analyze_email, set_settings

LABEL_FIELDS = ("category", "priority", "sentiment", "reply_required", "action_required")
EXTRACTION_FIELDS = ("order_number", "invoice_number", "amount", "currency", "customer_name", "meeting_date")


class Score:
    def __init__(self) -> None:
        self.correct = 0
        self.total = 0
        self.failures: list[str] = []

    @property
    def rate(self) -> float:
        return (100.0 * self.correct / self.total) if self.total else 100.0

    def add(self, ok: bool, label: str) -> None:
        self.total += 1
        if ok:
            self.correct += 1
        else:
            self.failures.append(label)


def _category_ok(expected: dict[str, Any], predicted: str) -> bool:
    allowed = expected.get("category_any_of") or [expected.get("category")]
    return predicted in allowed


def _deadline_ok(expected: dict[str, Any], analysis: Any) -> tuple[bool, str]:
    phrase = expected.get("deadline_text")
    if phrase is None:
        return True, ""
    due = expected.get("due_date")
    for mention in analysis.extracted_information.deadlines:
        if phrase.lower() in mention.text.lower():
            got = mention.normalized_date.isoformat() if mention.normalized_date else None
            return got == due, f"expected due {due}, got {got} for phrase {mention.text!r}"
    return False, f"deadline phrase {phrase!r} not found in extracted deadlines"


def evaluate(dataset_path: str, provider: str) -> dict[str, Any]:
    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    emails = dataset["emails"]

    settings = Settings.from_env(load_dotenv=True)
    if provider:
        settings = settings.replace(provider=provider)
    set_settings(settings)

    scores: dict[str, Score] = {name: Score() for name in LABEL_FIELDS}
    extraction_scores: dict[str, Score] = {name: Score() for name in EXTRACTION_FIELDS}
    hallucination = Score()
    deadline_score = Score()
    status_failures: list[str] = []
    per_group_category: dict[str, Score] = defaultdict(Score)
    errors: list[str] = []

    for record in emails:
        expected = record["expected"]
        email = {
            "subject": record["subject"],
            "sender": record["sender"],
            "recipients": record.get("recipients", []),
            "body": record["body"],
            "received_at": record["received_at"],
            "message_id": record["id"],
        }
        try:
            analysis = analyze_email(email, timezone=dataset.get("reference_timezone", "UTC"))
        except Exception as exc:  # pragma: no cover - reported, not hidden
            errors.append(f"{record['id']}: {type(exc).__name__}: {exc}")
            continue

        if analysis.processing_metadata.processing_status.value != "completed":
            status_failures.append(f"{record['id']}: {analysis.processing_metadata.processing_status.value}")

        predicted_category = analysis.category.value
        group_score = per_group_category[record["group"]]
        group_score.add(_category_ok(expected, predicted_category), record["id"])

        for field in LABEL_FIELDS:
            if field == "category":
                ok = _category_ok(expected, predicted_category)
                shown = f"{predicted_category} not in {expected.get('category_any_of') or [expected['category']]}"
            else:
                expected_value = expected.get(field)
                got_value = getattr(analysis, field)
                ok = expected_value == got_value
                shown = f"expected {expected_value!r}, got {got_value!r}"
            scores[field].add(ok, f"{record['id']} ({shown})")

        extracted = analysis.extracted_information
        for field in EXTRACTION_FIELDS:
            if expected.get(field) is None:
                continue
            got = getattr(extracted, field)
            ok = str(got) == str(expected[field])
            extraction_scores[field].add(ok, f"{record['id']}: expected {expected[field]!r}, got {got!r}")

        for field in expected.get("must_be_absent", []):
            got = getattr(extracted, field, None)
            hallucination.add(got is None, f"{record['id']}: {field} was invented as {got!r}")

        ok, detail = _deadline_ok(expected, analysis)
        deadline_score.add(ok, f"{record['id']}: {detail}")

    total_expected = sum(score.total for score in scores.values())
    total_correct = sum(score.correct for score in scores.values())
    total_ext = sum(score.total for score in extraction_scores.values())
    total_ext_correct = sum(score.correct for score in extraction_scores.values())

    return {
        "dataset": dataset_path,
        "dataset_version": dataset.get("dataset_version"),
        "email_count": len(emails),
        "provider": settings.provider,
        "model": settings.effective_model,
        "evaluated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "errors": errors,
        "status_failures": status_failures,
        "label_metrics": {
            name: {
                "correct": s.correct,
                "total": s.total,
                "accuracy_pct": round(s.rate, 2),
                "failures": s.failures[:20],
            }
            for name, s in scores.items()
        },
        "label_overall": {
            "correct": total_correct,
            "total": total_expected,
            "accuracy_pct": round(100.0 * total_correct / total_expected, 2) if total_expected else 0.0,
        },
        "extraction_metrics": {
            name: {
                "correct": s.correct,
                "total": s.total,
                "accuracy_pct": round(s.rate, 2),
                "failures": s.failures[:20],
            }
            for name, s in extraction_scores.items()
        },
        "extraction_overall": {
            "correct": total_ext_correct,
            "total": total_ext,
            "accuracy_pct": round(100.0 * total_ext_correct / total_ext, 2) if total_ext else 0.0,
        },
        "hallucination_check": {
            "invented": hallucination.total - hallucination.correct,
            "checked": hallucination.total,
            "failures": hallucination.failures[:20],
        },
        "deadline_check": {
            "correct": deadline_score.correct,
            "total": deadline_score.total,
            "accuracy_pct": round(deadline_score.rate, 2),
            "failures": deadline_score.failures[:20],
        },
        "per_group_category": {
            group: {"correct": s.correct, "total": s.total, "accuracy_pct": round(s.rate, 2)}
            for group, s in sorted(per_group_category.items())
        },
    }


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# AI Module Evaluation Report",
        "",
        "Generated by `python scripts/evaluate.py`. Every figure below is measured by that",
        "script against the stored expected labels - no accuracy number is hand-written.",
        "",
        f"- Evaluated at: {result['evaluated_at']}",
        f"- Dataset: `{result['dataset']}` (version {result['dataset_version']}, {result['email_count']} emails)",
        f"- Provider: `{result['provider']}` / model `{result['model']}`",
        f"- Analyzer errors: {len(result['errors'])}",
        f"- Non-completed processing statuses: {len(result['status_failures'])}",
        "",
        "## Label accuracy",
        "",
        "| Field | Correct | Total | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for name, metric in result["label_metrics"].items():
        lines.append(f"| {name} | {metric['correct']} | {metric['total']} | {metric['accuracy_pct']}% |")
    overall = result["label_overall"]
    lines.append(
        f"| **overall** | **{overall['correct']}** | **{overall['total']}** | **{overall['accuracy_pct']}%** |"
    )

    lines += [
        "",
        "## Category accuracy by dataset group",
        "",
        "| Group | Correct | Total | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for group, metric in result["per_group_category"].items():
        lines.append(f"| {group} | {metric['correct']} | {metric['total']} | {metric['accuracy_pct']}% |")

    lines += [
        "",
        "## Structured extraction (only fields expected to be present)",
        "",
        "| Field | Correct | Total | Accuracy |",
        "|---|---:|---:|---:|",
    ]
    for name, metric in result["extraction_metrics"].items():
        lines.append(f"| {name} | {metric['correct']} | {metric['total']} | {metric['accuracy_pct']}% |")
    ext = result["extraction_overall"]
    lines.append(f"| **overall** | **{ext['correct']}** | **{ext['total']}** | **{ext['accuracy_pct']}%** |")

    halluc = result["hallucination_check"]
    deadline = result["deadline_check"]
    lines += [
        "",
        "## Reliability checks",
        "",
        f"- Fields that must stay null but were invented: **{halluc['invented']} / {halluc['checked']}** checked",
        f"- Deadline phrase + normalized date correct: **{deadline['correct']} / {deadline['total']}** ({deadline['accuracy_pct']}%)",
        "",
    ]

    failures = []
    for name, metric in result["label_metrics"].items():
        for item in metric["failures"]:
            failures.append(f"- {name}: {item}")
    for name, metric in result["extraction_metrics"].items():
        for item in metric["failures"]:
            failures.append(f"- {name}: {item}")
    for item in deadline["failures"]:
        failures.append(f"- deadline: {item}")
    for item in halluc["failures"]:
        failures.append(f"- hallucination: {item}")
    for item in result["errors"]:
        failures.append(f"- error: {item}")

    if failures:
        lines += ["## Recorded mismatches (first 60)", ""] + failures[:60] + [""]
    else:
        lines += ["## Recorded mismatches", "", "None.", ""]

    lines += [
        "## How to reproduce",
        "",
        "```bash",
        "python scripts/generate_dataset.py",
        "python scripts/evaluate.py",
        "```",
        "",
        "## Live-provider evaluation",
        "",
        "The report above is produced with the offline mock provider so it needs no",
        "credentials. To measure a real provider instead:",
        "",
        "```bash",
        "set OPENAI_API_KEY=...      # or GEMINI_API_KEY=...",
        "python scripts/evaluate.py --provider openai   # or --provider gemini",
        "```",
        "",
        "Live-provider runs incur API cost and were not executed in this repository;",
        "see `docs/AI_MODULE.md` for what was actually verified.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the AI module on the synthetic dataset")
    parser.add_argument("--dataset", default="tests/fixtures/sample_emails.json")
    parser.add_argument("--provider", default="mock")
    parser.add_argument("--report", default="docs/EVALUATION_REPORT.md")
    parser.add_argument("--json-out", default=None, help="optional path for the raw metrics JSON")
    args = parser.parse_args()

    result = evaluate(args.dataset, args.provider)
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(result), encoding="utf-8")
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(result, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in {"label_metrics", "extraction_metrics"}},
            indent=2,
        )
    )
    print(f"report written to {report_path}")


if __name__ == "__main__":
    main()
