"""
로컬 FaceFusion 영상 합성 테스트
- 4.png (얼굴/source) + shocked.mp4 (대상/target) → output.mp4
"""

import subprocess
import sys
import os

FACEFUSION_DIR = os.path.join(os.path.dirname(__file__), "facefusion")
SOURCE_IMG = "/Users/daewookoh/Desktop/4.png"
TARGET_VID = os.path.join(os.path.dirname(__file__), "test_shocked.mp4")
OUTPUT_VID = os.path.join(os.path.dirname(__file__), "test_output_video.mp4")
TEMP_PATH = os.path.join(os.path.dirname(__file__), "ff_temp")
JOBS_PATH = os.path.join(os.path.dirname(__file__), "ff_jobs")

cmd = [
    sys.executable,
    os.path.join(FACEFUSION_DIR, "facefusion.py"),
    "headless-run",
    "-s", SOURCE_IMG,
    "-t", TARGET_VID,
    "-o", OUTPUT_VID,
    "--processors", "face_swapper",
    "--face-swapper-model", "inswapper_128_fp16",
    "--face-detector-model", "yolo_face",
    "--face-detector-score", "0.3",
    "--output-video-quality", "90",
    "--temp-path", TEMP_PATH,
    "--jobs-path", JOBS_PATH,
]

print(f"[TEST] Source (얼굴): {SOURCE_IMG}")
print(f"[TEST] Target (영상): {TARGET_VID}")
print(f"[TEST] Output: {OUTPUT_VID}")
print(f"[TEST] Running FaceFusion on video...")
print(f"[CMD] {' '.join(cmd)}")
print()

proc = subprocess.run(cmd, cwd=FACEFUSION_DIR)

if proc.returncode == 0 and os.path.exists(OUTPUT_VID):
    size = os.path.getsize(OUTPUT_VID)
    print(f"\n[SUCCESS] 영상 합성 완료! 결과: {OUTPUT_VID} ({size / 1024:.1f}KB)")
else:
    print(f"\n[FAILED] returncode={proc.returncode}")
