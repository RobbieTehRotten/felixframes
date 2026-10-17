from datetime import datetime
import os
import time
import urllib.request
from atproto import Client
import cv2

# --- BLUESKY CONFIGURATION ---
HANDLE = "malteseshakeframes.bsky.social"
# Recommended: Store your password in GitHub Secrets as BSKY_PASSWORD, or replace the fallback string below
APP_PASSWORD = os.getenv("BSKY_PASSWORD", "dh5h-biq2-7ija-d4s7")

# --- INTERNET ARCHIVE CONFIGURATION ---
# Replace this with your direct archive.org/download/... link ending in .mp4
ARCHIVE_VIDEO_URL = (
    "https://archive.org/download/Untitledfel/Untitledfel.mp4"
)

MAX_BYTES = 950_000  # Bluesky's strict image blob limit is ~976.56 KB (1,000,000 bytes)
LOCAL_STATE = "frame_counter.txt"
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
  """Archive.org /download/ links redirect (HTTP 302) to a specific storage server

  (e.g., https://ia801234.us.archive.org/...). Resolving the final URL first
  helps OpenCV's FFmpeg backend open and seek the stream without timing out.
  """
  try:
    req = urllib.request.Request(
        url, method="HEAD", headers={"User-Agent": "Mozilla/5.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as response:
      return response.url
  except Exception as e:
    print(f"⚠️ Could not pre-resolve redirect, using original URL: {e}")
    return url


def main():
  print(f"🚀 Execution started at {datetime.now().strftime('%H:%M:%S')}")
  current_frame = get_current_frame_index()
  print(f"🎬 Target index: Frame {current_frame}")

  # Resolve the direct storage server URL from Archive.org
  print("🌐 Resolving Internet Archive stream URL...")
  stream_url = resolve_archive_url(ARCHIVE_VIDEO_URL)
  print(f"🔗 Direct stream endpoint: {stream_url}")

  # Connect OpenCV to the Archive.org stream (with retries for transient network hiccups)
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
    return

  total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
  print(f"📊 Video stream parsed successfully. Total frames: {total_frames:,}")

  if total_frames <= 0:
    print("❌ ERROR: Video metadata returned an empty stream layout.")
    cap.release()
    return

  if current_frame >= total_frames:
    print("🎉 Finished all frames in the video!")
    cap.release()
    return

  # Seek directly to the target frame over the HTTP range stream
  cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
  ret, frame = cap.read()
  cap.release()

  if not ret or frame is None:
    print(
        f"❌ ERROR: Failed to extract frame {current_frame} from the network"
        " stream."
    )
    return

  cv2.imwrite(TEMP_IMG, frame, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])

  # Shrinking loop if the picture file size exceeds Bluesky's limit
  file_size = os.path.getsize(TEMP_IMG)
  scale_factor = 0.90
  while file_size > MAX_BYTES:
    orig_height, orig_width = frame.shape[0], frame.shape[1]
    width, height = int(orig_width * scale_factor), int(
        orig_height * scale_factor
    )
    if width < 100 or height < 100:
      break
    frame = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    cv2.imwrite(TEMP_IMG, frame, [int(cv2.IMWRITE_PNG_COMPRESSION), 4])
    file_size = os.path.getsize(TEMP_IMG)

  try:
    # Establish Bluesky authentication
    client = Client()
    client.login(HANDLE, APP_PASSWORD)
    progress_bar = generate_progress_bar(current_frame, total_frames)
    status_text = f"Frame {current_frame:,} of {total_frames:,}\n{progress_bar}"

    with open(TEMP_IMG, "rb") as f:
      img_data = f.read()

    client.send_image(
        text=status_text, image=img_data, image_alt=f"Frame {current_frame}"
    )
    print(f"🎯 SUCCESS: Posted frame {current_frame} to Bluesky.")

    # Increment index value and save it locally for the repo update step
    save_current_frame_index(current_frame + 1)

  except Exception as e:
    print(f"❌ Error occurred: {e}")

  finally:
    # Keep workspace clean
    if os.path.exists(TEMP_IMG):
      os.remove(TEMP_IMG)


if __name__ == "__main__":
  main()