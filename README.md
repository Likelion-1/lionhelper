# Llama-3 Korean Chat API

FastAPI 기반의 Llama-3 한국어 챗봇 웹 서비스입니다. MLP-KTLim/llama-3-Korean-Bllossom-8B 모델을 사용합니다.

## 🌐 온라인 데모

- **웹 인터페이스**: 브라우저에서 바로 사용 가능한 채팅 인터페이스
- **API 엔드포인트**: 다른 애플리케이션에서 사용할 수 있는 REST API
- **자동 문서**: `/docs`에서 Swagger UI로 API 문서 확인
- **모델**: MLP-KTLim/llama-3-Korean-Bllossom-8B (8B 파라미터)

## 🚀 장점

- **멀티 작업 지원**: 여러 사용자가 동시에 사용 가능
- **크로스 플랫폼**: Windows, macOS, Linux에서 동일하게 작동
- **리소스 효율성**: Ollama가 모델을 별도로 관리
- **확장성**: 웹 API로 다양한 클라이언트에서 접근 가능

## 📋 사전 요구사항

1. **Ollama 설치**
   - [Ollama 공식 사이트](https://ollama.ai/)에서 다운로드
   - Windows: `winget install Ollama.Ollama`
   - macOS: `brew install ollama`

2. **모델 다운로드**
   ```bash
   ollama pull mayo/llama-3-korean-bllossom-8b
   ```

## 🛠️ 로컬 설치 및 실행

1. **의존성 설치**
   ```bash
   pip install -r requirements.txt
   ```

2. **FastAPI 서버 실행**
   ```bash
   python main.py
   # 또는
   uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **웹 브라우저에서 접속**
   ```
   http://localhost:8000
   ```

**참고**: 첫 실행 시 모델 다운로드에 시간이 걸릴 수 있습니다 (약 15-20GB).

## 🚀 무료 호스팅 배포

### Render.com 배포 (권장)

1. **GitHub에 코드 업로드**
   ```bash
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/yourusername/llama3-korean-chat.git
   git push -u origin main
   ```

2. **Render.com에서 새 서비스 생성**
   - [Render.com](https://render.com)에 가입
   - "New Web Service" 클릭
   - GitHub 저장소 연결
   - 환경 변수 설정:
     - `OLLAMA_API_URL`: 실제 Ollama 서버 URL
     - `MODEL_NAME`: 사용할 모델명

3. **배포 완료**
   - 자동으로 배포가 시작됩니다
   - 배포 완료 후 제공되는 URL로 접속

### 다른 플랫폼

- **Heroku**: `Procfile` 사용
- **Railway**: `railway.json` 설정
- **Vercel**: `vercel.json` 설정

## 🌐 API 엔드포인트

- `GET /`: 서버 정보
- `POST /chat`: 챗봇 대화
- `GET /health`: 서버 상태 확인
- `GET /models`: 사용 가능한 모델 목록

## 📊 성능 비교

| 항목 | 현재 test.py | FastAPI 기반 |
|------|-------------|-------------|
| 동시 사용자 | 1명 | 다수 |
| 메모리 사용 | 높음 | 낮음 |
| 확장성 | 제한적 | 우수 |
| 플랫폼 호환성 | 제한적 | 우수 |
| 에러 처리 | 기본적 | 체계적 |

## 🔧 설정 옵션

`main.py`에서 다음 설정을 변경할 수 있습니다:

```python
MODEL_NAME = "mayo/llama-3-korean-bllossom-8b"  # 모델명
OLLAMA_API_URL = "http://localhost:11434/api/generate"  # Ollama API 주소
```

## 🚨 문제 해결

1. **Ollama 연결 오류**
   - Ollama가 실행 중인지 확인
   - `ollama serve` 명령어로 서버 시작

2. **모델 다운로드 오류**
   - 인터넷 연결 확인
   - `ollama pull mayo/llama-3-korean-bllossom-8b` 재실행

3. **포트 충돌**
   - `main.py`에서 포트 번호 변경
   - 다른 서비스와 포트 충돌 확인 