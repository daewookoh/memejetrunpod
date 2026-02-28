FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# ── 시스템 의존성 ──────
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── FaceFusion 설치 ──────
RUN git clone https://github.com/facefusion/facefusion.git /facefusion
WORKDIR /facefusion
RUN pip install --no-cache-dir -r requirements.txt

# ── Handler 의존성 ──────
COPY requirements.txt /requirements.txt
RUN pip install --no-cache-dir -r /requirements.txt

# ── Handler 복사 ──────
COPY src/ /src/

# ── Network volume mount point ──────
# RunPod Console에서 volume 연결 시 자동 마운트
ENV VOLUME_PATH=/runpod-volume
ENV FACEFUSION_DIR=/facefusion

CMD ["python", "/src/handler.py"]
