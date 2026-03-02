"""
MemeJet RunPod Serverless Handler
- Network volume 에 모델 캐시
- FaceFusion headless-run 으로 단일 이미지 face swap
- 결과 이미지를 base64 로 반환
"""

import base64
import io
import os
import shutil
import subprocess
import tempfile
import time

import runpod
from PIL import Image

from config import (
    VOLUME_PATH,
    FACEFUSION_DIR,
    FACEFUSION_ASSETS,
    VOLUME_ASSETS,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 초기화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def setup():
    """디렉토리 초기화 + FaceFusion 모델 캐시 심링크."""
    os.makedirs(VOLUME_ASSETS, exist_ok=True)

    # FaceFusion .assets → network volume 심링크
    if os.path.islink(FACEFUSION_ASSETS):
        os.unlink(FACEFUSION_ASSETS)
    elif os.path.isdir(FACEFUSION_ASSETS):
        for item in os.listdir(FACEFUSION_ASSETS):
            src = os.path.join(FACEFUSION_ASSETS, item)
            dst = os.path.join(VOLUME_ASSETS, item)
            if not os.path.exists(dst):
                shutil.move(src, dst)
        shutil.rmtree(FACEFUSION_ASSETS)
    os.symlink(VOLUME_ASSETS, FACEFUSION_ASSETS)
    print(f"[INIT] .assets -> {VOLUME_ASSETS}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def decode_base64_to_file(data: str, path: str):
    """base64 → PNG 파일 저장."""
    if data.startswith("data:"):
        data = data.split(",", 1)[1]
    raw = base64.b64decode(data)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img.save(path, "PNG")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RunPod Handler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def handler(job):
    """
    Input:
      - template_id: str     (템플릿 ID)
      - target_image: str    (base64 대상 이미지)
      - swap_image: str      (base64 얼굴 이미지)
    Output:
      - image: str           (base64 PNG 결과 이미지)
    """
    job_input = job["input"]
    template_id = job_input.get("template_id")
    target_image = job_input.get("target_image")
    swap_image = job_input.get("swap_image")

    if not template_id or not target_image or not swap_image:
        return {"error": "template_id, target_image, and swap_image are required"}

    work_dir = tempfile.mkdtemp(prefix="swap_")

    try:
        # 얼굴(source) 저장
        source_path = f"{work_dir}/source.png"
        decode_base64_to_file(swap_image, source_path)

        # 대상(target) 저장
        target_path = f"{work_dir}/target.png"
        decode_base64_to_file(target_image, target_path)

        output_path = f"{work_dir}/output.png"
        jobs_path = f"{work_dir}/ff_jobs"

        cmd = [
            "python", f"{FACEFUSION_DIR}/facefusion.py", "headless-run",
            "-s", source_path,
            "-t", target_path,
            "-o", output_path,
            "--processors", "face_swapper",
            "--face-swapper-model", "inswapper_128_fp16",
            "--face-detector-model", "yolo_face",
            "--face-detector-score", "0.3",
            "--jobs-path", jobs_path,
        ]

        print(f"[SWAP] {template_id}: processing single image")
        runpod.serverless.progress_update(job, {"step": "composing", "percent": 10})

        EXECUTION_TIMEOUT = 30

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=FACEFUSION_DIR,
        )

        start_time = time.time()
        ff_logs = []
        for raw_line in proc.stdout:
            elapsed = time.time() - start_time
            if elapsed > EXECUTION_TIMEOUT:
                print(f"[TIMEOUT] {elapsed:.1f}s exceeded {EXECUTION_TIMEOUT}s limit")
                proc.kill()
                proc.wait()
                return {"error": "timeout", "detail": f"Exceeded {EXECUTION_TIMEOUT}s", "logs": ff_logs[-20:]}

            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                ff_logs.append(line)
                print(f"[FF] {line}")

        proc.wait()

        elapsed = time.time() - start_time
        print(f"[SWAP] FaceFusion finished in {elapsed:.1f}s")

        if proc.returncode != 0 or not os.path.exists(output_path):
            print(f"[FF-ERR] returncode={proc.returncode}")
            return {"error": "face_swap_failed", "returncode": proc.returncode, "elapsed": round(elapsed, 1), "logs": ff_logs[-30:]}

        runpod.serverless.progress_update(job, {"step": "composing", "percent": 90})

        # 결과 이미지 base64 인코딩
        with open(output_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        print(f"[SWAP] Done: {template_id}")
        return {"image": image_b64}

    except Exception as e:
        print(f"[ERR] {e}")
        return {"error": str(e)}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ── 시작 ──────
setup()
runpod.serverless.start({"handler": handler})
