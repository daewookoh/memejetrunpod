"""
MemeJet RunPod Serverless Handler
- Network volume 에 템플릿 + 모델 캐시
- FaceFusion headless-run 으로 face swap
- 결과 프레임을 base64 배열로 반환
"""

import base64
import hashlib
import io
import os
import re
import shutil
import subprocess
import tempfile

import requests
import runpod
from PIL import Image

from config import (
    VOLUME_PATH,
    FACEFUSION_DIR,
    MP4_DIR,
    FACEFUSION_ASSETS,
    VOLUME_ASSETS,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 초기화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def setup():
    """디렉토리 초기화 + FaceFusion 모델 캐시 심링크."""
    os.makedirs(MP4_DIR, exist_ok=True)
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
# 템플릿 준비
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def prepare_template(tid: str, video_url: str) -> dict | None:
    """MP4 다운로드 + 프레임 수 파악. 성공 시 info dict."""
    # URL 해시로 캐시 키 생성 (URL 변경 시 재다운로드)
    url_hash = hashlib.md5(video_url.encode()).hexdigest()[:8]
    mp4_path = f"{MP4_DIR}/{tid}_{url_hash}.mp4"

    # 1) MP4 다운로드
    if not os.path.exists(mp4_path):
        try:
            r = requests.get(video_url, timeout=60)
            if r.status_code != 200:
                print(f"[WARN] MP4 download failed {tid}: HTTP {r.status_code}")
                return None
            with open(mp4_path, "wb") as f:
                f.write(r.content)
            print(f"[DL] {tid} downloaded from R2")
        except Exception as e:
            print(f"[WARN] MP4 download error {tid}: {e}")
            return None

    # 2) 프레임 수 파악 (ffprobe)
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-count_frames", "-select_streams", "v:0",
                "-show_entries", "stream=nb_read_frames",
                "-of", "csv=p=0",
                mp4_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        frame_count = int(result.stdout.strip())
    except Exception:
        frame_count = 0

    if frame_count == 0:
        print(f"[WARN] {tid}: no frames detected")
        return None

    info = {"frame_count": frame_count, "mp4_path": mp4_path}
    print(f"[OK] {tid}: {frame_count} frames")
    return info


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 유틸
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def decode_base64_to_file(data: str, path: str):
    """base64 → JPEG 파일 저장."""
    if data.startswith("data:"):
        data = data.split(",", 1)[1]
    raw = base64.b64decode(data)
    img = Image.open(io.BytesIO(raw)).convert("RGB")
    img.save(path, "JPEG", quality=95)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RunPod Handler
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def handler(job):
    """
    Input:
      - template_id: str  (템플릿 ID)
      - video_url: str    (R2 MP4 URL)
      - swap_image: str   (base64 face image)
    Output:
      - frames: list[str] (base64 PNG frames)
      - count: int
    """
    job_input = job["input"]
    template_id = job_input.get("template_id")
    video_url = job_input.get("video_url")
    swap_image = job_input.get("swap_image")

    if not template_id or not swap_image or not video_url:
        return {"error": "template_id, video_url, and swap_image are required"}

    # 템플릿 준비 (network volume 캐시)
    info = prepare_template(template_id, video_url)
    if info is None:
        return {"error": "template_not_found"}

    mp4_path = info["mp4_path"]
    total = info["frame_count"]
    work_dir = tempfile.mkdtemp(prefix="swap_")

    try:
        # 얼굴 저장
        source_path = f"{work_dir}/source.jpg"
        decode_base64_to_file(swap_image, source_path)

        output_path = f"{work_dir}/output.mp4"
        temp_path = f"{work_dir}/ff_temp"
        jobs_path = f"{work_dir}/ff_jobs"

        cmd = [
            "python", f"{FACEFUSION_DIR}/facefusion.py", "headless-run",
            "-s", source_path,
            "-t", mp4_path,
            "-o", output_path,
            "--processors", "face_swapper",
            "--face-swapper-model", "inswapper_128_fp16",
            "--face-detector-model", "yolo_face",
            "--face-detector-score", "0.3",
            "--output-video-quality", "90",
            "--temp-path", temp_path,
            "--jobs-path", jobs_path,
        ]

        print(f"[SWAP] {template_id}: processing {total} frames")
        runpod.serverless.progress_update(job, {"step": "sending", "done": 0, "total": total, "percent": 0})

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=FACEFUSION_DIR,
        )

        # 로그 출력 + 진행률 전송
        progress_re = re.compile(r"processing:.*\|\s*(\d+)/(\d+)\s*\[")
        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                m = progress_re.search(line)
                if m:
                    done = int(m.group(1))
                    frame_total = int(m.group(2))
                    pct = int(done / frame_total * 100) if frame_total > 0 else 0
                    print(f"[FF] progress {done}/{frame_total} ({pct}%)")
                    runpod.serverless.progress_update(job, {"step": "composing", "done": done, "total": frame_total, "percent": pct})
                else:
                    print(f"[FF] {line}")

        proc.wait()

        if proc.returncode != 0 or not os.path.exists(output_path):
            print(f"[FF-ERR] returncode={proc.returncode}")
            return {"error": "face_swap_failed"}

        print(f"[SWAP] FaceFusion done: {template_id}")
        runpod.serverless.progress_update(job, {"step": "generating", "done": 0, "total": 0, "percent": 90})

        # 출력 비디오 → 프레임 추출
        frames_out = f"{work_dir}/out_frames"
        os.makedirs(frames_out, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-i", output_path, "-vsync", "0", f"{frames_out}/%06d.png"],
            capture_output=True,
        )

        out_files = sorted(f for f in os.listdir(frames_out) if f.endswith(".png"))
        count = len(out_files)
        print(f"[SWAP] Extracted {count} frames")

        # base64 인코딩
        frames_b64 = []
        for fname in out_files:
            with open(f"{frames_out}/{fname}", "rb") as f:
                frames_b64.append(base64.b64encode(f.read()).decode("utf-8"))

        return {"frames": frames_b64, "count": count}

    except Exception as e:
        print(f"[ERR] {e}")
        return {"error": str(e)}
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


# ── 시작 ──────
setup()
runpod.serverless.start({"handler": handler})
