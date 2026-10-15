import os
import cv2
import json
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload
import io
from atproto import Client

# --- GOOGLE & BLUESKY CONFIGURATION ---
VIDEO_FILE_ID = "1YEyYl6jgXE9Vb9dG57-QfMDE0tdclfgq"
STATE_FILE_ID = "1W6BL89cWCpTUAQTN9rUCas8EyjMLgj_O"

HANDLE = "malteseshakeframes.bsky.social"
APP_PASSWORD = "dh5h-biq2-7ija-d4s7"

MAX_BYTES = 1_950_000
LOCAL_VIDEO = "temp_video.mp4"
LOCAL_STATE = "temp_frame_counter.txt"
TEMP_IMG = "temp_frame.png"

# --- GOOGLE DRIVE API UTILITIES ---
def get_drive_service():
    SCOPES = ['https://googleapis.com']
    
    # Read raw data directly from GitHub Environment Block
    raw_secret = os.environ.get('GOOGLE_CREDENTIALS_JSON', '{}')
    creds_info = json.loads(raw_secret)
    
    # Force fix multi-line certificate parsing bugs unique to container runners
    if "private_key" in creds_info:
        creds_info["private_key"] = creds_info["private_key"].replace("\\n", "\n").replace("\n", "\n")
        
    creds = service_account.Credentials.from_service_account_info(
        creds_info, 
        scopes=SCOPES
    )
    return build('drive', 'v3', credentials=creds)

def download_file_from_drive(service, file_id, local_path):
    print(f"📥 Downloading file ID {file_id} from Drive...")
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(local_path, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while not done:
        status, done = downloader.next_chunk()
    print("✅ Download complete.")

def upload_file_to_drive(service, file_id, local_path):
    print(f"📤 Updating state file on Google Drive...")
    media = MediaFileUpload(local_path, mimetype='text/plain')
    service.files().update(fileId=file_id, media_body=media).execute()
    print("✅ Drive state updated.")

# --- BOT LOGIC ---
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
    service = get_drive_service()
    
    # Download state tracker and raw video from shared Google Drive
    download_file_from_drive(service, STATE_FILE_ID, LOCAL_STATE)
    download_file_from_drive(service, VIDEO_FILE_ID, LOCAL_VIDEO)
    
    current_frame = get_current_frame_index()
    cap = cv2.VideoCapture(LOCAL_VIDEO)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    
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
        print(f"🎯 SUCCESS: Posted frame {current_frame}.")
        
        # Increment index value locally, then sync up to persistent cloud state
        save_current_frame_index(current_frame + 1)
        upload_file_to_drive(service, STATE_FILE_ID, LOCAL_STATE)

    except Exception as e:
        print(f"❌ Error occurred: {e}")
        
    finally:
        # Erase heavy media assets from memory storage to keep cloud node light
        for path in [LOCAL_VIDEO, LOCAL_STATE, TEMP_IMG]:
            if os.path.exists(path): os.remove(path)

if __name__ == "__main__":
    main()
