# 🦁 라이언 헬퍼 (Lion Helper)

멋쟁이사자처럼 K-Digital Training 부트캠프를 위한 AI 챗봇 & 검색 엔진 시스템

## 🚀 주요 기능

### 1. 🔍 스마트 검색 엔진
- 키워드 기반 관련 질문 검색
- 47개 카테고리 QA 데이터베이스
- 관련도 점수 계산 및 정렬
- 한 번에 모든 관련 정보 확인 가능

### 2. 🤖 하이브리드 AI 챗봇
- **Claude-3-Haiku** (Anthropic) - 지능형 대화 및 전문 상담
- **키워드 DB** - 빠른 응답 및 정확한 정보 제공
- 자연스러운 상담사 톤의 응답
- 컨텍스트 기반 지능형 답변

### 3. 💬 대화 세션 관리
- PostgreSQL 기반 대화 기록 저장
- 세션별 메시지 관리
- 대화 히스토리 조회 및 관리

### 4. 📊 슬랙 연동
- 슬랙 채널 이슈 자동 동기화
- 이슈 메시지 파싱 및 저장
- 실시간 이슈 트래킹

### 5. 🔐 Google OAuth 인증
- Google 계정 로그인
- JWT 토큰 기반 인증
- 사용자 정보 관리

### 6. 📈 피드백 시스템
- 답변 품질 피드백 수집
- 사용자 수정 제안 저장
- 답변 개선 로그 관리

## 🎯 지원 주제 (47개 카테고리)

### 💰 훈련장려금
- 계좌 변경, 금액, 지급시기
- 수령 조건, 신청 방법

### 📋 출결관리
- QR코드 출결, 지각, 조퇴, 외출
- 공결 신청, 결석 처리

### 🖥️ 교육도구
- 줌 설정 및 배경화면
- 노트북 대여/반납
- 교재 수령 및 관리

### 🎓 학습지원
- 기초클래스, OT, 녹화본
- 과제 제출, 평가 기준

### 💼 커리어
- 수료 후 취업 지원
- 조기취업, 인턴십
- 포트폴리오 특강

## 🛠️ 기술 스택

### Backend
- **FastAPI** 0.104.1 - 고성능 웹 프레임워크
- **Uvicorn** 0.24.0 - ASGI 서버
- **Gunicorn** 21.2.0 - 프로덕션 WSGI 서버
- **Pydantic** - 데이터 검증 및 직렬화

### AI/ML
- **Anthropic Claude-3-Haiku** - 빠르고 효율적인 AI 모델
- **Tenacity** 8.2.3 - API 재시도 로직
- **SequenceMatcher** - 문자열 유사도 계산

### Database
- **PostgreSQL** - 메인 데이터베이스
- **psycopg2-binary** 2.9.0+ - PostgreSQL 어댑터

### Authentication
- **python-jose** 3.3.0 - JWT 토큰 처리
- **passlib** 1.7.4 - 비밀번호 해싱
- **authlib** 1.2.1 - OAuth 인증

### Integration
- **slack-sdk** 3.37.0+ - 슬랙 API 연동
- **requests** - HTTP 클라이언트

## 📦 설치 및 실행

### 1. 저장소 클론

```bash
git clone https://github.com/Likelion-1/lionhelper.git
cd lionhelper
```

### 2. 가상환경 생성 및 활성화

```bash
python -m venv lionhelper
source lionhelper/bin/activate  # macOS/Linux
# lionhelper\Scripts\activate  # Windows
```

### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

### 4. 환경 변수 설정

`.env` 파일을 생성하고 다음 변수들을 설정하세요:

```env
# Anthropic Claude API
ANTHROPIC_API_KEY=your_anthropic_api_key
USE_CLAUDE=true

# PostgreSQL Database
DATABASE_URL=postgresql://username:password@localhost:5432/chat_history
DB_HOST=localhost
DB_PORT=5432
DB_NAME=chat_history
DB_USER=username
DB_PASSWORD=password

# Google OAuth
GOOGLE_CLIENT_ID=your_google_client_id
GOOGLE_CLIENT_SECRET=your_google_client_secret
SECRET_KEY=your_jwt_secret_key

# Slack Integration
SLACK_BOT_TOKEN=xoxb-your-slack-bot-token
SLACK_CHANNEL_ID=C08M47TM2KH

# Server
PORT=8001
```

### 5. 데이터베이스 초기화

PostgreSQL 데이터베이스를 생성하고 연결 정보를 환경 변수에 설정하세요. 
애플리케이션 시작 시 자동으로 필요한 테이블이 생성됩니다.

```bash
# PostgreSQL 설치 (macOS)
brew install postgresql
brew services start postgresql

# 데이터베이스 생성
createdb chat_history
```

### 6. 서버 실행

```bash
# 개발 환경
uvicorn main:app --reload --port 8001

# 프로덕션 환경
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8001
```

### 7. API 문서 확인

브라우저에서 다음 주소로 접속:
- Swagger UI: http://localhost:8001/docs
- ReDoc: http://localhost:8001/redoc

## 🌐 API 엔드포인트

### 🔍 검색 엔진

#### `GET /search`
키워드로 관련 질문 검색

**쿼리 파라미터:**
- `query` (필수): 검색 키워드
- `limit` (선택): 결과 개수 제한 (기본값: 10)
- `min_score` (선택): 최소 점수 (기본값: 0.1)

**예시:**
```bash
GET /search?query=훈련장려금&limit=5&min_score=0.3
```

**응답:**
```json
{
  "query": "훈련장려금",
  "total_found": 5,
  "showing": 5,
  "results": [
    {
      "id": "훈련장려금_금액",
      "question": "훈련장려금은 얼마인가요?",
      "answer_preview": "훈련장려금은 하루 수업을 모두 참여시...",
      "matched_keywords": ["훈련장려금", "얼마"],
      "score": 5.56
    }
  ]
}
```

### 💬 채팅

#### `POST /chat`
AI 챗봇과 대화

**요청 본문:**
```json
{
  "prompt": "훈련장려금은 얼마인가요?",
  "max_new_tokens": 1000,
  "temperature": 0.7,
  "use_claude": true,
  "session_id": "optional-session-id"
}
```

**응답:**
```json
{
  "response": "훈련장려금은 하루 수업을 모두 참여하시면 일일 15,800원이 지급됩니다...",
  "model": "claude-3-haiku-20240307",
  "status": "success",
  "matched_keywords": ["훈련장려금", "얼마"],
  "response_type": "claude_enhanced",
  "session_id": "session-uuid",
  "message_id": "message-uuid"
}
```

**응답 타입:**
- `claude_enhanced`: Claude가 키워드 DB를 참고한 지능형 응답
- `keyword`: 키워드 기반 직접 응답
- `fallback`: 기본 안내 응답

### ❓ QA 관리

#### `GET /qa-list`
등록된 QA 목록 조회

**쿼리 파라미터:**
- `keyword` (선택): 키워드 필터링

**예시:**
```bash
GET /qa-list?keyword=훈련장려금
```

### 📝 세션 관리

#### `POST /sessions`
새 대화 세션 생성

**요청 본문:**
```json
{
  "title": "훈련장려금 문의"
}
```

#### `GET /sessions`
세션 목록 조회

**쿼리 파라미터:**
- `limit` (선택): 결과 개수 (기본값: 50)
- `offset` (선택): 오프셋 (기본값: 0)

#### `GET /sessions/{session_id}`
세션 상세 정보 조회

#### `GET /sessions/{session_id}/messages`
세션의 메시지 목록 조회

#### `DELETE /sessions/{session_id}`
세션 삭제

### 🔐 인증

#### `GET /auth/google`
Google OAuth 로그인 시작

#### `GET /auth/google/callback`
Google OAuth 콜백 처리

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
      "picture": "https://...",
      "created_at": "2024-01-15T10:30:00"
    }
  }
}
```

#### `GET /auth/me`
현재 사용자 정보 조회 (인증 필요)

**헤더:**
```
Authorization: Bearer {access_token}
```

#### `POST /auth/logout`
로그아웃

### 🔄 슬랙 연동

#### `POST /slack/sync`
슬랙 이슈 동기화

**요청 본문:**
```json
{
  "hours": 24,
  "force": false
}
```

#### `GET /slack/issues`
저장된 슬랙 이슈 목록 조회

**쿼리 파라미터:**
- `project` (선택): 프로젝트 필터링
- `issue_type` (선택): 이슈 타입 필터링
- `limit` (선택): 결과 개수
- `offset` (선택): 오프셋

### 📊 피드백

#### `POST /feedback`
답변 피드백 제출

**요청 본문:**
```json
{
  "session_id": "session-uuid",
  "message_id": "message-uuid",
  "user_question": "질문 내용",
  "ai_answer": "AI 답변",
  "feedback_type": "positive",
  "feedback_content": "피드백 내용",
  "user_correction": "수정 제안"
}
```

#### `GET /feedback/stats`
피드백 통계 조회

### ℹ️ 시스템 정보

#### `GET /health`
서버 상태 확인

#### `GET /info`
시스템 정보 조회

## 🌐 프론트엔드 연동 가이드

### 1. Google 로그인 구현

```javascript
// Google 로그인 버튼 클릭
function loginWithGoogle() {
    window.location.href = 'http://localhost:8001/auth/google';
}

// 콜백 처리
function handleGoogleCallback() {
    const urlParams = new URLSearchParams(window.location.search);
    const token = urlParams.get('access_token');
    
    if (token) {
        localStorage.setItem('access_token', token);
        fetchUserInfo(token);
    }
}

// 사용자 정보 조회
async function fetchUserInfo(token) {
    const response = await fetch('http://localhost:8001/auth/me', {
        headers: {
            'Authorization': `Bearer ${token}`
        }
    });
    
    if (response.ok) {
        const user = await response.json();
        console.log('사용자 정보:', user);
    }
}
```

### 2. 챗봇 API 호출

```javascript
async function sendMessage(message) {
    const token = localStorage.getItem('access_token');
    
    const response = await fetch('http://localhost:8001/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify({
            prompt: message,
            use_claude: true
        })
    });
    
    if (response.ok) {
        const data = await response.json();
        return data.response;
    } else if (response.status === 401) {
        // 토큰 만료
        localStorage.removeItem('access_token');
        window.location.href = '/login';
    }
}
```

### 3. 검색 기능 구현

```javascript
async function searchQuestions(query) {
    const response = await fetch(
        `http://localhost:8001/search?query=${encodeURIComponent(query)}&limit=10`
    );
    
    if (response.ok) {
        const data = await response.json();
        return data.results;
    }
}
```

## 📊 검색 점수 계산 방식

- **정확한 키워드 매칭**: 5점
- **부분 키워드 매칭**: 2점
- **질문 유사도**: 최대 1점
- **답변 유사도**: 최대 0.5점

## 🔧 Google OAuth 설정 방법

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
3. 환경 변수 설정 (위의 환경 변수 섹션 참고)
4. Build Command: `pip install -r requirements.txt`
5. Start Command: `gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`

### Docker 배포

```bash
# 이미지 빌드
docker build -t lionhelper -f Dockerfile.combined .

# 컨테이너 실행
docker run -p 8001:8001 --env-file .env lionhelper
```

## 📈 성능 특징

### 키워드 기반 응답
- 응답 시간: < 100ms
- 정확도: 95%+
- 지원 주제: 47개 카테고리

### Claude AI 응답
- 응답 시간: 1-3초
- 모델: claude-3-haiku-20240307
- 한국어 지원: ✅
- 컨텍스트 이해: ✅

## 🗄️ 데이터베이스 스키마

### sessions
- id (VARCHAR): 세션 ID
- title (VARCHAR): 세션 제목
- created_at (TIMESTAMP): 생성 시간
- updated_at (TIMESTAMP): 수정 시간

### messages
- id (VARCHAR): 메시지 ID
- session_id (VARCHAR): 세션 ID (FK)
- role (VARCHAR): 역할 (user/assistant)
- content (TEXT): 메시지 내용
- response_type (VARCHAR): 응답 타입
- model_used (VARCHAR): 사용된 모델
- created_at (TIMESTAMP): 생성 시간

### users
- id (VARCHAR): 사용자 ID
- email (VARCHAR): 이메일 (UNIQUE)
- name (VARCHAR): 이름
- picture (TEXT): 프로필 사진 URL
- created_at (TIMESTAMP): 가입 시간
- last_login (TIMESTAMP): 마지막 로그인

### slack_issues
- id (VARCHAR): 이슈 ID
- project (VARCHAR): 프로젝트명
- issue_type (VARCHAR): 이슈 타입
- author (VARCHAR): 작성자
- content (TEXT): 이슈 내용
- raw_message (TEXT): 원본 메시지
- channel_id (VARCHAR): 채널 ID
- timestamp (VARCHAR): 타임스탬프
- slack_ts (VARCHAR): 슬랙 타임스탬프 (UNIQUE)
- created_at (TIMESTAMP): 생성 시간

### answer_feedback
- id (VARCHAR): 피드백 ID
- session_id (VARCHAR): 세션 ID (FK)
- message_id (VARCHAR): 메시지 ID (FK)
- user_question (TEXT): 사용자 질문
- ai_answer (TEXT): AI 답변
- feedback_type (VARCHAR): 피드백 타입
- feedback_content (TEXT): 피드백 내용
- user_correction (TEXT): 사용자 수정
- created_at (TIMESTAMP): 생성 시간

### improvement_logs
- id (VARCHAR): 로그 ID
- issue_type (VARCHAR): 이슈 타입
- original_answer (TEXT): 원본 답변
- improved_answer (TEXT): 개선된 답변
- improvement_reason (TEXT): 개선 이유
- created_at (TIMESTAMP): 생성 시간

## 🤝 기여하기

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 📞 문의

프로젝트에 대한 문의사항이 있으시면 GitHub Issues를 생성해주세요.

## 🙏 감사의 말

멋쟁이사자처럼 K-Digital Training 부트캠프를 지원하는 모든 분들께 감사드립니다.
