# Llama-3 Korean Bllossom Chatbot API

[Hugging Face의 Llama-3 Korean Bllossom 모델](https://huggingface.co/MLP-KTLim/llama-3-Korean-Bllossom-8B)을 사용한 한국어 챗봇 API 서버입니다.

## 특징

- **한국어 최적화**: 3만개 이상의 한국어 어휘 확장
- **긴 컨텍스트 처리**: Llama3 대비 25% 더 긴 한국어 컨텍스트 처리 가능
- **한국어-영어 이중 언어**: 한국어-영어 지식 연결
- **FastAPI 기반**: 현대적이고 빠른 API 서버

## 설치 및 실행

### 1. 가상환경 생성 및 활성화

```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# 또는
venv\Scripts\activate     # Windows
```

### 2. 의존성 설치

```bash
pip install -r requirements.txt
```

### 3. 서버 실행

```bash
python app.py
```

또는

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

## API 사용법

### 기본 엔드포인트

- `GET /`: 서버 상태 확인
- `GET /docs`: Swagger UI 문서
- `GET /model-info`: 모델 정보 확인
- `POST /generate`: 텍스트 생성

### 텍스트 생성 예시

```bash
curl -X POST "http://localhost:8000/generate" \
     -H "Content-Type: application/json" \
     -d '{
       "prompt": "안녕하세요! 오늘 날씨에 대해 이야기해주세요.",
       "max_new_tokens": 150,
       "temperature": 0.7,
       "top_p": 0.9
     }'
```

### Python 클라이언트 예시

```python
import requests

url = "http://localhost:8000/generate"
data = {
    "prompt": "안녕하세요! 오늘 날씨에 대해 이야기해주세요.",
    "max_new_tokens": 150,
    "temperature": 0.7,
    "top_p": 0.9
}

response = requests.post(url, json=data)
result = response.json()
print(result["generated_text"])
```

## 시스템 요구사항

- **Python**: 3.8 이상
- **메모리**: 최소 16GB RAM (모델 로딩용)
- **GPU**: 권장 (CUDA 지원 GPU)
- **저장공간**: 약 16GB (모델 다운로드용)

## 모델 정보

- **모델명**: MLP-KTLim/llama-3-Korean-Bllossom-8B
- **기반 모델**: Llama-3 8B
- **언어**: 한국어, 영어
- **라이선스**: Llama3 라이선스

## 개발자 정보

이 모델은 서울과기대, 테디썸, 연세대 언어자원 연구실에서 개발되었습니다.

## 라이선스

이 프로젝트는 Llama3 라이선스를 따릅니다. 