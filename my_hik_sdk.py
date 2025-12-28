"""
Minimalist wrapper for Hikvision MVS SDK.
Directly calls functions from MvCameraControl.dll using ctypes.
"""
import sys
import ctypes
from ctypes import *

# 1. Load the core DLL using an absolute path
# IMPORTANT: Update this path to match your actual DLL location
_DLL_ABSOLUTE_PATH = r"C:\Program Files (x86)\Common Files\MVS\Runtime\Win64_x64\MvCameraControl.dll"
try:
    _mv_dll = WinDLL(_DLL_ABSOLUTE_PATH)
except Exception as e:
    print(f"ERROR: Failed to load DLL from {_DLL_ABSOLUTE_PATH}")
    print(f"Exception: {e}")
    sys.exit(1)

# 2. Define essential C structures (simplified from SDK header)
class MV_CC_DEVICE_INFO(Structure):
    """Corresponds to MV_CC_DEVICE_INFO in the SDK."""
    _fields_ = [
        ("nMajorVer", c_ushort),
        ("nMinorVer", c_ushort),
        ("nMacAddrHigh", c_uint),
        ("nMacAddrLow", c_uint),
        ("nTLayerType", c_uint),  # Device type: GigE, USB, etc.
        ("nReserved", c_uint * 4),
        ("SpecialInfo", c_ubyte * 24)  # Union for GigE/USB specific info
    ]

class MV_CC_DEVICE_INFO_LIST(Structure):
    """Corresponds to MV_CC_DEVICE_INFO_LIST in the SDK."""
    _fields_ = [
        ("nDeviceNum", c_uint),          # Number of discovered devices
        ("pDeviceInfo", POINTER(MV_CC_DEVICE_INFO))  # Pointer to array of device info
    ]

# 3. Define function prototypes (CRITICAL for correct argument passing)
# Enumeration function
_mv_dll.MV_CC_EnumDevices.argtypes = [c_uint, POINTER(MV_CC_DEVICE_INFO_LIST)]
_mv_dll.MV_CC_EnumDevices.restype = c_int

# Device handle creation
_mv_dll.MV_CC_CreateHandle.argtypes = [POINTER(c_void_p), POINTER(MV_CC_DEVICE_INFO)]
_mv_dll.MV_CC_CreateHandle.restype = c_int

# Device opening
_mv_dll.MV_CC_OpenDevice.argtypes = [c_void_p, c_uint, c_ushort]
_mv_dll.MV_CC_OpenDevice.restype = c_int

# Parameter setting (for AcquisitionMode, FrameRate, etc.)
# Note: The exact function signature may vary. This is for string-enum parameters.
_mv_dll.MV_CC_SetEnumValue.argtypes = [c_void_p, c_char_p, c_uint]
_mv_dll.MV_CC_SetEnumValue.restype = c_int

# Boolean parameter setting (for features like AcquisitionFrameRateEnable)
_mv_dll.MV_CC_SetBoolValue.argtypes = [c_void_p, c_char_p, c_bool]
_mv_dll.MV_CC_SetBoolValue.restype = c_int

# Float parameter setting (for exposure time, frame rate value, etc.)
_mv_dll.MV_CC_SetFloatValue.argtypes = [c_void_p, c_char_p, c_float]
_mv_dll.MV_CC_SetFloatValue.restype = c_int

# Start image acquisition
_mv_dll.MV_CC_StartGrabbing.argtypes = [c_void_p]
_mv_dll.MV_CC_StartGrabbing.restype = c_int

# Get one frame with timeout
_mv_dll.MV_CC_GetOneFrameTimeout.argtypes = [c_void_p, c_void_p, c_uint, c_uint]
_mv_dll.MV_CC_GetOneFrameTimeout.restype = c_int

# Stop image acquisition
_mv_dll.MV_CC_StopGrabbing.argtypes = [c_void_p]
_mv_dll.MV_CC_StopGrabbing.restype = c_int

# Close device and destroy handle
_mv_dll.MV_CC_CloseDevice.argtypes = [c_void_p]
_mv_dll.MV_CC_CloseDevice.restype = c_int

_mv_dll.MV_CC_DestroyHandle.argtypes = [c_void_p]
_mv_dll.MV_CC_DestroyHandle.restype = c_int

# Optional: SDK version query (useful for debugging)
_mv_dll.MV_CC_GetSDKVersion.argtypes = []
_mv_dll.MV_CC_GetSDKVersion.restype = c_uint

# 4. User-friendly Python wrapper functions
def enum_devices(nTLayerType=4 | 8):
    """
    Enumerate available cameras.
    
    Args:
        nTLayerType: Bitwise combination of device types.
                     Default is MV_GIGE_DEVICE (4) | MV_USB_DEVICE (8).
    
    Returns:
        tuple: (error_code, device_list_structure)
               error_code == 0 means success.
    """
    device_list = MV_CC_DEVICE_INFO_LIST()
    ret = _mv_dll.MV_CC_EnumDevices(nTLayerType, byref(device_list))
    return ret, device_list

def create_handle(device_info):
    """
    Create a device handle for communication.
    
    Args:
        device_info: An MV_CC_DEVICE_INFO instance for the target camera.
    
    Returns:
        tuple: (error_code, device_handle)
               error_code == 0 means success.
    """
    handle = c_void_p()
    # Note: byref() is used to pass a pointer to the device_info struct
    ret = _mv_dll.MV_CC_CreateHandle(byref(handle), byref(device_info))
    return ret, handle

def open_device(handle, access_mode=1, switch_key=0):
    """
    Open a camera device for exclusive control.
    
    Args:
        handle: Device handle from create_handle().
        access_mode: 1 for exclusive access (MV_ACCESS_Exclusive).
        switch_key: Reserved, usually 0.
    
    Returns:
        int: Error code (0 for success).
    """
    ret = _mv_dll.MV_CC_OpenDevice(handle, access_mode, switch_key)
    return ret

def set_enum_value(handle, param_name, param_value):
    """
    Set an enumeration parameter (e.g., AcquisitionMode).
    
    Args:
        handle: Device handle.
        param_name: Parameter name as a string (e.g., b"AcquisitionMode").
        param_value: Integer value of the enum.
    
    Returns:
        int: Error code (0 for success).
    """
    # Convert string to bytes (C-style char*)
    param_name_bytes = param_name.encode('utf-8') if isinstance(param_name, str) else param_name
    ret = _mv_dll.MV_CC_SetEnumValue(handle, param_name_bytes, param_value)
    return ret

def set_bool_value(handle, param_name, param_value):
    """
    Set a boolean parameter.
    
    Args:
        handle: Device handle.
        param_name: Parameter name as a string (e.g., b"AcquisitionFrameRateEnable").
        param_value: Boolean value.
    
    Returns:
        int: Error code (0 for success).
    """
    param_name_bytes = param_name.encode('utf-8') if isinstance(param_name, str) else param_name
    ret = _mv_dll.MV_CC_SetBoolValue(handle, param_name_bytes, param_value)
    return ret

def set_float_value(handle, param_name, param_value):
    """
    Set a float parameter (e.g., exposure time, frame rate).
    
    Args:
        handle: Device handle.
        param_name: Parameter name as a string (e.g., b"AcquisitionFrameRate").
        param_value: Float value.
    
    Returns:
        int: Error code (0 for success).
    """
    param_name_bytes = param_name.encode('utf-8') if isinstance(param_name, str) else param_name
    ret = _mv_dll.MV_CC_SetFloatValue(handle, param_name_bytes, c_float(param_value))
    return ret

def start_grabbing(handle):
    """
    Start continuous image acquisition.
    
    Args:
        handle: Device handle.
    
    Returns:
        int: Error code (0 for success).
    """
    ret = _mv_dll.MV_CC_StartGrabbing(handle)
    return ret

def get_one_frame_timeout(handle, data_buffer, data_size, timeout_ms=1000):
    """
    Retrieve a single image frame.
    
    Args:
        handle: Device handle.
        data_buffer: Pre-allocated buffer (ctypes array) to hold image data.
        data_size: Size of the buffer.
        timeout_ms: Timeout in milliseconds.
    
    Returns:
        tuple: (error_code, frame_info_structure)
    """
    # Note: This function requires a proper MV_FRAME_OUT_INFO_EX structure.
    # For simplicity, we pass a void pointer and size.
    # In a full implementation, you would define MV_FRAME_OUT_INFO_EX.
    frame_info = c_uint * 8  # Placeholder for frame info
    ret = _mv_dll.MV_CC_GetOneFrameTimeout(handle, data_buffer, data_size, frame_info, timeout_ms)
    return ret, frame_info

def stop_grabbing(handle):
    """
    Stop image acquisition.
    
    Args:
        handle: Device handle.
    
    Returns:
        int: Error code (0 for success).
    """
    ret = _mv_dll.MV_CC_StopGrabbing(handle)
    return ret

def close_device(handle):
    """
    Close the device connection.
    
    Args:
        handle: Device handle.
    
    Returns:
        int: Error code (0 for success).
    """
    ret = _mv_dll.MV_CC_CloseDevice(handle)
    return ret

def destroy_handle(handle):
    """
    Destroy the device handle and free resources.
    
    Args:
        handle: Device handle.
    
    Returns:
        int: Error code (0 for success).
    """
    ret = _mv_dll.MV_CC_DestroyHandle(handle)
    return ret

def get_sdk_version():
    """
    Query the SDK version number.
    
    Returns:
        int: SDK version (hexadecimal, e.g., 0x04070000 for V4.7.0).
    """
    return _mv_dll.MV_CC_GetSDKVersion()

# 5. Simple test when run directly
if __name__ == "__main__":
    print("Testing Hikvision SDK wrapper...")
    version = get_sdk_version()
    print(f"SDK Version: 0x{version:08X}")
    
    ret, devices = enum_devices()
    if ret == 0:
        print(f"Device enumeration successful. Found {devices.nDeviceNum} device(s).")
    else:
        print(f"Device enumeration failed with error code: {ret}")