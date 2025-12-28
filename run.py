import sys
import time
import os
from datetime import datetime
from ctypes import *
import platform

# ========== 0. SDK Import Setup (Critical) ==========
currentsystem = platform.system()
if currentsystem == 'Windows':
    common_env = os.getenv('MVCAM_COMMON_RUNENV')
    if common_env:
        mv_import_path = os.path.join(common_env, "Samples", "Python", "MvImport")
        sys.path.append(mv_import_path)
    else:
        sys.path.append('./MvImport')
else:
    sys.path.append(os.path.join("..", "..", "MvImport"))

from MvCameraControl_class import *

# ========== 1. User Configuration ==========
# CRITICAL: Set your own base path for saving images!
PARENT_SAVE_PATH = r"D:\CV-NET\Hikivision"  # <<< CHANGE THIS TO YOUR PATH!
SESSION_FOLDER_NAME = datetime.now().strftime("%Y%m%d_%H%M%S")  # e.g., "20231026_143022"
BASE_SAVE_PATH = os.path.join(PARENT_SAVE_PATH, SESSION_FOLDER_NAME)  # Master folder for this run

DESIRED_FPS = 1.0  # Target frame rate (1 frame per second)
CONNECTION_INTERVAL = 2  # Seconds between connecting each camera
START_INTERVAL = 2       # Seconds between starting acquisition for each camera

def ensure_dir(path):
    """Create directory if it does not exist."""
    if not os.path.exists(path):
        os.makedirs(path)
        print(f"Created directory: {path}")
    return path

def main():
    # ========== 2. Initialize SDK ==========
    print("Initializing Hikvision SDK...")
    ret = MvCamera.MV_CC_Initialize()
    if ret != 0:
        print(f"Failed to initialize SDK! Error code: {ret}")
        return
    print("SDK initialized successfully.")

    # ========== 3. Create Master and Sub Directories ==========
    print("\n" + "="*60)
    print("Step 1: Creating folder structure...")
    print("="*60)
    
    # Create master folder for this session
    ensure_dir(BASE_SAVE_PATH)
    print(f"Master folder for this session: {BASE_SAVE_PATH}")
    
    # Create subfolders for each camera
    save_dirs = []
    for i in range(4):
        # Create subfolder: MasterFolder/Camera_01/, etc.
        subfolder_name = f"Camera_{i+1:02d}"  # Format as 01, 02, etc.
        camera_save_path = ensure_dir(os.path.join(BASE_SAVE_PATH, subfolder_name))
        save_dirs.append(camera_save_path)
        print(f"  Images for Camera {i+1} -> {camera_save_path}")

    # ========== 4. Enumerate and Connect 4 Cameras (with interval) ==========
    print("\n" + "="*60)
    print("Step 2: Enumerating and connecting cameras...")
    print("="*60)
    
    deviceList = MV_CC_DEVICE_INFO_LIST()
    ret = MvCamera.MV_CC_EnumDevices(MV_GIGE_DEVICE | MV_USB_DEVICE, deviceList)
    if ret != 0:
        print(f"Enumeration failed. Error code: {ret}")
        MvCamera.MV_CC_Finalize()
        return

    cam_count = deviceList.nDeviceNum
    print(f"Found {cam_count} device(s).")

    if cam_count < 4:
        print(f"Error: Only {cam_count} camera(s) found. 4 are required.")
        MvCamera.MV_CC_Finalize()
        return

    camera_list = []  # Store connected camera objects

    # Connect to each camera with interval
    for i in range(4):
        print(f"\n--- Connecting Camera {i+1} ---")
        cam = MvCamera()
        
        # FIXED: Correctly extract device info structure
        p_device_info = cast(deviceList.pDeviceInfo[i], POINTER(MV_CC_DEVICE_INFO))
        st_device_info = p_device_info.contents
        
        ret = cam.MV_CC_CreateHandle(st_device_info)
        if ret != 0:
            print(f"Camera {i+1}: Failed to create handle. Error: {ret}")
            continue
            
        ret = cam.MV_CC_OpenDevice(MV_ACCESS_Exclusive, 0)
        if ret != 0:
            print(f"Camera {i+1}: Failed to open device. Error: {ret}")
            cam.MV_CC_DestroyHandle()
            continue
            
        camera_list.append(cam)
        print(f"Camera {i+1}: Connected successfully.")
        
        # Wait before connecting next camera (except after the last one)
        if i < 3:
            print(f"Waiting {CONNECTION_INTERVAL} seconds before connecting next camera...")
            time.sleep(CONNECTION_INTERVAL)

    if len(camera_list) != 4:
        print(f"Failed to connect all 4 cameras. Only {len(camera_list)} connected.")
        for cam in camera_list:
            cam.MV_CC_CloseDevice()
            cam.MV_CC_DestroyHandle()
        MvCamera.MV_CC_Finalize()
        return

    # ========== 5. Configure Camera Parameters (1 FPS) ==========
    print("\n" + "="*60)
    print("Step 3: Configuring camera parameters...")
    print("="*60)
    
    for idx, cam in enumerate(camera_list):
        print(f"\nConfiguring Camera {idx+1}:")
        
        # Set to Continuous Acquisition Mode (Typically value is 2)
        ret = cam.MV_CC_SetEnumValue("AcquisitionMode", 2)
        if ret != 0:
            print(f"  Warning: Failed to set AcquisitionMode. Error: {ret}")
        
        # Enable frame rate control
        ret = cam.MV_CC_SetBoolValue("AcquisitionFrameRateEnable", True)
        if ret != 0:
            # Try alternative parameter name
            ret = cam.MV_CC_SetBoolValue("AcquisitionFrameRateEnabled", True)
        
        # Set frame rate to 1 FPS
        ret = cam.MV_CC_SetFloatValue("AcquisitionFrameRate", DESIRED_FPS)
        if ret == 0:
            print(f"  Frame rate set to {DESIRED_FPS} FPS")
        else:
            print(f"  Warning: Could not set frame rate. Error: {ret}")
            print(f"  Camera will use default frame rate.")

    # ========== 6. Start Continuous Acquisition (with interval) ==========
    print("\n" + "="*60)
    print("Step 4: Starting continuous acquisition...")
    print("="*60)
    
    for idx, cam in enumerate(camera_list):
        print(f"\nStarting acquisition for Camera {idx+1}...")
        ret = cam.MV_CC_StartGrabbing()
        if ret != 0:
            print(f"  Failed to start grabbing! Error: {ret}")
        else:
            start_time = datetime.now().strftime("%H:%M:%S")
            print(f"  Continuous acquisition STARTED at {start_time}")
        
        # Wait before starting next camera (except after the last one)
        if idx < 3:
            print(f"  Waiting {START_INTERVAL} seconds before starting next camera...")
            time.sleep(START_INTERVAL)

    # ========== 7. Main Acquisition Loop ==========
    print("\n" + "="*60)
    print("Step 5: Running main acquisition loop")
    print("All 4 cameras are now:")
    print("1. Connected with 2-second intervals")
    print("2. Configured for 1 FPS capture")
    print("3. Started with 2-second intervals")
    print("="*60)
    print("Press Ctrl+C to stop the program and save all images.")
    print("="*60 + "\n")
    
    frame_count = [0, 0, 0, 0]
    last_capture_time = [0.0, 0.0, 0.0, 0.0]
    
    try:
        while True:
            current_time = time.time()
            
            for idx, cam in enumerate(camera_list):
                # Check if it's time to capture next frame (for 1 FPS)
                if current_time - last_capture_time[idx] >= (1.0 / DESIRED_FPS):
                    # Prepare structures for image data - FIXED VERSION
                    stFrameInfo = MV_FRAME_OUT_INFO_EX()
                    
                    # Allocate buffer (adjust size based on your camera resolution)
                    max_buffer_size = 4096 * 4096 * 3
                    data_buf = (c_ubyte * max_buffer_size)()
                    
                    # Get one frame with timeout - CORRECT PARAMETER ORDER
                    #(pData, nDataSize, pFrameInfo, nMsec)
                    ret = cam.MV_CC_GetOneFrameTimeout(data_buf, max_buffer_size, stFrameInfo, 1500)
                    
                    if ret == 0:
                        last_capture_time[idx] = current_time
                        frame_count[idx] += 1
                        
                        # Generate filename with timestamp
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
                        filename = f"Cam{idx+1}_{timestamp}_Frame{frame_count[idx]}.raw"
                        # CRITICAL FIX: Use the correct camera-specific directory
                        filepath = os.path.join(save_dirs[idx], filename)
                        
                        # Save only the actual image data (not the entire buffer)
                        try:
                            # Use the actual frame length returned in stFrameInfo
                            img_bytes = bytes(data_buf[:stFrameInfo.nFrameLen])
                            with open(filepath, 'wb') as f:
                                f.write(img_bytes)
                            
                            # Print status every 10 frames
                            if frame_count[idx] % 10 == 0:
                                print(f"Camera {idx+1}: Saved {frame_count[idx]} frames (latest: {filename})")
                        except Exception as e:
                            print(f"Camera {idx+1}: Failed to save image. Error: {e}")
            
            # Small sleep to prevent high CPU usage
            time.sleep(0.001)
            
    except KeyboardInterrupt:
        print("\n" + "="*60)
        print("Stopping acquisition...")
        print("="*60)

    # ========== 8. Cleanup Resources ==========
    print("\n" + "="*60)
    print("Step 6: Cleaning up resources...")
    print("="*60)
    
    # Stop grabbing and close all cameras
    for idx, cam in enumerate(camera_list):
        try:
            cam.MV_CC_StopGrabbing()
            cam.MV_CC_CloseDevice()
            cam.MV_CC_DestroyHandle()
            print(f"Camera {idx+1}: Stopped. Total frames: {frame_count[idx]}")
        except Exception as e:
            print(f"Camera {idx+1}: Error during cleanup: {e}")
    
    # Finalize SDK
    print("\nFinalizing SDK...")
    MvCamera.MV_CC_Finalize()
    
    # Print summary
    total_frames = sum(frame_count)
    print("\n" + "="*60)
    print("ACQUISITION SUMMARY")
    print("="*60)
    for idx in range(4):
        print(f"Camera {idx+1}: {frame_count[idx]} frames saved to '{os.path.basename(save_dirs[idx])}'")
    print(f"Total frames from all cameras: {total_frames}")
    print(f"\nAll images are organized in:")
    print(f"Master Folder : {BASE_SAVE_PATH}")
    for idx, save_dir in enumerate(save_dirs):
        print(f"  - Camera {idx+1} : {save_dir}")
    print("="*60)
    print("Program completed successfully.")

if __name__ == "__main__":
    main()
