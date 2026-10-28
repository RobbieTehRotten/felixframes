from datetime import datetime
import os
import sys
import time
import urllib.request

import cv2
from atproto import Client
from atproto.exceptions import AtProtocolError

# --- BLUESKY CONFIGURATION ---
HANDLE = "malteseshakeframes.bsky.social"
APP_PASSWORD = (
    os.getenv("BLUESKY_APP_PASSWORD")
    or os.getenv("BSKY_PASSWORD")
)

# --- INTERNET ARCHIVE CONFIGURATION ---
ARCHIVE_VIDEO_URL = "https://archive.org/download/Untitledfel/Untitledfel.mp4"

MAX_BYTES = 950_000
LOCAL_STATE = "frame_counter.txt"
SESSION_FILE = "bsky_session.txt"
TEMP_IMG = "temp_frame.png"


def get_current_frame_index():
    """Read the next frame index, starting at zero if no state file exists."""
    if not os.path.exists(LOCAL_STATE):
        return 0

    with open(LOCAL_STATE, "r", encoding="utf-8") as state_file:
        content = state_file.read().strip()

    if not content:
        return 0

    try:
        return max(0, int(content))
    except ValueError as exc:
        raise ValueError(
            f"{LOCAL_STATE} must contain a non-negative integer; got {content!r}."
        ) from exc


def save_current_frame_index(index):
    """Save the index of the next frame to post."""
    with open(LOCAL_STATE, "w", encoding="utf-8") as state_file:
        state_file.write(str(index))


def generate_progress_bar(current, total, bar_length=10):
    """Return a compact progress bar for the Bluesky post text."""
    if total <= 0:
        return ""

    percentage = (current / total) * 100
    filled_length = int(round(bar_length * current / float(total)))
    bar = "█" * filled_length + "▒" * (bar_length - filled_length)
    return f"{bar} {percentage:.1f}%"


def resolve_archive_url(url):
    """Try to resolve Internet Archive's redirect to a direct storage URL."""
    try:
        request = urllib.request.Request(
            url,
            method="HEAD",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.url
    except Exception as exc:
        print(
            "⚠️ Could not pre-resolve the Internet Archive redirect; "
            f"using the original URL: {exc}"
        )
        return url


def get_authenticated_client():
    """Reuse a saved Bluesky session, falling back to an app-password login."""
    client = Client()

    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as session_file:
                session_string = session_file.read().strip()

            if session_string:
                print("🔑 Resuming saved Bluesky session...")
                client.login(session_string=session_string)
                # Save the latest session value, which may have been refreshed.
                with open(SESSION_FILE, "w", encoding="utf-8") as session_file:
                    session_file.write(client.export_session_string())
                return client
