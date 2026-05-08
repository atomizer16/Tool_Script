import os
import subprocess

# ==========================
# User-configurable section
video_path = "D:/CV-Dataset/DJI_20260113111034_0008_D.mp4"  # <-- fill in your video path
output_dir = "D:/CV-Dataset/video2png"   # <-- fill in the folder to save frames
# ==========================

# Create output directory if it does not exist
os.makedirs(output_dir, exist_ok=True)

# ffmpeg command: lossless frame extraction to PNG
# -vsync 0 ensures every frame is output without dropping
# frame_%06d.png naming: frame_000001.png, frame_000002.png, ...
ffmpeg_cmd = [
    "ffmpeg",
    "-i", video_path,
    "-vsync", "0",
    os.path.join(output_dir, "frame_%06d.png")
]

# Run ffmpeg
try:
    subprocess.run(ffmpeg_cmd, check=True)
    print(f"Frame extraction completed. All frames saved to: {output_dir}")
except subprocess.CalledProcessError as e:
    print(f"Frame extraction failed. Error: {e}")