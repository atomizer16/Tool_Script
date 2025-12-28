import time
import threading
import numpy as np
import cv2
from ctypes import *
from hikvisionapi import Client

# 定义相机数量
NUM_CAMERAS = 4
CAMERA_SNS = ["SN12345678", "SN23456789", "SN34567890", "SN45678901"]  # 使用相机SN码

# 初始化相机客户端
cameras = []

# 连接相机并初始化
def init_cameras():
    global cameras
    for sn in CAMERA_SNS:
        # 创建相机客户端实例
        client = Client(sn)  # 使用SN码进行连接
        cameras.append(client)
        # 连接相机
        client.login("admin", "admin")  # 登录相机，默认用户名密码，需根据你的实际情况修改
        print(f"Connected to camera {sn}")

# 配置每台相机为连续抓图模式
def configure_camera_for_continuous_capture(camera):
    camera.set_video_mode('continuous')  # 设置视频模式为连续抓图模式
    camera.set_trigger_mode('software')  # 设置触发模式为软件触发

# 启动每台相机并抓图
def start_capture(camera, index):
    # 每台相机启动时，间隔2秒启动
    print(f"Starting camera {index + 1} capture...")
    time.sleep(2)  # 延迟2秒启动
    configure_camera_for_continuous_capture(camera)  # 配置相机
    print(f"Camera {index + 1} started capture.")

    # 开始连续抓图
    while True:
        # 获取图像
        frame = camera.get_frame()  # 这需要根据你的SDK实际方法进行修改
        if frame is not None:
            print(f"Camera {index + 1} captured a frame.")
            cv2.imshow(f"Camera {index + 1}", frame)  # 显示图像
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break  # 按q键退出
        else:
            print(f"Camera {index + 1} frame capture failed.")
    print(f"Camera {index + 1} capture stopped.")

# 多线程实现按顺序启动四台相机
def capture_all_cameras():
    # 启动每台相机并抓图
    threads = []
    for i in range(NUM_CAMERAS):
        thread = threading.Thread(target=start_capture, args=(cameras[i], i))
        threads.append(thread)
        thread.start()
        time.sleep(2)  # 每台相机启动间隔2秒

    # 等待所有线程完成
    for thread in threads:
        thread.join()

# 主程序
if __name__ == "__main__":
    print("Initializing cameras...")
    init_cameras()  # 初始化相机
    capture_all_cameras()  # 启动并开始抓图
