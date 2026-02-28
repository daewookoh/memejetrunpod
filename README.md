# MemeJet RunPod Serverless

FaceFusion 기반 Face Swap AI 서버 — RunPod Serverless GPU 배포용

## 구조

```
├── Dockerfile          # RunPod serverless 이미지
├── requirements.txt    # Python 의존성
├── src/
│   ├── config.py       # 환경 변수 + 경로 설정
│   └── handler.py      # RunPod serverless handler
└── test_input.json     # 로컬 테스트용 입력
```

## Network Volume

- RunPod Console에서 Network Volume 생성 후 Endpoint에 연결
- 저장 내용: FaceFusion 모델 캐시 (.assets), GIF 템플릿, 프레임, MP4

## 배포 순서

### 1. Docker 이미지 빌드 & 푸시

```bash
# DockerHub
docker build -t YOUR_DOCKERHUB/memejet-runpod:latest .
docker push YOUR_DOCKERHUB/memejet-runpod:latest
```

### 2. RunPod Serverless Endpoint 생성

1. [RunPod Console](https://www.runpod.io/console/serverless) → New Endpoint
2. 설정:
   - **Container Image**: `YOUR_DOCKERHUB/memejet-runpod:latest`
   - **GPU**: RTX 3090 / RTX 4090 (24GB VRAM 권장)
   - **Volume**: 생성한 Network Volume → `/runpod-volume`
   - **Max Workers**: 필요에 따라 설정
   - **Idle Timeout**: 5초 (비용 절감)
   - **Execution Timeout**: 600초

### 3. Flutter 앱 설정

`lib/constants.dart`:
```dart
static const ServerMode serverMode = ServerMode.runpod;
static const String runpodEndpointId = 'YOUR_ENDPOINT_ID';   // RunPod Console에서 확인
static const String runpodApiKey = 'YOUR_RUNPOD_API_KEY';    // RunPod Console → API Keys
```

## API

### Input
```json
{
  "input": {
    "template_id": "l3q2K5jinAlChoCLS",
    "swap_image": "data:image/jpeg;base64,..."
  }
}
```

### Output (성공)
```json
{
  "frames": ["base64...", "base64...", ...],
  "count": 24
}
```

### Output (에러)
```json
{
  "error": "template_not_found | face_swap_failed | ..."
}
```
