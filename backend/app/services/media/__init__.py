"""Shared media ingest errors and constants.

Public messages are user-facing. Logs must never include file contents
or transcripts at INFO.
"""
from __future__ import annotations

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv"}
MEDIA_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS

IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".heif": "image/heif",
}

KIND_IMAGE = "image"
KIND_AUDIO = "audio"
KIND_VIDEO = "video"
KIND_YOUTUBE = "youtube"

JOB_IMAGE = "image_ingest"
JOB_AUDIO = "audio_ingest"
JOB_VIDEO = "video_ingest"
JOB_YOUTUBE = "youtube_ingest"
JOB_AUDIO_OVERVIEW = "audio_overview"
JOB_VIDEO_OVERVIEW = "video_overview"
JOB_INFOGRAPHIC = "infographic"

STATUS_QUEUED = "queued"
STATUS_PROCESSING = "processing"
STATUS_WAITING = "waiting"
STATUS_DONE = "done"
STATUS_FAILED = "failed"

ACTIVE_JOB_STATUSES = (STATUS_QUEUED, STATUS_PROCESSING, STATUS_WAITING)

MSG_UNSUPPORTED_IMAGE = (
    "This file type is not supported. Upload a PNG, JPEG, WEBP, or HEIC image."
)
MSG_IMAGE_TOO_LARGE = (
    "This image is larger than 20 MB. Compress it or upload a smaller file."
)
MSG_IMAGE_EMPTY = (
    "This image contains no readable text or visual content that Atlas can index."
)
MSG_UNSUPPORTED_MEDIA = (
    "This file type is not supported. Upload MP3, WAV, M4A, AAC, OGG, FLAC, "
    "MP4, MOV, WEBM, or MKV."
)
MSG_NOT_MEDIA = (
    "This file is not a valid audio or video file. Atlas could not read a media track."
)
MSG_MEDIA_TOO_LARGE = (
    "This file is larger than the staging limit. Upload a shorter recording."
)
MSG_MEDIA_TOO_LONG = (
    "This recording is longer than the staging time limit. Split it into shorter files."
)
MSG_YOUTUBE_BLOCKED = (
    "YouTube blocked automated access to this video. Upload the video file instead."
)
MSG_YOUTUBE_PRIVATE = (
    "This YouTube video is private, so Atlas cannot ingest it."
)
MSG_YOUTUBE_AGE = (
    "This YouTube video is age-restricted, so Atlas cannot ingest it."
)
MSG_YOUTUBE_LIVE = (
    "This YouTube video is a live stream. Wait until it ends, then try again."
)
MSG_YOUTUBE_INVALID = (
    "That does not look like a valid YouTube link. Paste a video URL "
    "such as https://www.youtube.com/watch?v=..."
)
MSG_GLADIA_TIMEOUT = (
    "Transcription timed out after 60 minutes. Try a shorter file or try again."
)
MSG_GLADIA_MISSING = (
    "Speech transcription is not configured on this server. Contact your administrator."
)
MSG_CONCURRENT = (
    "You already have two media jobs running. Wait for one to finish, then try again."
)


class MediaIngestError(ValueError):
    """User-facing ingest failure. Safe to show in the UI."""

    def __init__(self, public_message: str):
        super().__init__(public_message)
        self.public_message = public_message
