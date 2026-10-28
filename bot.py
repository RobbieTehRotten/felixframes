from datetime import datetime
import os
import sys
import time
import urllib.request
from atproto import Client
from atproto.exceptions import AtProtocolError
import cv2

# --- BLUESKY CONFIGURATION ---
HANDLE = "malteseshakeframes.bsky.social"
APP_PASSWORD = (
    os.getenv("BLUESKY_APP_PASSWORD")
    or os.getenv("BSKY_PASSWORD")
    or "vpxt-man6-sgqi-cgrm"
)

# --- INTERNET ARCHIVE CONFIGURATION ---
ARCHIVE_VIDEO_URL = "https://archive.org/download/Untitledfel/Untitledfel.mp4"

MAX_BYTES = 950_000
LOCAL_STATE = "frame_counter.txt"
SESSION_FILE = "bsky_session.txt"
TEMP_IMG = "temp_frame.png"


def get_current_frame_index():
  if os.path.exists(LOCAL_STATE):
    with open(LOCAL_STATE, "r") as f:
      content = f.read().strip()
      if content:
        return int(content)
  return 0


def save_current_frame_index(index):
  with open(LOCAL_STATE, "w") as f:
    f.write(str(index))


def generate_progress
