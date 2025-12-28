#!/usr/bin/env python3
"""
Hikvision USB Camera Synchronized Capture System
Real SDK version - Requires Hikvision MVS and Python interface
"""

import os
import sys
import platform
import time
import threading
from datetime import datetime
from PIL import Image
import numpy as np
from ctypes import cast, POINTER, c_ubyte, string_at

# Import real Hikvision SDK
currentsystem = platform.system()
if currentsystem == 'Windows':
    # Try to get MVCAM_COMMON_RUNENV environment variable for SDK path
    common_env = os.getenv('MVCAM_COMMON_RUNENV')
    if common_env:
        mv_import_path = os.path.join(common_env, "Samples", "Python", "MvImport")
        sys.path.append(mv_import_path)
    else:
        sys.path.append('./MvImport')  # Default path if environment variable is not set
else:
    # For non-Windows systems, use a relative path
    sys.path.append(os.path.join("..", "..", "MvImport"))

# Now, import the SDK
try:
    from MvCameraControl_class import *  # Correct import for SDK classes
    print("Successfully imported Hikvision MVSDK")
except ImportError as e:
    print(f"Failed to import MVSDK: {e}")
    print("Please ensure:")
    print("1. Hikvision MVS is installed")
    print("2. MvImport.py is in Python path")
    print("3. Required runtime libraries are installed")
    sys.exit(1)


class HikUSBSyncController:
    """Hikvision USB Camera Synchronized Controller"""
    
    def __init__(self, base_save_path="./sync_capture"):
        """
        Initialize the controller
        
        Args:
            base_save_path: Base directory for saving captured images
        """
        self.cameras = {}  # Dictionary to store camera objects
        self.base_save_path = base_save_path
        self.is_running = False
        self.frame_counter = 0
        self.sync_lock = threading.Lock()
        
        # 延迟补偿配置：为每台相机设置特定的延迟
        self.delay_compensation = {
            0: 0,      # Camera 0: 无补偿
            1: 0,    # Camera 1: 增加150ms延迟（因为它的响应最快）
            2: 0,      # Camera 2: 无补偿
            3: 0       # Camera 3: 无补偿
        }
        
        # 统计每台相机的平均延迟
        self.camera_delay_stats = {}
        
        # Create base directory
        os.makedirs(base_save_path, exist_ok=True)
        print(f"Save directory created: {base_save_path}")
    
    def _capture_thread_function(self, camera_id, frame_number, timestamp_str, results_dict):
        """Thread function for camera capture"""
        success, delay, filename = self.trigger_single_camera(
            camera_id, frame_number, timestamp_str
        )
    
        if success:
            # 更新延迟统计
            if camera_id not in self.camera_delay_stats:
                self.camera_delay_stats[camera_id] = []
            self.camera_delay_stats[camera_id].append(delay)
            
            # 显示应用了补偿的延迟
            compensation = self.delay_compensation.get(camera_id, 0)
            actual_delay = delay + compensation
            print(f"  Camera {camera_id}: ✓ {filename} (delay: {delay:.1f}ms + {compensation}ms comp = {actual_delay:.1f}ms)")
        else:
            print(f"  Camera {camera_id}: ✗ Capture failed")
    
        results_dict[camera_id] = (success, delay, filename)

    def detect_usb_cameras(self):
        """
        Detect all connected USB cameras
        
        Returns:
            int: Number of detected cameras
        """
        try:
            # Create device list
            device_list = MV_CC_DEVICE_INFO_LIST()
            
            # Enumerate USB devices
            ret = MvCamera.MV_CC_EnumDevices(MV_USB_DEVICE, device_list)
            
            if ret != 0:
                print(f"Device enumeration failed with error code: {ret}")
                return 0
            
            num_devices = device_list.nDeviceNum
            print(f"Detected {num_devices} USB camera(s)")
            
            # Display device information
            for i in range(num_devices):
                device_info = device_list.pDeviceInfo[i]
                if hasattr(device_info, 'SpecialInfo'):
                    model = device_info.SpecialInfo.stUsb3VInfo.chModelName
                    serial = device_info.SpecialInfo.stUsb3VInfo.chSerialNumber
                    print(f"  Camera {i}: Model={model.decode('utf-8')}, "
                          f"Serial={serial.decode('utf-8')}")
            
            return num_devices
            
        except Exception as e:
            print(f"Error detecting cameras: {e}")
            return 0
    
    def connect_camera(self, camera_index):
        """
        Connect to a specific USB camera
    
        Args:
            camera_index: Index of the camera to connect
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Create device list
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_USB_DEVICE, device_list)
        
            if ret != 0 or camera_index >= device_list.nDeviceNum:
                print(f"Cannot find camera with index {camera_index}")
                return False
        
            # Create camera instance
            camera = MvCamera()
        
            # Correct way to create device handle: Use the MV_CC_DEVICE_INFO structure
            stDeviceList = cast(device_list.pDeviceInfo[camera_index], POINTER(MV_CC_DEVICE_INFO)).contents
            ret = camera.MV_CC_CreateHandle(stDeviceList)  # Corrected handle creation

            if ret != 0:
                print(f"Failed to create handle for camera {camera_index}, error: {ret}")
                return False
        
            # Open device
            ret = camera.MV_CC_OpenDevice()
            if ret != 0:
                print(f"Failed to open camera {camera_index}, error: {ret}")
                camera.MV_CC_DestroyHandle()
                return False
        
            # Configure camera for software trigger mode
            self._configure_camera(camera)
        
            # Start image grabbing
            ret = camera.MV_CC_StartGrabbing()
            if ret != 0:
                print(f"Failed to start grabbing for camera {camera_index}, error: {ret}")
                camera.MV_CC_CloseDevice()
                camera.MV_CC_DestroyHandle()
                return False
        
            # Create camera-specific save directory
            camera_save_dir = os.path.join(self.base_save_path, f"camera_{camera_index}")
            os.makedirs(camera_save_dir, exist_ok=True)
        
            # Store camera object
            self.cameras[camera_index] = {
                'handle': camera,
                'save_dir': camera_save_dir,
                'connected': True,
                'last_capture': None,
                'serial': self._get_camera_serial(camera)
            }
        
            print(f"Camera {camera_index} connected successfully. Serial: {self.cameras[camera_index]['serial']}")
        
            return True
        
        except Exception as e:
            print(f"Error connecting to camera {camera_index}: {e}")
            return False
    
    def _get_camera_serial(self, camera):
        """Get camera serial number"""
        try:
            serial_value = MVCC_STRINGVALUE()
            ret = camera.MV_CC_GetStringValue("DeviceSerialNumber", serial_value)
            
            if ret == 0:
                return serial_value.chCurValue.decode('utf-8', errors='ignore')
        except:
            pass
        return "Unknown"
    
    def _configure_camera(self, camera):
        """
        Configure camera parameters for synchronized capture
        
        Args:
            camera: Camera instance to configure
        """
        try:
            # Set trigger mode to ON
            ret = camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_ON)
            if ret != 0:
                print(f"Warning: Failed to set trigger mode, error: {ret}")
            
            # Set trigger source to Software
            ret = camera.MV_CC_SetEnumValue("TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE)
            if ret != 0:
                print(f"Warning: Failed to set trigger source, error: {ret}")
            
            # Set acquisition mode to Continuous
            ret = camera.MV_CC_SetEnumValue("AcquisitionMode", MV_ACQ_MODE_CONTINUOUS)
            if ret != 0:
                print(f"Warning: Failed to set acquisition mode, error: {ret}")
            
            # Set exposure time (adjust based on requirements)
            ret = camera.MV_CC_SetFloatValue("ExposureTime", 5000.0)  # 10ms
            if ret != 0:
                print(f"Warning: Failed to set exposure time, error: {ret}")
            
            # Set frame rate (optional)
            ret = camera.MV_CC_SetFloatValue("AcquisitionFrameRate", 30.0)
            if ret != 0:
                print(f"Warning: Failed to set frame rate, error: {ret}")
                
        except Exception as e:
            print(f"Error configuring camera: {e}")
    
    def connect_all_cameras(self, max_cameras=4):
        """
        Connect to all available cameras
        
        Args:
            max_cameras: Maximum number of cameras to connect
            
        Returns:
            int: Number of successfully connected cameras
        """
        num_detected = self.detect_usb_cameras()
        if num_detected == 0:
            print("No cameras detected. Please check USB connections.")
            return 0
        
        connected_count = 0
        max_to_connect = min(num_detected, max_cameras)
        
        print(f"Attempting to connect {max_to_connect} camera(s)...")
        
        for i in range(max_to_connect):
            if self.connect_camera(i):
                connected_count += 1
        
        print(f"Successfully connected {connected_count} out of {max_to_connect} camera(s)")
        
        # 初始化延迟统计
        for cam_id in self.cameras.keys():
            self.camera_delay_stats[cam_id] = []
            
        return connected_count
    
    def trigger_single_camera(self, camera_id, frame_number, timestamp_str):
        """
        Trigger single camera capture
        
        Args:
            camera_id: ID of the camera to trigger
            frame_number: Current frame number
            timestamp_str: Timestamp string for filename
            
        Returns:
            tuple: (success_status, delay_ms, filename)
        """
        try:
            camera_info = self.cameras[camera_id]
            camera = camera_info['handle']
            
            # Generate filename
            filename = f"frame_{frame_number:06d}_{timestamp_str}.png"
            filepath = os.path.join(camera_info['save_dir'], filename)
            
            # Record trigger start time
            trigger_start = datetime.now()
            
            # 应用延迟补偿
            compensation = self.delay_compensation.get(camera_id, 0)
            if compensation > 0:
                time.sleep(compensation / 1000.0)  # 转换为秒
            
            # Send software trigger command
            ret = camera.MV_CC_SetCommandValue("TriggerSoftware")
            if ret != 0:
                print(f"  Camera {camera_id}: ✗ Software trigger failed, error: {ret}")
                return False, 0, ""
            
            # Get image buffer
            frame_data = MV_FRAME_OUT()
            
            # Timeout set to 1000ms (1 second)
            ret = camera.MV_CC_GetImageBuffer(frame_data, 1000)
            if ret != 0:
                print(f"  Camera {camera_id}: ✗ Get image buffer failed, error: {ret}")
                return False, 0, ""
            
            # Check if image data is valid
            if not frame_data.pBufAddr:
                print(f"  Camera {camera_id}: ✗ No image data received")
                camera.MV_CC_FreeImageBuffer(frame_data)
                return False, 0, ""
            
            # Get actual data size
            data_size = frame_data.stFrameInfo.nFrameLen
            if data_size <= 8:  # If data size is too small (like 8 bytes)
                print(f"  Camera {camera_id}: ✗ Invalid image data size: {data_size} bytes")
                camera.MV_CC_FreeImageBuffer(frame_data)
                return False, 0, ""
            
            # Save image to file
            save_success = self._save_image_data(camera, frame_data, filepath)
            
            # Release image buffer
            camera.MV_CC_FreeImageBuffer(frame_data)
            
            # Calculate delay (包括补偿时间)
            capture_end = datetime.now()
            total_delay = (capture_end - trigger_start).total_seconds() * 1000
            
            if save_success:
                camera_info['last_capture'] = capture_end
                return True, total_delay, filename
            else:
                return False, 0, ""
                
        except Exception as e:
            print(f"  Camera {camera_id}: ✗ Capture error: {e}")
            return False, 0, ""
    
    def _save_image_data(self, camera, frame_data, filepath):
        """
        Save image data to file as PNG format
    
        Args:
            camera: Camera instance
            frame_data: Frame data structure from SDK
            filepath: Path to save the image
        
        Returns:
            bool: True if save successful
        """
        try:
            # Get image width, height, and pixel format
            width = frame_data.stFrameInfo.nWidth
            height = frame_data.stFrameInfo.nHeight
            pixel_format = frame_data.stFrameInfo.enPixelType
            data_size = frame_data.stFrameInfo.nFrameLen
            
            # 直接使用原始数据（不进行像素转换）
            # 使用ctypes的string_at来从指针读取数据
            image_data = string_at(frame_data.pBufAddr, data_size)
            
            # Check data size matches expected size
            expected_size_mono8 = width * height
            
            if pixel_format == 17301505:  # MONO8 format
                if data_size != expected_size_mono8:
                    print(f"  Warning: MONO8 data size mismatch. "
                          f"Expected: {expected_size_mono8}, Actual: {data_size}")
                
                # Convert to numpy array and reshape
                image_array = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width))
                image = Image.fromarray(image_array, mode='L')
                
            elif pixel_format == 24:  # RGB format
                expected_size_rgb = width * height * 3
                if data_size != expected_size_rgb:
                    print(f"  Warning: RGB data size mismatch. "
                          f"Expected: {expected_size_rgb}, Actual: {data_size}")
                
                image_array = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width, 3))
                image = Image.fromarray(image_array, mode='RGB')
                
            elif pixel_format == 32:  # BGRA format
                image_array = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width, 4))
                image = Image.fromarray(image_array, mode='RGBA')
                
            else:
                print(f"  Unsupported pixel format: {pixel_format}")
                return False

            # Save as PNG with minimal compression
            image.save(filepath, format="PNG", compress_level=0)  # 无压缩以加快保存速度
            return True
            
        except Exception as e:
            print(f"  Error saving image: {e}")
            return False
    
    def synchronized_capture(self):
        """Perform synchronized capture from all cameras"""
        with self.sync_lock:
            self.frame_counter += 1
            trigger_time = datetime.now()
            timestamp_str = trigger_time.strftime("%Y%m%d_%H%M%S_%f")[:-3]
        
            print(f"\n[Frame {self.frame_counter:04d}] Trigger time: "
                f"{trigger_time.strftime('%H:%M:%S.%f')[:-3]}")
        
            results = {}
            threads = []
        
            # Create and start capture threads for each camera
            for camera_id in self.cameras.keys():
                thread = threading.Thread(
                    target=self._capture_thread_function,
                    args=(camera_id, self.frame_counter, timestamp_str, results)
                )
                threads.append(thread)
                thread.start()
        
            # Wait for all threads to complete
            for thread in threads:
                thread.join()
        
            # Print summary
            success_count = sum(1 for result in results.values() if result[0])
            print(f"  Result: {success_count}/{len(self.cameras)} cameras captured successfully")
            
            # 每5帧显示一次延迟统计
            if self.frame_counter % 5 == 0 and success_count == len(self.cameras):
                self._print_delay_stats()
        
            return results
    
    def _print_delay_stats(self):
        """打印延迟统计信息"""
        print("\n  --- Delay Statistics (last 5 frames) ---")
        for camera_id in sorted(self.camera_delay_stats.keys()):
            delays = self.camera_delay_stats[camera_id][-5:]  # 最近5帧
            if delays:
                avg_delay = sum(delays) / len(delays)
                min_delay = min(delays)
                max_delay = max(delays)
                print(f"  Camera {camera_id}: Avg={avg_delay:.1f}ms, Min={min_delay:.1f}ms, Max={max_delay:.1f}ms")

    def start_capture_session(self, capture_interval=1.0, total_frames=None):
        """Start synchronized capture session"""
        # Connect cameras if not already connected
        if not self.cameras:
            connected = self.connect_all_cameras(max_cameras=4)
            if connected == 0:
                print("No cameras connected. Cannot start capture session.")
                return
        
        self.is_running = True
        frames_captured = 0
        
        print("\n" + "="*60)
        print("STARTING SYNCHRONIZED CAPTURE SESSION")
        print("="*60)
        print(f"Number of cameras: {len(self.cameras)}")
        print(f"Capture interval: {capture_interval} seconds")
        print(f"Total frames: {total_frames or 'Unlimited'}")
        print(f"Delay compensation: {self.delay_compensation}")
        print("="*60 + "\n")
        
        try:
            while self.is_running:
                if total_frames and frames_captured >= total_frames:
                    print(f"\nCompleted {total_frames} frames as requested.")
                    break
                
                # Perform synchronized capture
                self.synchronized_capture()
                frames_captured += 1
                
                # Wait for next capture interval
                if frames_captured < (total_frames or float('inf')):
                    time.sleep(capture_interval)
        
        except KeyboardInterrupt:
            print("\nCapture session interrupted by user.")
        except Exception as e:
            print(f"\nError during capture session: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.stop_capture_session()
    
    def stop_capture_session(self):
        """Stop capture session and release resources"""
        self.is_running = False
        
        print("\nStopping capture session and releasing resources...")
        
        # Close all camera connections
        for camera_id, camera_info in self.cameras.items():
            try:
                camera = camera_info['handle']
                camera.MV_CC_StopGrabbing()
                camera.MV_CC_CloseDevice()
                camera.MV_CC_DestroyHandle()
                print(f"  Camera {camera_id}: Resources released")
            except Exception as e:
                print(f"  Camera {camera_id}: Error releasing resources: {e}")
        
        # 打印最终延迟统计
        if self.camera_delay_stats:
            print("\n  --- Final Delay Statistics ---")
            for camera_id in sorted(self.camera_delay_stats.keys()):
                delays = self.camera_delay_stats[camera_id]
                if delays:
                    avg_delay = sum(delays) / len(delays)
                    print(f"  Camera {camera_id}: Average delay = {avg_delay:.1f}ms ({len(delays)} frames)")
        
        self.cameras.clear()
        print("All camera resources released.")
    
    def print_session_summary(self):
        """Print capture session summary"""
        print("\n" + "="*60)
        print("CAPTURE SESSION SUMMARY")
        print("="*60)
        print(f"Total frames captured: {self.frame_counter}")
        print(f"Images saved to: {self.base_save_path}")
        
        if os.path.exists(self.base_save_path):
            print("\nDirectory structure:")
            for camera_dir in sorted(os.listdir(self.base_save_path)):
                cam_path = os.path.join(self.base_save_path, camera_dir)
                if os.path.isdir(cam_path):
                    file_count = len([f for f in os.listdir(cam_path) 
                                    if f.endswith(('.bmp', '.jpg', '.png'))])
                    print(f"  {camera_dir}/ - {file_count} image(s)")


def main():
    """Main function to run synchronized capture"""
    # Create timestamped save directory
    session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    save_directory = f"./sync_capture_{session_timestamp}"
    
    # Create controller instance
    controller = HikUSBSyncController(save_directory)
    
    print("="*60)
    print("HIKVISION USB CAMERA SYNCHRONIZED CAPTURE SYSTEM")
    print("="*60)
    
    try:
        # Start capture session
        # Parameters:
        #   capture_interval: Time between captures (seconds)
        #   total_frames: Total number of frames to capture
        controller.start_capture_session(
            capture_interval=0.5,   # 2 seconds between captures to ensure stability
            total_frames=20         # Capture 10 frames total
        )
        
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Print summary
        controller.print_session_summary()


if __name__ == "__main__":
    main()