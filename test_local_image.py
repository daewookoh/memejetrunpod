"""
로컬 FaceFusion 이미지→이미지 합성 테스트
- 1.png (얼굴/source) + target (대상/target) → output
- output 확장자는 target 확장자와 동일하게 맞춤
"""

import subprocess
import sys
import os

FACEFUSION_DIR = os.path.join(os.path.dirname(__file__), "facefusion")
SOURCE_IMG = "/Users/daewookoh/Desktop/1.png"
TARGET_IMG = "/Users/daewookoh/Desktop/target.png"

# FaceFusion은 target과 output 확장자가 일치해야 함
target_ext = os.path.splitext(TARGET_IMG)[1]
OUTPUT_IMG = os.path.join(os.path.dirname(__file__), f"test_output_image{target_ext}")

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
print(f"[TEST] Running FaceFusion image-to-image swap...")
print()

proc = subprocess.run(cmd, cwd=FACEFUSION_DIR)

if proc.returncode == 0 and os.path.exists(OUTPUT_IMG):
    size = os.path.getsize(OUTPUT_IMG)
    print(f"\n[SUCCESS] 합성 완료! 결과: {OUTPUT_IMG} ({size / 1024:.1f}KB)")
else:
    print(f"\n[FAILED] returncode={proc.returncode}")
