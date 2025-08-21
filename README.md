# 한국어 AI 챗봇 (하이브리드 시스템)

한국어에 특화된 AI 챗봇 서비스로, 키워드 기반 빠른 응답 시스템과 Ollama GPT-OSS-20B 모델을 결합한 하이브리드 AI 시스템입니다.

## 🚀 주요 기능

### 1. 키워드 기반 빠른 응답
- 미리 정의된 질문-답변 쌍으로 즉시 응답
- 키워드 매칭 및 유사도 계산
- 훈련 관련 정보 제공

### 2. Ollama GPT-OSS-20B 통합
- 키워드 매칭 실패 시 AI 모델 사용
- 자연어 이해 및 생성
- 한국어 특화 응답

### 3. 하이브리드 시스템
- 빠른 응답 + AI 생성 응답
- 응답 타입 구분 (`keyword` / `ollama`)
- 사용자 선택 가능

## 🛠️ 기술 스택

### Backend
- **FastAPI** - 웹 프레임워크
- **Uvicorn** - ASGI 서버
- **Gunicorn** - WSGI 서버 (프로덕션)
- **Pydantic** - 데이터 검증
- **Requests** - HTTP 클라이언트

### AI/ML
- **Ollama** - 로컬 LLM 실행
- **GPT-OSS-20B** - 20B 파라미터 오픈소스 모델
- **SequenceMatcher** - 문자열 유사도 계산

### DevOps
- **Render** - 클라우드 배포
- **Docker** - 컨테이너화
- **Python 3.11** - 런타임

## 📦 설치 및 실행

### 1. 로컬 개발 환경

```bash
# 저장소 클론
git clone <repository-url>
cd helper

# 의존성 설치
pip install -r requirements.txt

# Ollama 설치 (macOS)
brew install ollama

# Ollama 모델 다운로드
ollama pull openai/gpt-oss-20b

# Ollama 서버 시작
ollama serve

# FastAPI 서버 시작
uvicorn main:app --reload --port 8000
```

### 2. 테스트

```bash
# 통합 테스트 실행
python test_ollama.py
```

## 🌐 API 엔드포인트

### POST /chat
챗봇과의 대화를 수행합니다.

**요청:**
```json
{
  "prompt": "사용자 질문",
  "max_new_tokens": 512,
  "temperature": 0.6,
  "use_ollama": true
}
```

**응답:**
```json
{
  "response": "챗봇 답변",
  "model": "openai/gpt-oss-20b",
  "status": "success",
  "matched_keywords": ["키워드1"],
  "response_type": "ollama"
}
```

### GET /info
모델 정보를 반환합니다.

### GET /health
서버 상태를 확인합니다.

### GET /qa-list
등록된 QA 목록을 반환합니다.

## 🔧 환경 변수

- `OLLAMA_BASE_URL`: Ollama 서버 URL (기본값: http://localhost:11434)
- `PORT`: 서버 포트 (기본값: 8000)

## 🚀 배포

### Render 배포

1. Render 대시보드에서 새 Web Service 생성
2. GitHub 저장소 연결
3. 환경 변수 설정:
   - `OLLAMA_BASE_URL`: http://ollama:11434
4. 배포 완료

## 📊 성능 특징

### 키워드 기반 응답
- 응답 시간: < 100ms
- 정확도: 95%+
- 지원 주제: 8개 카테고리

### Ollama 응답
- 응답 시간: 2-5초
- 모델 크기: 20B 파라미터
- 한국어 지원: ✅

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 📞 문의

프로젝트에 대한 문의사항이 있으시면 이슈를 생성해주세요.
