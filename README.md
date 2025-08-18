# 🤖 한국어 AI 챗봇

한국어에 특화된 AI 챗봇 서비스입니다. 친근하고 유능한 AI 어시스턴트와 자연스러운 한국어 대화를 나눌 수 있습니다.

## ✨ 주요 기능

- 🇰🇷 **한국어 특화**: 한국어에 최적화된 AI 모델 사용
- 💬 **자연스러운 대화**: 친근하고 예의 바른 톤으로 소통
- 🎨 **아름다운 UI**: 모던하고 직관적인 웹 인터페이스
- 📱 **반응형 디자인**: 모바일과 데스크톱 모두 지원
- ⚡ **빠른 응답**: 최적화된 모델로 빠른 응답 속도
- 🔧 **쉬운 배포**: Render.com 원클릭 배포 지원

## 🚀 기술 스택

- **Backend**: FastAPI, Python 3.11
- **AI Model**: KoAlpaca-Polyglot-5.8B (한국어 최적화)
- **Frontend**: HTML5, CSS3, JavaScript
- **Deployment**: Render.com
- **Hardware**: Apple M4 Pro (24GB RAM) 최적화

## 📦 설치 및 실행

### 로컬 개발 환경

1. **저장소 클론**
```bash
git clone <repository-url>
cd helper
```

2. **가상환경 생성 및 활성화**
```bash
python -m venv venv
source venv/bin/activate  # macOS/Linux
# 또는
venv\Scripts\activate  # Windows
```

3. **의존성 설치**
```bash
pip install -r requirements.txt
```

4. **서버 실행**
```bash
python main.py
```

5. **브라우저에서 접속**
```
http://localhost:8000
```

### Render.com 배포

1. **GitHub에 코드 푸시**
2. **Render.com에서 새 Web Service 생성**
3. **GitHub 저장소 연결**
4. **자동 배포 완료**

## 🎯 사용법

1. 웹 브라우저에서 챗봇 페이지 접속
2. 하단 입력창에 메시지 입력
3. Enter 키 또는 전송 버튼 클릭
4. AI의 응답 확인
5. 제안된 질문 버튼으로 빠른 시작 가능

## 🔧 설정 옵션

### 모델 설정
- **모델**: `beomi/KoAlpaca-Polyglot-5.8B`
- **메모리 할당**: 20GB (M4 Pro 24GB RAM 기준)
- **생성 토큰**: 최대 1024개
- **온도**: 0.7 (창의성과 일관성의 균형)

### 환경 변수
```bash
PORT=8000  # 서버 포트
PYTHON_VERSION=3.11  # Python 버전
```

## 📊 성능 최적화

- **메모리 최적화**: M4 Pro 24GB RAM에 맞춘 설정
- **모델 양자화**: float16 사용으로 메모리 효율성 향상
- **배치 처리**: torch.no_grad() 사용으로 추론 속도 개선
- **반복 방지**: repetition_penalty 적용

## 🛠️ API 엔드포인트

### POST /chat
챗봇과 대화를 수행합니다.

**요청 예시:**
```json
{
  "prompt": "안녕하세요!",
  "max_new_tokens": 1024,
  "temperature": 0.7,
  "top_p": 0.9
}
```

**응답 예시:**
```json
{
  "response": "안녕하세요! 반갑습니다. 무엇을 도와드릴까요?",
  "model": "beomi/KoAlpaca-Polyglot-5.8B",
  "status": "success"
}
```

### GET /health
서버 상태를 확인합니다.

### GET /info
모델 정보를 반환합니다.

## 🎨 UI 특징

- **모던한 디자인**: 그라데이션과 그림자 효과
- **애니메이션**: 부드러운 전환 효과
- **타이핑 인디케이터**: AI 응답 생성 중 시각적 피드백
- **제안 질문**: 빠른 시작을 위한 버튼
- **반응형 레이아웃**: 모든 디바이스 지원

## 🔒 보안 및 안정성

- **입력 검증**: 사용자 입력에 대한 검증
- **오류 처리**: 친화적인 오류 메시지
- **CORS 설정**: 웹 브라우저 호환성
- **메모리 관리**: 효율적인 리소스 사용

## 🤝 기여하기

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the Branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📝 라이선스

이 프로젝트는 MIT 라이선스 하에 배포됩니다.

## 📞 지원

문제가 있거나 제안사항이 있으시면 이슈를 생성해주세요.

---

**한국어 AI 챗봇**으로 더 나은 AI 경험을 시작해보세요! 🚀
