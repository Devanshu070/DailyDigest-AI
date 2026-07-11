"""
main.py — Entry point for the DailyDigest pipeline.

Usage:
  python main.py             # scheduled mode: snaps window to cron time
  python main.py --manual    # manual/on-demand mode: rolling now-24h → now window
"""
import argparse
import logging
import sys
from app.runner import run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DailyDigest AI pipeline.")
    parser.add_argument(
        "--manual",
        action="store_true",
        default=False,
        help=(
            "Run in manual/on-demand mode: uses a rolling 24h window (now-24h → now). "
            "Default (scheduled) mode snaps the window to the configured cron time."
        ),
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Optional: For manual runs, target a specific user email. Defaults to settings.digest_recipient_email if omitted.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )

    run(manual=args.manual, target_email=args.email)


if __name__ == "__main__":
    main()
