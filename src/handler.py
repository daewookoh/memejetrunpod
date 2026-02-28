"""
MemeJet RunPod Serverless Handler
- Network volume 에 템플릿 + 모델 캐시
- FaceFusion headless-run 으로 face swap
- 결과 프레임을 base64 배열로 반환
"""

import base64
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
    GIF_DIR,
    FRAMES_DIR,
    MP4_DIR,
    FACEFUSION_ASSETS,
    VOLUME_ASSETS,
)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 초기화
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def setup():
    """디렉토리 초기화 + FaceFusion 모델 캐시 심링크."""
    os.makedirs(GIF_DIR, exist_ok=True)
    os.makedirs(FRAMES_DIR, exist_ok=True)
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

def prepare_template(tid: str) -> dict | None:
    """GIF 다운로드 → 프레임 추출 → MP4 변환. 성공 시 info dict."""
    gif_path = f"{GIF_DIR}/{tid}.gif"
    frame_dir = f"{FRAMES_DIR}/{tid}"
    mp4_path = f"{MP4_DIR}/{tid}.mp4"

    url = f"https://media.giphy.com/media/{tid}/giphy.gif"

    # 1) GIF 다운로드
    if not os.path.exists(gif_path):
        try:
            r = requests.get(url, timeout=30)
            if r.status_code != 200:
                print(f"[WARN] GIF download failed {tid}: HTTP {r.status_code}")
                return None
            with open(gif_path, "wb") as f:
                f.write(r.content)
            print(f"[DL] {tid} downloaded")
        except Exception as e:
            print(f"[WARN] GIF download error {tid}: {e}")
            return None

    # 2) 프레임 추출
    if not os.path.exists(frame_dir) or not os.listdir(frame_dir):
        os.makedirs(frame_dir, exist_ok=True)
        subprocess.run(
            ["ffmpeg", "-i", gif_path, "-vsync", "0", f"{frame_dir}/%06d.png"],
            capture_output=True,
        )

    frame_files = sorted(f for f in os.listdir(frame_dir) if f.endswith(".png"))
    if not frame_files:
        print(f"[WARN] {tid}: no frames extracted")
        return None

    # 3) MP4 변환
    if not os.path.exists(mp4_path):
        subprocess.run(
            [
                "ffmpeg", "-framerate", "10",
                "-i", f"{frame_dir}/%06d.png",
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                mp4_path,
            ],
            capture_output=True,
        )
        print(f"[MP4] {tid}: converted")

    info = {"frame_count": len(frame_files), "mp4_path": mp4_path}
    print(f"[OK] {tid}: {info['frame_count']} frames")
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
      - template_id: str  (Giphy media ID)
      - swap_image: str   (base64 face image)
    Output:
      - frames: list[str] (base64 PNG frames)
      - count: int
    """
    job_input = job["input"]
    template_id = job_input.get("template_id")
    swap_image = job_input.get("swap_image")

    if not template_id or not swap_image:
        return {"error": "template_id and swap_image are required"}

    # 템플릿 준비 (network volume 캐시)
    info = prepare_template(template_id)
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

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            cwd=FACEFUSION_DIR,
        )

        # 로그 출력
        progress_re = re.compile(r"processing:.*\|\s*(\d+)/(\d+)\s*\[")
        for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                m = progress_re.search(line)
                if m:
                    print(f"[FF] progress {m.group(1)}/{m.group(2)}")
                else:
                    print(f"[FF] {line}")

        proc.wait()

        if proc.returncode != 0 or not os.path.exists(output_path):
            print(f"[FF-ERR] returncode={proc.returncode}")
            return {"error": "face_swap_failed"}

        print(f"[SWAP] FaceFusion done: {template_id}")

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
