import os
import cv2
import requests
from datetime import datetime
from atproto import Client

# --- BLUESKY CONFIGURATION ---
HANDLE = "malteseshakeframes.bsky.social"
APP_PASSWORD = "dh5h-biq2-7ija-d4s7"

# Verified Dropbox raw direct download link
VIDEO_URL = "https://dropbox.com"

MAX_BYTES = 1_950_000
LOCAL_VIDEO = "temp_video.mp4"
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
    if total <= 0: return ""
    percentage = (current / total) * 100
    filled_length = int(round(bar_length * current / float(total)))
    bar = '█' * filled_length + '▒' * (bar_length - filled_length)
    return f"{bar} {percentage:.1f}%"

def main():
    print(f"🚀 Execution started at {datetime.now().strftime('%H:%M:%S')}")
    current_frame = get_current_frame_index()
    print(f"🎬 Target index: Frame {current_frame}")
    
    # 1. Chunk download video cleanly from your Dropbox link
    print("📥 Stream downloading video from Dropbox link in 5MB blocks...")
    response = requests.get(VIDEO_URL, stream=True)
    if response.status_code == 200:
        with open(LOCAL_VIDEO, 'wb') as f:
            for chunk in response.iter_content(chunk_size=5*1024*1024):
                if chunk:
                    f.write(chunk)
        print("✅ Video file successfully buffered to container disk.")
    else:
        print(f"❌ Failed to download video. Status code: {response.status_code}")
        return

    # 2. Extract targeted frame locally
    cap = cv2.VideoCapture(LOCAL_VIDEO)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"📊 Video file opened successfully. Total frames: {total_frames:,}")
    
    if current_frame >= total_frames:
        print("🎉 Finished all frames in the video!")
        cap.release()
        return

    cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
    ret, frame = cap.read()
    cap.release()
    
    if not ret or frame is None:
        print(f"❌ ERROR: Failed to extract frame {current_frame}")
        return

    cv2.imwrite(TEMP_IMG, frame, [int(cv2.IMWRITE_PNG_COMPRESSION), 3])

    # Shrinking loop if the picture file size exceeds constraints
    file_size = os.path.getsize(TEMP_IMG)
    scale_factor = 0.90  
    while file_size > MAX_BYTES:
        orig_height, orig_width = frame.shape[0], frame.shape[1]
        width, height = int(orig_width * scale_factor), int(orig_height * scale_factor)
        if width < 100 or height < 100: break
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
            
        client.send_image(text=status_text, image=img_data, image_alt=f"Frame {current_frame}")
        print(f"🎯 SUCCESS: Posted frame {current_frame} to Bluesky.")
        
        # Increment index value and save it locally for the repo update step
        save_current_frame_index(current_frame + 1)

    except Exception as e:
        print(f"❌ Error occurred: {e}")
        
    finally:
        # Keep workspace clean
        if os.path.exists(LOCAL_VIDEO):
            os.remove(LOCAL_VIDEO)
        if os.path.exists(TEMP_IMG):
            os.remove(TEMP_IMG)

if __name__ == "__main__":
    main()
