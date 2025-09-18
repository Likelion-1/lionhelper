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

## 🔐 Google OAuth 인증 API

### GET /auth/google
Google OAuth 로그인을 시작합니다. 사용자를 Google 로그인 페이지로 리다이렉트합니다.

### GET /auth/google/callback
Google OAuth 콜백을 처리하고 JWT 토큰을 발급합니다.

**응답:**
```json
{
  "success": true,
  "message": "로그인에 성공했습니다!",
  "token": {
    "access_token": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "token_type": "bearer",
    "expires_in": 1800,
    "user": {
      "id": "user-uuid",
      "email": "user@example.com",
      "name": "사용자 이름",
      "picture": "https://lh3.googleusercontent.com/...",
      "created_at": "2024-01-15T10:30:00"
    }
  },
  "user": {
    "id": "user-uuid",
    "email": "user@example.com",
    "name": "사용자 이름",
    "picture": "https://lh3.googleusercontent.com/...",
    "created_at": "2024-01-15T10:30:00"
  }
}
```

### GET /auth/me
현재 로그인한 사용자의 정보를 조회합니다. Authorization 헤더에 Bearer 토큰이 필요합니다.

**헤더:**
```
Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...
```

### POST /auth/logout
사용자를 로그아웃 처리합니다. (클라이언트에서 토큰 삭제 필요)

## 🌐 프론트엔드 연동 가이드

### 1. Google 로그인 구현

```javascript
// Google 로그인 버튼 클릭 시
function loginWithGoogle() {
    window.location.href = 'http://localhost:8001/auth/google';
}

// 콜백 페이지에서 토큰 처리
function handleGoogleCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('access_token');
    
    if (token) {
        // 토큰을 localStorage에 저장
        localStorage.setItem('access_token', token);
        
        // 사용자 정보 가져오기
        fetchUserInfo(token);
    }
}

// 사용자 정보 조회
async function fetchUserInfo(token) {
    try {
        const response = await fetch('http://localhost:8001/auth/me', {
            headers: {
                'Authorization': `Bearer ${token}`
            }
        });
        
        if (response.ok) {
            const user = await response.json();
            console.log('사용자 정보:', user);
            // 사용자 정보를 UI에 표시
        }
    } catch (error) {
        console.error('사용자 정보 조회 실패:', error);
    }
}
```

### 2. 인증이 필요한 API 호출

```javascript
// 토큰이 필요한 API 호출
async function callProtectedAPI() {
    const token = localStorage.getItem('access_token');
    
    if (!token) {
        // 로그인 페이지로 리다이렉트
        window.location.href = '/login';
        return;
    }
    
    try {
        const response = await fetch('http://localhost:8001/chat', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify({
                prompt: '사용자 질문',
                use_ollama: true
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            console.log('챗봇 응답:', data);
        } else if (response.status === 401) {
            // 토큰 만료 - 로그인 페이지로 리다이렉트
            localStorage.removeItem('access_token');
            window.location.href = '/login';
        }
    } catch (error) {
        console.error('API 호출 실패:', error);
    }
}
```

### 3. 로그아웃 구현

```javascript
function logout() {
    // 토큰 삭제
    localStorage.removeItem('access_token');
    
    // 로그아웃 API 호출 (선택사항)
    fetch('http://localhost:8001/auth/logout', {
        method: 'POST'
    });
    
    // 로그인 페이지로 리다이렉트
    window.location.href = '/login';
}
```

## 🔧 환경 변수

### 기본 설정
- `OLLAMA_BASE_URL`: Ollama 서버 URL (기본값: http://localhost:11434)
- `PORT`: 서버 포트 (기본값: 8000)

### Google OAuth 설정 (로그인 기능)
- `GOOGLE_CLIENT_ID`: Google OAuth 클라이언트 ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth 클라이언트 시크릿
- `SECRET_KEY`: JWT 토큰 서명용 시크릿 키

### Google OAuth 설정 방법
1. [Google Cloud Console](https://console.cloud.google.com/) 접속
2. 새 프로젝트 생성 또는 기존 프로젝트 선택
3. "API 및 서비스" > "사용자 인증 정보" 이동
4. "사용자 인증 정보 만들기" > "OAuth 2.0 클라이언트 ID" 선택
5. 애플리케이션 유형: "웹 애플리케이션"
6. 승인된 리디렉션 URI 추가:
   - 개발: `http://localhost:8001/auth/google/callback`
   - 프로덕션: `https://yourdomain.com/auth/google/callback`
7. 클라이언트 ID와 시크릿을 환경변수로 설정

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
