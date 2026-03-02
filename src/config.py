"""
MemeJet RunPod 서버 설정
- 환경 변수로 오버라이드 가능
"""

import os

# Network volume 경로 (RunPod Console에서 Endpoint에 volume 연결 필요)
VOLUME_PATH = os.environ.get("VOLUME_PATH", "/runpod-volume")

# FaceFusion 설치 경로
FACEFUSION_DIR = os.environ.get("FACEFUSION_DIR", "/facefusion")

# FaceFusion 모델 캐시 (network volume 에 저장 → cold start 방지)
FACEFUSION_ASSETS = f"{FACEFUSION_DIR}/.assets"
VOLUME_ASSETS = f"{VOLUME_PATH}/.assets"
