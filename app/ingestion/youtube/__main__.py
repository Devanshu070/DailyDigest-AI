# %%

import logging
import sys
from datetime import datetime, timezone

from app.ingestion.youtube.ingester import YouTubeIngester


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)-8s %(name)s — %(message)s",
    )

    # Usage: python -m app.ingestion.youtube [@handle] [run_at_iso] [window_hours]
    # run_at_iso example: 2025-05-21T06:00:00+00:00
    source = "@bytemonk"
    if len(sys.argv) > 1 and not sys.argv[1].startswith(("-f=", "--f=")):
        source = sys.argv[1]

    run_at: datetime | None = None
    if len(sys.argv) > 2:
        try:
            run_at = datetime.fromisoformat(sys.argv[2])
            if run_at.tzinfo is None:
                run_at = run_at.replace(tzinfo=timezone.utc)
        except ValueError:
            print(f"[WARN] Could not parse run_at '{sys.argv[2]}' — using current UTC time.", file=sys.stderr)

    window_hours = 24
    if len(sys.argv) > 3:
        try:
            window_hours = int(sys.argv[3])
        except ValueError:
            print(f"[WARN] Could not parse window_hours '{sys.argv[3]}' — using 24 hours.", file=sys.stderr)

    ingester = YouTubeIngester(run_at=run_at, window_hours=window_hours)

    try:
        entries = ingester.fetch(source)
        articles = ingester.parse(entries)
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)

    if not articles:
        print(f"No videos published in the last {window_hours} hours for {source}.")
    else:
        for art in articles:
            print(
                f"{art['title']} | {art['url']} | "
                f"{art['published_at'].isoformat()} | "
                f"{art['raw_content_source']} | {len(art['raw_content'])} chars"
            )


if __name__ == "__main__":
    main()

# %%
