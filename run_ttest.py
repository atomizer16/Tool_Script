#!/usr/bin/env python3


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
    common_env = os.getenv('MVCAM_COMMON_RUNENV')
    if common_env:
        sys.path.append(os.path.join(common_env, "Samples", "Python", "MvImport"))
    else:
        sys.path.append('./MvImport')
else:
    sys.path.append(os.path.join("..", "..", "MvImport"))

try:
    from MvCameraControl_class import *
    print("✓ Hikvision MVSDK imported")
except ImportError as e:
    print(f"✗ Failed to import MVSDK: {e}")
    sys.exit(1)


class HikUSBSyncController:
    """Hikvision USB Camera Synchronized Controller - Simplified"""
    
    def __init__(self, base_save_path="./sync_capture"):
        self.cameras = {}
        self.base_save_path = base_save_path
        self.is_running = False
        self.frame_counter = 0
        self.sync_lock = threading.Lock()
        self.trigger_log_file = None
        
        os.makedirs(base_save_path, exist_ok=True)
        
        self._setup_trigger_logging()
    
    def _setup_trigger_logging(self):
        try:
            log_file = os.path.join(self.base_save_path, "trigger_times.txt")
            self.trigger_log_file = open(log_file, 'a+', buffering=1)
            
            if self.trigger_log_file.tell() == 0:
                self.trigger_log_file.write(f"# Trigger Time Log - Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                self.trigger_log_file.write("# Frame, UnixTimestamp, HumanTime\n")
            
            print(f"✓ Trigger log: {log_file}")
            
        except Exception as e:
            print(f"✗ Setup trigger log failed: {e}")
            self.trigger_log_file = None

    def _log_trigger_time(self, frame_number, trigger_time):
        if not self.trigger_log_file:
            return
        
        try:
            unix_ts = trigger_time.timestamp()
            human_time = trigger_time.strftime("%H:%M:%S.%f")[:-3]
            self.trigger_log_file.write(f"{frame_number},{unix_ts:.6f},{human_time}\n")
        except:
            pass

    def detect_and_connect_cameras(self, max_cameras=4):
        try:
            device_list = MV_CC_DEVICE_INFO_LIST()
            ret = MvCamera.MV_CC_EnumDevices(MV_USB_DEVICE, device_list)
            
            if ret != 0 or device_list.nDeviceNum == 0:
                print("No USB cameras detected")
                return 0
            
            connected = 0
            max_to_connect = min(device_list.nDeviceNum, max_cameras)
            
            for i in range(max_to_connect):
                if self._connect_single_camera(i, device_list):
                    connected += 1
            
            print(f"✓ Connected {connected} camera(s)")
            return connected
            
        except Exception as e:
            print(f"✗ Camera connection failed: {e}")
            return 0
    
    def _connect_single_camera(self, index, device_list):
        try:
            camera = MvCamera()
            stDeviceList = cast(device_list.pDeviceInfo[index], POINTER(MV_CC_DEVICE_INFO)).contents
            ret = camera.MV_CC_CreateHandle(stDeviceList)
            
            if ret != 0:
                return False
            
            ret = camera.MV_CC_OpenDevice()
            if ret != 0:
                camera.MV_CC_DestroyHandle()
                return False
            
            camera.MV_CC_SetEnumValue("TriggerMode", MV_TRIGGER_MODE_ON)
            camera.MV_CC_SetEnumValue("TriggerSource", MV_TRIGGER_SOURCE_SOFTWARE)
            camera.MV_CC_SetFloatValue("AcquisitionFrameRate", 5.0)
            
            ret = camera.MV_CC_StartGrabbing()
            if ret != 0:
                camera.MV_CC_CloseDevice()
                camera.MV_CC_DestroyHandle()
                return False
            
            cam_dir = os.path.join(self.base_save_path, f"cam{index}")
            os.makedirs(cam_dir, exist_ok=True)
            
            self.cameras[index] = {
                'handle': camera,
                'save_dir': cam_dir
            }
            
            print(f"  Camera {index}: Connected")
            return True
            
        except:
            return False
    
    def _capture_single_camera(self, camera_id, frame_number, timestamp_str, results_dict):
        try:
            camera_info = self.cameras[camera_id]
            camera = camera_info['handle']
            
            filename = f"f{frame_number:04d}_{timestamp_str}.png"
            filepath = os.path.join(camera_info['save_dir'], filename)
            
            ret = camera.MV_CC_SetCommandValue("TriggerSoftware")
            if ret != 0:
                results_dict[camera_id] = (False, "")
                return
            
            frame_data = MV_FRAME_OUT()
            ret = camera.MV_CC_GetImageBuffer(frame_data, 500)
            if ret != 0:
                results_dict[camera_id] = (False, "")
                return
            
            success = self._save_image_fast(camera, frame_data, filepath)
            camera.MV_CC_FreeImageBuffer(frame_data)
            
            if success:
                results_dict[camera_id] = (True, filename)
            else:
                results_dict[camera_id] = (False, "")
                
        except Exception as e:
            print(f"  Cam{camera_id}: Error - {e}")
            results_dict[camera_id] = (False, "")
    
    def _save_image_fast(self, camera, frame_data, filepath):
        try:
            width = frame_data.stFrameInfo.nWidth
            height = frame_data.stFrameInfo.nHeight
            pixel_format = frame_data.stFrameInfo.enPixelType
            
            if pixel_format == 17301505:  # MONO8
                data_size = width * height
                image_data = string_at(frame_data.pBufAddr, data_size)
                image_array = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width))
                image = Image.fromarray(image_array, mode='L')
                
            elif pixel_format == 24:  # RGB
                data_size = width * height * 3
                image_data = string_at(frame_data.pBufAddr, data_size)
                image_array = np.frombuffer(image_data, dtype=np.uint8).reshape((height, width, 3))
                image = Image.fromarray(image_array, mode='RGB')
                
            else:
                return False
            
            image.save(filepath, format="PNG", compress_level=0)
            return True
            
        except:
            return False
    
    def synchronized_capture(self):
        with self.sync_lock:
            self.frame_counter += 1
            trigger_time = datetime.now()
            timestamp_str = trigger_time.strftime("%H%M%S%f")[:-3]
            
            self._log_trigger_time(self.frame_counter, trigger_time)
            
            if self.frame_counter % 10 == 1:  
                print(f"\n[Frame {self.frame_counter:04d}] {trigger_time.strftime('%H:%M:%S.%f')[:-3]}")
            elif self.frame_counter % 2 == 0:  
                print(".", end="", flush=True)
            
            results = {}
            threads = []
            
            for camera_id in self.cameras.keys():
                thread = threading.Thread(
                    target=self._capture_single_camera,
                    args=(camera_id, self.frame_counter, timestamp_str, results)
                )
                threads.append(thread)
                thread.start()
            
            for thread in threads:
                thread.join()
            
            success_count = sum(1 for result in results.values() if result[0])
            if success_count != len(self.cameras):
                print(f"\n⚠️ Frame {self.frame_counter}: {success_count}/{len(self.cameras)} cameras")
            
            return True
    
    def start_stable_capture(self, fps=2.0, total_frames=100):
        if not self.cameras:
            connected = self.detect_and_connect_cameras()
            if connected == 0:
                print("No cameras available")
                return
        
        print(f"\n{'='*50}")
        print(f"Starting {fps}Hz Capture ({total_frames} frames)")
        print(f"Interval: {1.0/fps:.3f}s, Cameras: {len(self.cameras)}")
        print(f"{'='*50}\n")
        
        self.is_running = True
        capture_interval = 1.0 / fps
        
        try:
            start_time = time.time()
            
            for frame in range(1, total_frames + 1):
                if not self.is_running:
                    break
                
                frame_start = time.time()
                
                self.synchronized_capture()
                
                elapsed = time.time() - frame_start
                sleep_time = max(0, capture_interval - elapsed)
                
                if sleep_time > 0 and frame < total_frames:
                    time.sleep(sleep_time)
            
            end_time = time.time()
            total_time = end_time - start_time
            actual_fps = (total_frames - 1) / total_time if total_time > 0 else 0
            
            print(f"\n\n{'='*50}")
            print(f"Capture Complete")
            print(f"Expected FPS: {fps:.1f}")
            print(f"Actual FPS: {actual_fps:.2f}")
            print(f"Total time: {total_time:.2f}s")
            print(f"{'='*50}")
            
        except KeyboardInterrupt:
            print("\n\nCapture interrupted")
        except Exception as e:
            print(f"\nError: {e}")
        finally:
            self._cleanup()
    
    def _cleanup(self):
        self.is_running = False
        
        print("\nCleaning up...")
        
        if self.trigger_log_file:
            try:
                self.trigger_log_file.close()
                print("✓ Trigger log closed")
            except:
                pass
        
        for cam_id, info in self.cameras.items():
            try:
                camera = info['handle']
                camera.MV_CC_StopGrabbing()
                camera.MV_CC_CloseDevice()
                camera.MV_CC_DestroyHandle()
                print(f"  Cam{cam_id}: Closed")
            except:
                pass
        
        self.cameras.clear()
        print("Cleanup complete")
    
    def print_summary(self):
        print(f"\nSummary:")
        print(f"  Frames captured: {self.frame_counter}")
        print(f"  Save location: {self.base_save_path}")
        
        if os.path.exists(self.base_save_path):
            for item in os.listdir(self.base_save_path):
                path = os.path.join(self.base_save_path, item)
                if os.path.isdir(path) and item.startswith('cam'):
                    img_count = len([f for f in os.listdir(path) if f.endswith('.png')])
                    print(f"  {item}: {img_count} images")


def main():
    timestamp = datetime.now().strftime("%m%d_%H%M")
    save_dir = f"./capture_{timestamp}"
    
    print(f"{'='*50}")
    print("Hikvision Sync Capture - Simplified")
    print(f"{'='*50}")
    
    controller = HikUSBSyncController(save_dir)
    
    try:
        FPS = 2.0
        TOTAL_FRAMES = 100
        
        controller.start_stable_capture(
            fps=FPS,
            total_frames=TOTAL_FRAMES
        )
        
    except Exception as e:
        print(f"\nFatal error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        controller.print_summary()


if __name__ == "__main__":
    main()