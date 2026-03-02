"""
로컬 FaceFusion 테스트 스크립트
- 1.png (얼굴/source) + 2.png (대상/target) → output.png
"""

import subprocess
import sys
import os

FACEFUSION_DIR = os.path.join(os.path.dirname(__file__), "facefusion")
SOURCE_IMG = "/Users/daewookoh/Desktop/1.png"  # 얼굴
TARGET_IMG = "/Users/daewookoh/Desktop/2.png"  # 대상
OUTPUT_IMG = os.path.join(os.path.dirname(__file__), "test_output.png")

cmd = [
    sys.executable,
    os.path.join(FACEFUSION_DIR, "facefusion.py"),
    "headless-run",
    "-s", SOURCE_IMG,
    "-t", TARGET_IMG,
    "-o", OUTPUT_IMG,
    "--processors", "face_swapper",
    "--face-swapper-model", "inswapper_128_fp16",
    "--face-detector-model", "yolo_face",
    "--face-detector-score", "0.3",
]

print(f"[TEST] Source (얼굴): {SOURCE_IMG}")
print(f"[TEST] Target (대상): {TARGET_IMG}")
print(f"[TEST] Output: {OUTPUT_IMG}")
print(f"[TEST] Running FaceFusion...")
print(f"[CMD] {' '.join(cmd)}")
print()

proc = subprocess.run(
    cmd,
    cwd=FACEFUSION_DIR,
)

if proc.returncode == 0 and os.path.exists(OUTPUT_IMG):
    print(f"\n[SUCCESS] 합성 완료! 결과: {OUTPUT_IMG}")
else:
    print(f"\n[FAILED] returncode={proc.returncode}")
