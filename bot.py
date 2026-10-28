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
        except Exception as exc:
            print(
                "⚠️ Saved session could not be resumed; trying a fresh login: "
                f"{exc}"
            )

    if not APP_PASSWORD:
        raise RuntimeError(
            "Bluesky app password is missing. Set the BLUESKY_APP_PASSWORD "
            "or BSKY_PASSWORD environment variable."
        )

    print("🔐 Performing fresh login with Bluesky App Password...")
    client.login(HANDLE, APP_PASSWORD)
    with open(SESSION_FILE, "w", encoding="utf-8") as session_file:
        session_file.write(client.export_session_string())
    return client


def main():
    print(f"🚀 Execution started at {datetime.now().strftime('%H:%M:%S')}")

    if not APP_PASSWORD and not os.path.exists(SESSION_FILE):
        print(
            "❌ ERROR: Bluesky app password is not configured. Set the "
            "BLUESKY_APP_PASSWORD or BSKY_PASSWORD environment variable."
        )
        sys.exit(1)

    try:
        current_frame = get_current_frame_index()
    except (OSError, ValueError) as exc:
        print(f"❌ ERROR: Could not read the frame counter: {exc}")
        sys.exit(1)

    print(f"🎬 Target index: Frame {current_frame}")
    print("🌐 Resolving Internet Archive stream URL...")
    stream_url = resolve_archive_url(ARCHIVE_VIDEO_URL)
    print(f"🔗 Stream endpoint: {stream_url}")

    cap = None
    for attempt in range(1, 4):
        if cap is not None:
            cap.release()

        cap = cv2.VideoCapture(stream_url)
        if cap.isOpened():
            break

        print(f"⏳ Video connection attempt {attempt}/3 failed.")
        time.sleep(3)

    if cap is None or not cap.isOpened():
        if cap is not None:
            cap.release()
        print("❌ ERROR: Could not open the Internet Archive video stream.")
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"📊 Video stream parsed. Total frames reported: {total_frames:,}")

    if total_frames <= 0:
        cap.release()
        print(
            "❌ ERROR: OpenCV reported no frames. The remote stream may not "
            "support frame seeking or may be temporarily unavailable."
        )
        sys.exit(1)

    if current_frame >= total_frames:
        print("🎉 Finished all frames in the video!")
        cap.release()
        return

    # Seek directly to the requested frame in the remote video.
    cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None:
        print(f"❌ ERROR: Failed to extract frame {current_frame} from the stream.")
        sys.exit(1)

    try:
        write_ok = cv2.imwrite(
            TEMP_IMG,
            frame,
            [int(cv2.IMWRITE_PNG_COMPRESSION), 3],
        )
        if not write_ok:
            raise RuntimeError("OpenCV could not write the extracted frame.")

        # Reduce image dimensions until the PNG is below the target upload size.
        file_size = os.path.getsize(TEMP_IMG)
        while file_size > MAX_BYTES:
            orig_height, orig_width = frame.shape[:2]
            width = int(orig_width * 0.90)
            height = int(orig_height * 0.90)

            if width < 100 or height < 100:
                raise RuntimeError(
                    f"Frame image remains too large ({file_size:,} bytes) "
                    f"to upload under the {MAX_BYTES:,}-byte limit."
                )

            frame = cv2.resize(
                frame,
                (width, height),
                interpolation=cv2.INTER_AREA,
            )
            write_ok = cv2.imwrite(
                TEMP_IMG,
                frame,
                [int(cv2.IMWRITE_PNG_COMPRESSION), 4],
            )
            if not write_ok:
                raise RuntimeError("OpenCV could not write the resized frame.")

            file_size = os.path.getsize(TEMP_IMG)

        progress_bar = generate_progress_bar(current_frame, total_frames)
        status_text = f"Frame {current_frame:,} of {total_frames:,}\n{progress_bar}"

        with open(TEMP_IMG, "rb") as image_file:
            image_data = image_file.read()

        # Retry API errors, but do not delete the saved session for every error:
        # a temporary server/network failure does not necessarily mean it is bad.
        for attempt in range(1, 4):
            try:
                client = get_authenticated_client()
                client.send_image(
                    text=status_text,
                    image=image_data,
                    image_alt=f"Frame {current_frame}",
                )
                print(f"🎯 SUCCESS: Posted frame {current_frame} to Bluesky.")
                save_current_frame_index(current_frame + 1)
                break
            except AtProtocolError as exc:
                print(f"⚠️ Bluesky API error (attempt {attempt}/3): {exc}")
                if attempt == 3:
                    raise
                wait_seconds = 15 * attempt
                print(f"⏳ Waiting {wait_seconds} seconds before retrying...")
                time.sleep(wait_seconds)

    except Exception as exc:
        print(f"❌ Error occurred: {exc}")
        sys.exit(1)
    finally:
        if os.path.exists(TEMP_IMG):
            try:
                os.remove(TEMP_IMG)
            except OSError as exc:
                print(f"⚠️ Could not remove temporary image: {exc}")


if __name__ == "__main__":
    main()
