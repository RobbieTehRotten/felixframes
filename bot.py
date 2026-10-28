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
    or "---------"
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


def generate_progress_bar(current, total, bar_length=10):
  if total <= 0:
    return ""
  percentage = (current / total) * 100
  filled_length = int(round(bar_length * current / float(total)))
  bar = "█" * filled_length + "▒" * (bar_length - filled_length)
  return f"{bar} {percentage:.1f}%"


def resolve_archive_url(url):
  """Resolves Archive.org's 302 redirect to the direct storage server URL."""
  try:
    req = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
      return response.url
  except Exception as e:
    print(f"⚠️ Could not pre-resolve redirect, using original URL: {e}")
    return url


def get_authenticated_client():
  """Reuses an existing Bluesky session if available."""
  client = Client()

  if os.path.exists(SESSION_FILE):
    try:
      with open(SESSION_FILE, "r") as f:
        session_str = f.read().strip()
      if session_str:
        print("🔑 Resuming saved Bluesky session...")
        client.login(session_string=session_str)
        with open(SESSION_FILE, "w") as f:
          f.write(client.export_session_string())
        return client
    except Exception as e:
      print(f"⚠️ Saved session expired or invalid ({e}), logging in fresh...")

  print("🔐 Performing fresh login with App Password...")
  client.login(HANDLE, APP_PASSWORD)
  with open(SESSION_FILE, "w") as f:
    f.write(client.export_session_string())
  return client


def main():
  print(f"🚀 Execution started at {datetime.now().strftime('%H:%M:%S')}")
  current_frame = get_current_frame_index()
  print(f"🎬 Target index: Frame {current_frame}")

  print("🌐 Resolving Internet Archive stream URL...")
  stream_url = resolve_archive_url(ARCHIVE_VIDEO_URL)
  print(f"🔗 Direct stream endpoint: {stream_url}")

  cap = None
  for attempt in range(1, 4):
    cap = cv2.VideoCapture(stream_url)
    if cap.isOpened():
      break
    print(f"⏳ Connection attempt {attempt} failed, retrying in 3 seconds...")
    time.sleep(3)

  if not cap or not cap.isOpened():
    print(
        "❌ ERROR: Could not open the Archive.org video stream URL directly."
    )
    sys.exit(1)

  total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
  print(f"📊 Video stream parsed successfully. Total frames: {total_frames:,}")

  if total_frames <= 0:
    print("❌ ERROR: Video metadata returned an empty stream layout.")
    cap.release()
    sys.exit(1)

  if current_frame >= total_frames:
    print("🎉 Finished all frames in the video!")
    cap.release()
    return

  cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
  ret, frame = cap.read()
  cap.release()

  if not ret or frame is None:
    print(
        f"❌ ERROR: Failed to extract frame {current_frame} from the network"
        " stream."
    )
    sys.exit(1)

  cv2.imwrite(TEMP_IMG, frame, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])

  file_size = os.path.getsize(TEMP_IMG)
  scale_factor = 0.90
  while file_size > MAX_BYTES:
    orig_height, orig_width = frame.shape[0], frame.shape[1]
    width = int(orig_width * scale_factor)
    height = int(orig_height * scale_factor)
    if width < 100 or height < 100:
      break
    frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    cv2.imwrite(TEMP_IMG, frame, [int(cv2.IMWRITE_PNG_COMPRESSION), 4])
    file_size = os.path.getsize(TEMP_IMG)

  try:
    progress_bar = generate_progress_bar(current_frame, total_frames)
    status_text = f"Frame {current_frame:,} of {total_frames:,}\n{progress_bar}"

    with open(TEMP_IMG, "rb") as f:
      img_data = f.read()

    for attempt in range(1, 4):
      try:
        client = get_authenticated_client()
        client.send_image(
            text=status_text, image=img_data, image_alt=f"Frame {current_frame}"
        )
        print(f"🎯 SUCCESS: Posted frame {current_frame} to Bluesky.")
        save_current_frame_index(current_frame + 1)
        break
      except AtProtocolError as bsky_err:
        print(f"⚠️ Bluesky API Error (Attempt {attempt}/3): {bsky_err}")
        if os.path.exists(SESSION_FILE):
          os.remove(SESSION_FILE)
        if attempt == 3:
          raise
        wait_seconds = 15 * attempt
        print(f"⏳ Waiting {wait_seconds} seconds before retry...")
        time.sleep(wait_seconds)

  except Exception as e:
    print(f"❌ Error occurred: {e}")
    sys.exit(1)

  finally:
    if os.path.exists(TEMP_IMG):
      os.remove(TEMP_IMG)


if __name__ == "__main__":
  main()
