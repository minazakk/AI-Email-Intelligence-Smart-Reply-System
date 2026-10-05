"""Command line demo for the standalone AI module.

Examples::

    python -m ai_email.cli analyze --text "Please send the invoice by Friday"
    python -m ai_email.cli analyze --file samples/order_issue.eml
    python -m ai_email.cli reply --file samples/order_issue.eml --tone apologetic
    python -m ai_email.cli search "show urgent customer complaints from this week"
    python -m ai_email.cli ask "which emails need my reply?" --records records.json
    python -m ai_email.cli deadline --text "next Monday" --reference 2025-09-22T09:00:00+00:00

No database, backend or API key is required when AI_PROVIDER=mock.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .config import get_settings, set_settings
from .date_normalizer import normalize_deadline
from .email_parser import parse_email_text, parse_eml
from .exceptions import AIEmailError, InputValidationError
from .schemas import EmailInput, ThreadMessage
from .services import (
    analyze_email,
    answer_inbox_question,
    generate_smart_reply,
    parse_search_query,
)


def _read_file(path: str) -> bytes:
    file_path = Path(path)
    if not file_path.is_file():
        raise InputValidationError(f"file not found: {path}")
    return file_path.read_bytes()


def _load_email(args: argparse.Namespace) -> EmailInput:
    if getattr(args, "text", None):
        return parse_email_text(args.text)
    if getattr(args, "file", None):
        data = _read_file(args.file)
        if args.file.lower().endswith(".eml"):
            return parse_eml(data, max_bytes=get_settings().max_eml_bytes)
        if args.file.lower().endswith((".json", ".txt")):
            text = data.decode("utf-8", errors="replace")
            if args.file.lower().endswith(".json"):
                payload = json.loads(text)
                if isinstance(payload, list):
                    payload = payload[0]
                return EmailInput.model_validate(payload)
            return parse_email_text(text)
        raise InputValidationError("unsupported file type; use .eml, .json or .txt")
    if not sys.stdin.isatty():
        raw = sys.stdin.read()
        if raw.strip():
            return parse_email_text(raw)
    raise InputValidationError("provide --text, --file or pipe raw email text on stdin")


def _load_json(path: str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_records(path: str) -> list[Any]:
    payload = _load_json(path)
    if isinstance(payload, dict):
        for key in ("emails", "records", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise InputValidationError("records file must contain a JSON list or an object with an 'emails' list")
    return payload


def _emit(payload: Any) -> None:
    if hasattr(payload, "model_dump"):
        payload = payload.model_dump(mode="json")
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=str))


def _cmd_analyze(args: argparse.Namespace) -> int:
    email = _load_email(args)
    analysis = analyze_email(
        email,
        reference_datetime=args.reference,
        timezone=args.timezone,
        on_error=args.on_error,
    )
    _emit(analysis)
    return 0 if analysis.processing_metadata.processing_status.value != "failed" else 2


def _cmd_reply(args: argparse.Namespace) -> int:
    email = _load_email(args)
    thread: list[ThreadMessage] = []
    if args.thread:
        for item in _load_json(args.thread):
            thread.append(ThreadMessage.model_validate(item))
    result = generate_smart_reply(
        email,
        thread_messages=thread,
        tone=args.tone,
        business_context=args.context,
        length_preference=args.length,
        timezone=args.timezone,
    )
    _emit(result)
    return 0


def _cmd_search(args: argparse.Namespace) -> int:
    intent = parse_search_query(
        args.question,
        reference_datetime=args.reference,
        timezone=args.timezone,
    )
    _emit(intent)
    return 0


def _cmd_ask(args: argparse.Namespace) -> int:
    records = _load_records(args.records) if args.records else []
    actions = _load_json(args.actions) if args.actions else []
    answer = answer_inbox_question(
        args.question,
        records,
        actions,
        reference_datetime=args.reference,
        timezone=args.timezone,
    )
    _emit(answer)
    return 0


def _cmd_deadline(args: argparse.Namespace) -> int:
    result = normalize_deadline(args.text, args.reference, args.timezone)
    _emit(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ai_email", description="Standalone AI email module CLI")
    parser.add_argument("--provider", help="override AI_PROVIDER (mock, openai, gemini)")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--timezone", default=None, help="IANA timezone (default from env)")
    common.add_argument("--reference", default=None, help="reference datetime (ISO 8601)")

    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", parents=[common], help="analyze one email")
    analyze.add_argument("--text", help="raw email text")
    analyze.add_argument("--file", help="path to .eml / .json / .txt")
    analyze.add_argument("--on-error", choices=["raise", "status", "fallback"], default="raise")
    analyze.set_defaults(func=_cmd_analyze)

    reply = sub.add_parser("reply", parents=[common], help="draft a smart reply")
    reply.add_argument("--text", help="raw email text")
    reply.add_argument("--file", help="path to .eml / .json / .txt")
    reply.add_argument("--tone", default="professional")
    reply.add_argument("--length", default=None)
    reply.add_argument("--context", default=None, help="trusted business context")
    reply.add_argument("--thread", help="JSON file with thread messages")
    reply.set_defaults(func=_cmd_reply)

    search = sub.add_parser("search", parents=[common], help="parse a search question")
    search.add_argument("question")
    search.set_defaults(func=_cmd_search)

    ask = sub.add_parser("ask", parents=[common], help="answer from supplied records")
    ask.add_argument("question")
    ask.add_argument("--records", help="JSON file with records supplied by the backend")
    ask.add_argument("--actions", help="JSON file with pending actions")
    ask.set_defaults(func=_cmd_ask)

    deadline = sub.add_parser("deadline", parents=[common], help="normalize a deadline phrase")
    deadline.add_argument("--text", required=True)
    deadline.set_defaults(func=_cmd_deadline)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.provider:
            set_settings(get_settings().replace(provider=args.provider))
        if args.timezone is None:
            args.timezone = get_settings().default_timezone
        return int(args.func(args))
    except AIEmailError as exc:
        print(json.dumps({"error": type(exc).__name__, "detail": str(exc)}), file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(json.dumps({"error": "JSONDecodeError", "detail": str(exc)}), file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
