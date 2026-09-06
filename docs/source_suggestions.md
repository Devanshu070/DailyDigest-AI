# Source suggestions

Source discovery recommends blogs and YouTube channels from a user's saved
interest profile. It runs independently of digest ingestion and delivery.

## User flow

Open Suggested Sources from the Sources page. Returned suggestions are selected
by default. Clicking a card toggles its selection; clicking its URL or blog/YouTube
badge opens the source in a new tab without toggling selection. Add Selected
subscribes to the selected sources through the existing source-creation endpoint.

The modal is centered on the viewport through a React portal to `document.body`.
Its result area scrolls when the list exceeds the modal height.

**Find more**, below the last result, appends new suggestions and preserves
existing selections, including deselected cards. Newly appended results are
selected by default. Existing cards remain visible during the request. Duplicate
URLs are not appended. When nothing new is returned, the list remains in place
with a “No new sources found right now” message. Request errors appear below
the list and allow another attempt. Add Selected is disabled while finding more.

Accumulated results are component state, not saved browsing history. Closing and
reopening the modal loads the initial batch again; Find more does not persist a
history of batches. Responses from a closed modal or previous account are ignored.

## API

```text
GET /api/v1/sources/suggestions
```

| Query parameter | Behavior |
|---|---|
| `email` | Required user email, used to load interests and subscriptions. |
| `refresh` | Defaults to `false`. With no exclusions, `true` bypasses the initial cache read. |
| `exclude_urls` | Optional repeated parameter containing previously displayed URLs. A nonempty list runs discovery without reading or replacing the initial cache. |

Example find-more request:

```text
/api/v1/sources/suggestions?email=user%40example.com&refresh=true&exclude_urls=https%3A%2F%2Fexample.com%2Ffeed
```

The response contains `suggestions`, `cached`, and `generated_at`. Each suggestion
has `name`, `url`, `source_type` (`blog` or `youtube`), and `recommendation_reason`.
Exclusions are temporary request inputs; they do not create subscriptions.

## Discovery and ranking

1. Generate up to five queries from the user's interests using the assembler LLM.
2. Search Exa sequentially for up to five results per query.
3. Deduplicate URLs and remove subscribed or previously displayed candidates.
4. Cap candidates at 25 and build a bounded ranking prompt.
5. Rank with `openai/gpt-oss-120b` through the configured assembler instance.
6. Validate returned URLs and source types, deduplicate, and remove subscriptions
   and request exclusions again before responding.

The ranking prompt asks for 0–10 recommendations from the candidate list. Ten is
a prompt instruction, not a hard response-length limit. Relevant trusted sources
are prioritized, followed by other relevant sources, including lesser-known or
unverified ones. Unknown credibility alone is not grounds for exclusion. The
prompt asks for evidence of credibility rather than popularity alone; the app
does not independently certify sources or display trust badges.

### Ranking input limits

| Input | Current limit |
|---|---|
| Candidate title | 100 characters |
| Evidence per candidate | 240 characters, from up to two highlights or the description |
| Combined candidate section | 6,000 characters, including titles and URLs |
| Interests in ranking prompt | 2,000 characters |
| Subscriptions/exclusions in ranking prompt | 1,000 characters of URLs |

Candidate URLs remain intact; entries that cannot fit are skipped. These are
character limits, not exact token guarantees. The complete subscription and
exclusion lists are still used for deterministic filtering, regardless of the
prompt limit. Query generation uses the supplied interest profile without the
ranking prompt's character cap.

These bounds prevent large Exa excerpts from inflating ranking requests. They do
not change stored source data or article/transcript summarization for digests.
The separate experiment summarizing 15 candidates into short summaries has **not**
been integrated into the application; discovery currently uses bounded excerpts.

## Cache and failure behavior

Nonempty initial results are cached per user for 24 hours in the API process.
The cache also checks the interest profile and subscription URLs; changes cause
regeneration. Restarting the process clears the cache, and separate workers do
not share it. Empty results are not cached. A refreshed empty result removes the
previous initial cache entry. Find-more requests leave that entry untouched.

Missing `EXA_API_KEY`, empty interests, handled provider failures, or no eligible
candidates can produce an empty list. The UI cannot distinguish all these causes;
check backend logs when repeated attempts return nothing. RecommendationService
contains a direct-LLM fallback, but the current orchestrator returns early when
search produces no candidates, so that fallback is not used by this endpoint.

URL normalization handles scheme/host case, `www.`, and trailing slashes. It does
not resolve redirects or identify equivalent YouTube handle/channel-ID URLs,
blog homepages versus feeds, or tracking-parameter variants. Syntactic validation
does not establish that a source is reachable or readable. Ranking quality and
candidate-only recommendations rely on the LLM prompt; membership in the candidate
list is not independently enforced by the validator.

Find more excludes already displayed URLs but does not pass those exclusions to
query generation or Exa. Search may return the same candidates, leaving nothing
new to recommend. It is not guaranteed pagination over a fixed result set.

## Checks

Run `uv run pytest tests/test_source_suggestions.py` for regression coverage of
bounded ranking input, validation, cache hits and invalidation, retrying empty
results, and find-more exclusions with preservation of the original cache.

From `frontend/`, run:

```bash
npx eslint src/components/SourceSuggestionsModal.js src/lib/api.js
```

For a UI check, deselect one suggestion, preview a URL and badge, then use Find
more. Confirm the existing selection remains unchanged, new cards appear below
the old ones, and no-new-result or error messages leave the existing list intact.
