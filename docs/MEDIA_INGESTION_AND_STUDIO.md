# Media ingestion and Studio generation

Staging-only architecture for image, audio, video, and YouTube sources, plus
Studio outputs that speak (audio overview, video overview) or render as
infographics. No GPU. No self-hosted image or video generation models.

Secrets stay in `/etc/atlaslm/staging.env` on the server. Never commit values.

## Pipeline

```text
Source input                         Ingestion pipeline
------------                         ------------------
PDF/DOCX/...   text extract  ---------------------------------+
Image          EXIF strip -> tesseract OCR                    |
               + vision describe (Langdock, image_url) -------+--> chunk -> embed
Audio file     ffprobe -> ffmpeg 16 kHz mono FLAC -> Gladia --+    -> pgvector
Video file     ffmpeg audio strip -> Gladia ------------------+    + citations
YouTube URL    captions (youtube-transcript-api)              |
                 fallback: yt-dlp audio -> Gladia ------------+
```

Long-running work is a `media_jobs` row the frontend can poll:

`queued -> processing -> waiting -> done | failed`

`waiting` is used while Gladia transcribes. The worker polls every 15 seconds
for up to 60 minutes, and Gladia may POST
`/api/v1/internal/media/stt-callback?token=...`. The token is per-job; anything
else is rejected with 403.

Failed jobs retry at most twice with exponential backoff. A reaper marks stale
processing jobs failed (or retries them) so nothing stays "processing" forever.
Each user is limited to two concurrent media/Studio jobs (`ATLAS_MEDIA_CONCURRENT_JOBS`).

## Citations

Every indexed source type stores chunks that cite a real location:

| Source | Citation |
| --- | --- |
| Image | `{source_id, region: "full"}` plus OCR and vision chunk groups |
| Audio / video | `{source_id, start_ms, end_ms, speaker}` |
| YouTube | `{source_id, video_id, start_s}` rendered as `watch?v=ID&t=START` |

If a question is not in the sources, the assistant says it cannot find it and
does not invent a citation.

## Studio outputs

| Output | Path |
| --- | --- |
| Audio overview | Grounded two-host script (Maya / Theo) -> `TTSProvider.synthesize` (Kokoro-82M CPU) -> ffmpeg concat + loudnorm -> MP3 128 kbps in `atlaslm_staging_audio` |
| Video overview | Slide JSON -> HTML (1920x1080, brand palette) -> headless Chromium PNG -> Kokoro narration -> ffmpeg H.264/AAC 1080p with 300 ms fades |
| Infographic | Structured JSON -> SVG templates (facts / comparison / timeline) -> PNG 1200x1500 and SVG download |

`TTSProvider` is the swap point for a paid voice later. Only Kokoro is shipped.

## Staging env keys (names only)

Filled on the server. Empty placeholders live in `deploy/staging/env.example`.

- `GLADIA_API_KEY`
- `GLADIA_BASE_URL=https://api.gladia.io`
- `GLADIA_CALLBACK_BASE=https://api.staging.atlaslm.cloud`
- `ATLAS_MEDIA_MAX_MB=2048`
- `ATLAS_MEDIA_MAX_SECONDS=10800`
- `ATLAS_YTDLP_COOKIES` (optional host path, root-only)
- `ATLAS_MEDIA_CONCURRENT_JOBS=2`
- `ATLAS_MEDIA_DIR=/data/media`
- Kokoro model/voice paths and Chromium binary (optional if on PATH)

Deploy remains `atlaslmctl staging deploy <sha>` from a commit on `main`.

## Failure messages

Users see a specific reason, not a generic failure:

- unsupported image or media type
- image larger than 20 MB
- image with no readable content
- file that is not a real audio/video track (including a renamed document)
- oversize or overlong media
- Gladia missing / timeout
- YouTube private, age-restricted, live, or "YouTube blocked automated access to this video. Upload the video file instead."
