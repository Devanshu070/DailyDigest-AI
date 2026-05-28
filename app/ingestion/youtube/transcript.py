import logging

log = logging.getLogger(__name__)

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound
    HAS_TRANSCRIPT_API = True
except ImportError:
    HAS_TRANSCRIPT_API = False


def fetch_transcript(video_id: str) -> str:
    """
    Returns an English transcript for the video as a single string,
    or "" if no transcript is available.

    Tries manually created transcripts first, then auto-generated ones.
    Non-English transcripts are intentionally ignored.
    """
    if not HAS_TRANSCRIPT_API:
        log.warning("youtube-transcript-api not installed — transcripts unavailable.")
        return ""

    try:
        transcript_list = YouTubeTranscriptApi().list(video_id)
        for fetch_fn in [
            lambda tl: tl.find_manually_created_transcript(["en", "en-US", "en-GB", "en-IN"]),
            lambda tl: tl.find_generated_transcript(["en", "en-US", "en-GB", "en-IN"]),
        ]:
            try:
                transcript = fetch_fn(transcript_list).fetch()
                return "\n".join(
                    segment.text if hasattr(segment, "text") else segment["text"]
                    for segment in transcript
                )
            except Exception:
                continue

        log.debug("No English transcript available for video %s — falling back to description", video_id)

    except TranscriptsDisabled:
        log.debug("Transcripts disabled for video %s", video_id)
    except NoTranscriptFound:
        log.debug("No transcript found for video %s", video_id)
    except Exception as exc:
        log.warning("Unexpected error fetching transcript for %s: %s", video_id, exc)

    return ""
