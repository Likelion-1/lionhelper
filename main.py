
import os
import time
import uuid
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
import uvicorn
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Optional, List, Dict, Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from anthropic import Anthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from fastapi import FastAPI, HTTPException, Request, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from jose import JWTError, jwt
from passlib.context import CryptContext

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 비밀번호 해싱
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 설정
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-change-this-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30

# Google OAuth 설정
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "your-google-client-id")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "your-google-client-secret")

# 슬랙 API 설정
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_CHANNEL_ID = "C08M47TM2KH"  # 지정된 채널 ID
slack_client = WebClient(token=SLACK_BOT_TOKEN) if SLACK_BOT_TOKEN else None

# google_oauth = GoogleOAuth2(  # 임시 비활성화
#     client_id=GOOGLE_CLIENT_ID,
#     client_secret=GOOGLE_CLIENT_SECRET,
#     redirect_uri="http://localhost:8001/auth/google/callback"
# )

# JWT 토큰 검증 함수
def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None

# JWT 토큰 의존성
security = HTTPBearer()

def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """현재 로그인한 사용자 정보 가져오기"""
    token = credentials.credentials
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="유효하지 않은 토큰입니다",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload

# Anthropic Claude API 설정
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
USE_CLAUDE = os.getenv("USE_CLAUDE", "true").lower() == "true"

# Ollama 설정 (백업용)
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "GPT-OSS-20B")

# PostgreSQL 데이터베이스 설정
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://username:password@localhost:5432/chat_history")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "chat_history")
DB_USER = os.getenv("DB_USER", "username")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

def get_db_connection():
    """PostgreSQL 데이터베이스 연결 함수"""
    try:
        if DATABASE_URL and DATABASE_URL != "postgresql://username:password@localhost:5432/chat_history":
            return psycopg2.connect(DATABASE_URL)
        else:
            return psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                database=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
    except psycopg2.Error as e:
        logger.error(f"데이터베이스 연결 오류: {e}")
        raise

# GPTAPIClient 클래스 제거됨 - Claude 전용 시스템으로 전환


class ClaudeAPIClient:
    def __init__(self, api_key):
        """Claude API 클라이언트 초기화"""
        if not api_key:
            raise ValueError("Anthropic API 키가 제공되지 않았습니다.")
        
        self.logger = logging.getLogger(__name__)
        self.model = "claude-3-haiku-20240307"  # 가장 빠르고 저렴한 모델
        
        # Anthropic 클라이언트 초기화
        self.client = Anthropic(api_key=api_key)
        
        self.logger.info(f"ClaudeAPIClient 초기화 완료 (모델: {self.model})")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        reraise=True
    )
    def make_request(self, prompt: str, max_tokens: int = 1000) -> Optional[str]:
        """Claude API 요청 수행"""
        self.logger.info(f"Claude API 요청 시작 (프롬프트 길이: {len(prompt)} 문자)")
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=0.7,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            if response and response.content and len(response.content) > 0:
                result = response.content[0].text
                self.logger.info("Claude API 요청 성공")
                return result
            else:
                self.logger.error("Claude API 응답이 비어있음")
                raise Exception("Claude API 응답이 비어있습니다")
                
        except Exception as e:
            self.logger.error(f"Claude API 요청 실패: {str(e)}")
            raise
    
    def test_connection(self) -> bool:
        """Claude API 연결 테스트"""
        try:
            self.logger.info("Claude API 연결 테스트 시작")
            result = self.make_request("안녕하세요", max_tokens=10)
            return bool(result)
        except Exception as e:
            self.logger.error(f"Claude API 연결 테스트 실패: {str(e)}")
            return False

# Claude 클라이언트 초기화 (API 키가 있는 경우에만)
claude_client = None
if ANTHROPIC_API_KEY:
    try:
        claude_client = ClaudeAPIClient(ANTHROPIC_API_KEY)
        logger.info("Claude 클라이언트 초기화 완료")
    except Exception as e:
        logger.warning(f"Claude 클라이언트 초기화 실패: {str(e)}")

# GPT 관련 코드 제거됨 - Claude 전용 시스템

# 데이터베이스 초기화
def init_database():
    """PostgreSQL 데이터베이스 초기화"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 세션 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR(255) PRIMARY KEY,
                title VARCHAR(500) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 메시지 테이블
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id VARCHAR(255) PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                role VARCHAR(50) NOT NULL,
                content TEXT NOT NULL,
                response_type VARCHAR(100),
                model_used VARCHAR(100),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id)
            )
        ''')
        
        # 사용자 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id VARCHAR(255) PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                picture TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 슬랙 이슈 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS slack_issues (
                id VARCHAR(255) PRIMARY KEY,
                project VARCHAR(255) NOT NULL,
                issue_type VARCHAR(100) NOT NULL,
                author VARCHAR(255) NOT NULL,
                content TEXT NOT NULL,
                raw_message TEXT NOT NULL,
                channel_id VARCHAR(255),
                timestamp VARCHAR(255),
                slack_ts VARCHAR(255) UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    
        # 답변 피드백 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS answer_feedback (
                id VARCHAR(255) PRIMARY KEY,
                session_id VARCHAR(255) NOT NULL,
                message_id VARCHAR(255) NOT NULL,
                user_question TEXT NOT NULL,
                ai_answer TEXT NOT NULL,
                feedback_type VARCHAR(50) NOT NULL, -- 'positive', 'negative', 'correction'
                feedback_content TEXT,
                user_correction TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES sessions (id),
                FOREIGN KEY (message_id) REFERENCES messages (id)
            )
        ''')
        
        # 답변 개선 로그 테이블 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS improvement_logs (
                id VARCHAR(255) PRIMARY KEY,
                issue_type VARCHAR(100) NOT NULL,
                original_answer TEXT NOT NULL,
                improved_answer TEXT NOT NULL,
                improvement_reason TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        logger.info("PostgreSQL 데이터베이스 초기화 완료")
        
    except psycopg2.Error as e:
        logger.error(f"데이터베이스 초기화 오류: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()

# 데이터베이스 초기화는 앱 시작 시점에 실행 (지연 초기화)

# QA 데이터베이스 (키워드 기반 빠른 응답)
QA_DATABASE = {
    "줌": {
        "keywords": ["줌", "zoom", "배경", "화면", "설정"],
        "question": "배경 화면도 설정해야 하나요? 어떻게 하나요?",
        "answer": "해당 사항은 수강생 공식 안내 페이지(노션) 내 K-Digital Training 수강준비 가이드에 자세히 나와있음을 안내드립니다. 확인하시고 모두 설정 부탁드립니다."
    },
    "훈련장려금": {
        "keywords": ["훈련장려금", "수령", "계좌", "정보", "안보임"],
        "question": "훈련장려금 수령 계좌 정보가 안보이면 어떻게 하나요?",
        "answer": "개강전이라면, 고용 24 로그인 → 온라인 수강신청 → 수강신청 상세보기 클릭\n개강 이후라면, 부트캠프별로 안내된 '구글폼 링크(훈련장려금 변경 구글폼 신청링크)'를 통해 변경 정보 제출"
    },
    "출결_외출": {
        "keywords": ["출결", "외출", "국민취업지원제도", "고용복지센터", "상담", "공적", "결석"],
        "question": "국민취업지원제도 관련으로 고용복지센터와 상담이 필요한데 이 경우 외출로 다녀오면 되나요? 아니면 공적인 결석으로 인정해주나요?",
        "answer": "해당 사유로 공적인 결석은 어려우며, '외출' 또는 '조퇴' QR처리 필요"
    },
    "화장실": {
        "keywords": ["화장실", "자유롭게", "장시간", "자리", "비움"],
        "question": "수업 중에 화장실은 자유롭게 다녀와도 되나요?",
        "answer": "다만 장시간 자리를 비우시는 경우에는 부트캠프 담당자님의 DM이 갈 수 있음을 인지해주시기 바랍니다."
    },
    "기초클래스_출결": {
        "keywords": ["기초클래스", "온라인", "출결", "등록", "훈련생", "등록되지 않는"],
        "question": "기초클래스 온라인 출결 등록 시, 등록되지 않는 훈련생으로 떠서 온라인 출결 등록이 불가합니다. 어떻게 수정하면 될까요?",
        "answer": "- 먼저 생년월일성별이 ex) 97010102 형태로 입력되어 있는지 확인해주세요.\n- 훈련생성명, 훈련일자, 과정코드, 훈련과정회차에 문제가 없는지 확인해 주세요.\n- 전부 이상이 없는데도 출결 등록이 불가할 경우 전산문제로 PA팀으로 문의해 주세요!"
    },
    "내일배움카드": {
        "keywords": ["내일배움카드", "이슈", "수강생", "등록", "늦게", "정상", "출결"],
        "question": "최근에 개강을 해서, 내일배움카드 이슈로 인해 금일 9시 넘어서 수강생 등록이 된 경우 금일자 출결을 정상 출결로 변경이 가능한 부분일까요?",
        "answer": "내일배움카드 발급이 늦어져서 등록이 늦게 된 경우 정상 출결 정정은 어려우며, 늦게라도 QR 입실 체크를 해주셔야 합니다."
    },
    "사랑니": {
        "keywords": ["사랑니", "발치", "공결", "치과", "진료"],
        "question": "사랑니 발치도 공결 인정이 될까요?",
        "answer": "치과진료 항목(스케일링, 사랑니 발치, 치아 발치, 교정 등)은 공결 신청이 불가합니다."
    },
    "입원": {
        "keywords": ["입원", "격리", "진단서", "매일", "제출"],
        "question": "병원에서 당분간 입원 혹은 격리조치를 받았는데, 공결 신청을 위한 진단서를 매일 받아서 제출해야 되나요?",
        "answer": "- 입원으로 인한 공결신청 시, 입퇴원확인서를 제출해 주시면 됩니다."
    },
    "수료_출석률": {
        "keywords": ["수료", "출석", "몇일", "가능"],
        "question": "몇 일 이상 출석해야 수료가 가능할까요?",
        "answer": "- 전체 훈련일수에서 80%이상 출석을 하셔야 수료가 가능합니다."
    },
    "단위기간_결석": {
        "keywords": ["단위기간", "결석", "몇번", "훈련장려금"],
        "question": "단위기간에 결석은 몇 번 할 수 있나요?",
        "answer": "- 단위기간 일수에서 80% 이상 출석하셔야 훈련장려금 수령이 가능합니다.\n- 예를 들어 단위기간 수업 일수가 18일이면 => 18 * 80% => 14.4(올림) => 15이상 출석해 주셔야 합니다."
    },
    "수료후_취업": {
        "keywords": ["수료일수", "취업", "처리", "서류"],
        "question": "수료일수를 다 채우고 취업을 하게 될 경우 어떻게 처리가 되는 걸까요?, 필요한 서류가 있을까요?",
        "answer": "- 80% 이상 수업 수강 후 취업이 되실 경우 수료 후 취업으로 처리되며, 근로계약서와 중도포기 서약서를 제출해 주셔야 합니다."
    },
    "노트북_반납": {
        "keywords": ["노트북", "반납", "절차", "포장", "픽업"],
        "question": "노트북 반납 절차는 어떻게 진행될까요?",
        "answer": "(한국렌탈에서 진행하는 경우, 아래와 같은 프로세스로 진행)\n[노트북 반납 준비 프로세스]\n- 운영진에게 반납 가능 일정 / 집 주소 / 연락처 공유\n- 반납 일자에 맞춰 픽업 받았던 포장 그대로 포장 진행 (포장지 없을 경우 운영진에게 연락) → 포장 누락으로 인해 노트북 파손이 될 경우 본인에게 비용 청구됨\n- 포장 후 반납 일자에 맞춰 노트북 회수 준비\n- 배송기사님이 일자에 맞춰 노트북 회수\n\n[운영진에게 전달할 사항 - 00월00일까지 공유해 주세요]\n- 반납 가능한 주소 및 연락처\n- 포장지 필요 여부 (포장지 분실로 인해 필요할 경우, 배송기사님이 포장지를 먼저 배송 후 픽업하실 예정)\n- 배송일자 확인 : 00월 00일"
    },
    "외출_조퇴_지각": {
        "keywords": ["외출", "조퇴", "지각", "결석", "처리", "3번"],
        "question": "외출이나 조퇴 지각 3번이 결석 1번으로 처리 되나요? 외출 시간은 상관 없나요?",
        "answer": "- 지각 + 조퇴 + 외출 = 3회 → 결석 1회와 같습니다.\n- 지각,조퇴,외출의 경우 1일 훈련 시간의 50% 초과 시 결석 처리 됩니다."
    },
    "이사_공결": {
        "keywords": ["이사", "공결", "처리", "인정"],
        "question": "이사의 경우 공결 처리 가능한가요?",
        "answer": "출석 인정 가능한 공결의 경우는 첨부한 사진과 같은 상황에만 공결 처리가 가능합니다!(공결인정사유 표 첨부)\n이사의 경우에는 공결인정사유에 포함되지 않으므로 수업에 참여하지 못하시게 될 경우 결석/조퇴 등으로 처리 됩니다."
    },
    "입실QR_스크린샷": {
        "keywords": ["입실QR", "스크린샷", "컴퓨터", "멈춤", "캠"],
        "question": "9시에 입실QR은 찍었으나, 스크린샷 찍을 때 컴퓨터가 멈춰서 캠을 못켰어요.",
        "answer": "항상 HRD QR이 가장 우선시 되며, QR확인 오류가 있거나 전산상으로 입/퇴실에 대한 증빙이 필요한 경우 줌 스크린샷이 가장 중요한 증빙자료로 쓰이고 있기에 스크린샷도 잘 찍어주셔야 합니다.\n오늘 건은 입실 QR은 잘 찍어주셔서 해당 내용 남겨놓겠으나, 이후로는 누락되지 않도록 카메라 미리 확인 해주시어 스크린샷 잘 찍어주시길 바랍니다."
    },
    "OT_출결": {
        "keywords": ["OT", "참여", "어려운", "출결", "반영", "내용"],
        "question": "첫날 OT 참여가 어려운데, OT 날 출결도 동일하게 출석 반영이 되나요? OT 관련 내용을 추가로 따로 안내 받을 수 있을까요?",
        "answer": "OT 또한 수강기간에 포함 되기 때문에 결석 시, 출결에 동일하게 반영됩니다.\nOT에 참여하지 못하신 분들은 따로 추가 OT 진행하고 있습니다."
    },
    "맥북_고장": {
        "keywords": ["맥북", "고장", "수리", "일주일", "수업"],
        "question": "갖고있는 맥북이 고장났어요. 수리 기간이 일주일정도 소요된다고 하는데, 그동안 수업을 어떻게 들어야 할까요?",
        "answer": "- 거주하시는 지역이 어디신가요?\n- 당사 방문하시어 맥북 대여를 해드릴 수 있는 상황입니다. 단기임대(최소 1개월)로도 대여진행이 가능합니다."
    },
    "기초클래스_결석": {
        "keywords": ["기초클래스", "수강", "완료", "HRD", "결석"],
        "question": "기초클래스 수강을 완료했는데, HRD에서 결석으로 뜹니다.",
        "answer": "기초클래스의 경우 출결을 수기로 등록해야하기 때문에 출결 반영까지 최대 2주정도 소요될 수 있습니다."
    },
    "단위기간_지각": {
        "keywords": ["단위기간", "지각", "적용", "카운트"],
        "question": "A 단위기간 때 지각 2개 있다고 가정했을 때 B 단위기간 때 지각 1개 찍으면 B 단위기간때 결석 찍히는걸까요?",
        "answer": "세 번째 카운트 되는 시점의 단위기간에 적용됩니다. (예시의 경우, B 단위기간)"
    },
    "훈련장려금_입금": {
        "keywords": ["훈련장려금", "지난", "단위기간", "언제", "입금"],
        "question": "지난 단위기간 훈련장려금은 언제 입금되나요?",
        "answer": "훈련장려금 신청은 본 과정의 모든 훈련생의 출결 정정 및 근로 형태가 확인된 이후 진행되기 때문에 지급까지 최대 한 달이 소요될 수 있습니다."
    },
    "조기취업": {
        "keywords": ["조기취업", "중도포기", "불이익", "내일배움카드"],
        "question": "과정 수강 중에 취업하게 되면 어떤 불이익이 있나요?",
        "answer": "조기취업으로 인한 중도포기 처리되며, 내일배움카드 잔액 차감 및 5년 이내 KDT 과정 수강이 불가합니다."
    },
    "공결_횟수": {
        "keywords": ["공결", "몇번", "사용", "질병", "횟수"],
        "question": "공결 몇 번까지 사용할 수 있나요?",
        "answer": "질병 공결에만 횟수가 제한되어 있고, 전체 훈련일수의 10%까지만 사용 가능합니다."
    },
    "계좌_변경": {
        "keywords": ["훈련장려금", "계좌", "변경", "은행", "번호"],
        "question": "훈련장려금 수령 계좌를 변경하고 싶은데 어떻게 변경하나요?",
        "answer": "행정 채널에 변경하고자 하는 은행과 계좌 번호를 행정 담당자님께 제출 부탁드립니다."
    },
    "공결_출석률": {
        "keywords": ["예비군", "병원", "공결", "출석률", "포함"],
        "question": "예비군, 병원 방문 등으로 인한 공결은 출석률에 포함되는 건가요?",
        "answer": "네. 공결은 정상출석과 동일하게 처리되기 때문에 출석률에 반영됩니다."
    },
    "HRD_로그인": {
        "keywords": ["HRD", "앱", "출석", "오류", "로그인"],
        "question": "HRD 앱으로 출석 진행하려고 하는데, 계속 오류가 발생해서 로그인이 불가합니다. 어떻게 해야할까요?",
        "answer": "인증수단이 아닌 아이디로 로그인 시도, 어플 재설치 후 로그인 시도 부탁드립니다."
    },
    "해외출국": {
        "keywords": ["해외출국", "해외여행", "교육", "불가", "결석"],
        "question": "교육 참여 중 해외 출국이 불가하다고 안내 받았는데, 교육 듣는 과정 중에 해외여행도 불가한가요?",
        "answer": "결석 처리하시거나 휴강 및 주말 활용하여 해외여행 다녀오시는 건 가능합니다."
    },
    "입실QR_누락": {
        "keywords": ["입실QR", "깜빡", "누락", "출결정정", "개인과실"],
        "question": "오늘 입실QR 찍는 걸 잊어서 정상 출석 처리가 안 될 것 같은데 입퇴실 스크린샷에 문제가 없다면 출석으로 출결정정 가능할까요?!",
        "answer": "개인 과실로 인해 발생한 입실 QR 누락이기 때문에 해당 건은 출결정정 불가합니다.\n앞으로는 알람을 맞춰두시는 등 누락 없도록 QR체크 잘 부탁드립니다! : )"
    },
    "국민취업지원제도_장려금": {
        "keywords": ["국민취업지원제도", "국취제", "훈련장려금", "동시", "받기"],
        "question": "국민취업제도장려금이랑 훈련장려금을 동시에 받을 수 있나요?",
        "answer": "네. 국민취업제도 (국취제) 장려금과 훈련장려금은 별도이기에 동시에 받으실 수 있으십니다."
    },
    "당일_출결": {
        "keywords": ["입실", "정상", "HRD", "결석", "퇴실"],
        "question": "오늘 입실을 정상적으로 했는데 HRD 어플 내 에서는 결석으로 나와요",
        "answer": "당일 출결의 경우 퇴실까지 완전하게 찍혀야 당일 출결이 출석으로 인정됩니다. 아직 수업 중이시면 결석으로 나오는게 정상입니다 :)"
    },
    "해외_수업참여": {
        "keywords": ["해외여행", "수업시간", "참여", "가능", "접속"],
        "question": "해외 여행을 가지만 수업시간 내 일정이 없어 참여가 가능할 거 같은데 참여해도 될까요?",
        "answer": "KDT 교육과정은 국내에서만 제공 되는 교육과정이기에 해외에서는 절대적으로 접속이 불가합니다. 해외에서 접속하셔서 이에 따른 불이익은 당사자 본인에게 있습니다"
    },
    "장소_이동": {
        "keywords": ["훈련", "이동", "장소", "불가피", "교육매니저"],
        "question": "훈련 중 이동을 하게 되면 어떻게 해야 하나요?",
        "answer": "KDT 훈련 중 장소 이동은 불가합니다. 장소이동이 불가피한 상황이시라면 담당 교육 매니저께 내용을 먼저 말씀해주셔야 불이익이 발생하지 않습니다."
    },
    "QR코드_개인소지": {
        "keywords": ["입퇴실", "QR코드", "개인", "보관", "소지"],
        "question": "입퇴실 QR코드를 개인적으로 보관해도 될까요?",
        "answer": "QR코드는 훈련기관에서 제공을 하는 것이므로 개인 소지가 절대적으로 불가합니다. 개인 소지 및 사용으로 발생하는 모든 불이익은 당사자에게 있습니다."
    },
    "단위기간_정의": {
        "keywords": ["단위기간", "무엇", "1달", "개강"],
        "question": "단위기간이 무엇인가요?",
        "answer": "단위기간은 교육 시작을 기점으로 1달을 말합니다.\n예를 들어 1월5일 개강시 1월 5일부터 2월 4일까지가 첫 번째 단위기간이 됩니다."
    },
    "줌_참여필수": {
        "keywords": ["줌", "참여", "필수", "송출", "출석체크"],
        "question": "수업에 꼭 줌 참여를 해야하나요?",
        "answer": "네, 수업이 진행되는 9시부터 18시까지 꼭 줌에 참여해주셔야 합니다.\n줌은 수업 송출용도로도 사용되지만 수강생들의 출석 체크로도 사용되는 중요한 툴입니다.\n쉬는시간과 점심시간 외 줌에 참여를 하지 않으시거나 캠을 끄시면 결석/지각 처리가 되며,\n훈련장려금 부정수급까지 연결될 수 있는 중요한 사안입니다."
    },
    "훈련장려금_금액": {
        "keywords": ["훈련장려금", "얼마", "일일", "지급", "계산"],
        "question": "훈련장려금은 얼마인가요?",
        "answer": "훈련장려금은 하루 수업을 모두 참여시 일일 15,800원이 지급됩니다.\n다만 지각/조퇴/외출/결석시 15,800원의 훈련장려금 지급이 어려우며,\n월 별 훈련장려금은 단위기간 별 \"정상 출석일 * 15,800원\"으로 계산합니다."
    },
    "처방전_서류": {
        "keywords": ["처방전", "서류", "인정", "진료확인서", "진단서"],
        "question": "병원 방문시 처방전은 서류 인정이 어려운가요?",
        "answer": "처방전은 서류 인정이 어렵습니다.\n질병명 혹은 질병코드가 기재된 진료확인서, 입퇴원 확인서, 진단서로 제출 부탁드립니다."
    },
    "녹화본_제공": {
        "keywords": ["녹화본", "제공", "지각", "외출", "조퇴", "결석"],
        "question": "익일 지각/외출/조퇴/결석 예정인데, 녹화본 제공이 가능한가요?",
        "answer": "멋쟁이사자처럼 부트캠프는 실시간 온라인 강의로 진행되기 때문에, 녹화본 제공은 따로 진행되지 않습니다. 강사님이 올려주신 교안 확인 부탁드립니다."
    },
    "수강증명서_발급": {
        "keywords": ["실업급여", "출석부", "수강증명서", "급해", "발급"],
        "question": "실업급여 제출용으로 급해서 그러는데 오늘 중으로 발급 가능한가요?",
        "answer": "해당 내용은 멋쟁이사자처럼 교육행정 디스코드 서버에서 훈련생 분이 수강하고 있는 부트캠프 카테고리에서 서류요청 란에 작성해주셔야 합니다. 원칙적으로 영업일 기준 2-3일 이전에 작성해주셔야 합니다."
    },
    "퇴실QR_정정": {
        "keywords": ["퇴실QR", "안찍음", "정정", "개인부주의"],
        "question": "퇴실 QR 안 찍었는데 정정 가능한가요?",
        "answer": "우선, 원칙적으로 개인부주의 항목에 해당하기 때문에 불가능합니다.\n\n다만 1단위기간인 경우 (개강 이후 1개월 이내) QR 미숙 건으로 정정신청이 가능합니다.\n정정 증빙자료로는 훈련생 분이 해당일 입실/중간/퇴실 스크린샷에 눈•코•입 이 모두 명확하게 나와야하며, 09:00 - 18:00 줌 접속기록이 필요합니다."
    },
    "실업급여_국취제": {
        "keywords": ["실업급여", "국취제", "서류", "제출", "공가"],
        "question": "실업급여 서류 제출 방문 / 국취제 서류 제출 방문으로 인한 부재는 공가신청이 가능한가요?",
        "answer": "해당 내용은 공가신청이 불가능합니다. 자세한 사항은 OT 때 안내드린 공가인정신청표를 확인해주세요."
    },
    "프로젝트_수정": {
        "keywords": ["프로젝트", "제출", "수정", "링크", "LMS"],
        "question": "프로젝트 제출 이후 수정 건이 생겨, 링크를 수정하고 싶습니다. 가능할까요?",
        "answer": "네, 가능합니다. 자세한 사항은 수강하고 있는 부트캠프 담당 매니저 님에게 문의 부탁드립니다."
    },
    "졸업식_공결": {
        "keywords": ["졸업식", "공결", "신청", "휴가"],
        "question": "졸업식도 공결신청이 가능한가요?",
        "answer": "졸업식은 공결인정 사유에 포함되지 않으며, 휴가신청이 가능한 과정에서는 휴가신청 후 다녀올 수 있습니다. 휴가가 없는 과정의 경우, 공결 불인정되니 참고 부탁드립니다."
    },
    "조모상_공결": {
        "keywords": ["조모상", "공결", "3일", "사유발생일", "주말"],
        "question": "금요일에 조모상을 당했습니다. 공결인정이 3일이라고 나와있는데, 차주 월~화까지 공결로 인정되나요?",
        "answer": "조모상의 경우, 공결은 사유발생일로부터 3일까지 인정됩니다. 단, 주말은 기산하지 않으므로 차주 월요일부터는 공결로 인정되지 않습니다."
    },
    "훈련장려금_지급시기": {
        "keywords": ["훈련장려금", "언제", "받기", "단위기간", "2주"],
        "question": "훈련장려금은 언제 받을 수 있나요?",
        "answer": "훈련장려금은 해당 과정의 단위기간 마감일을 기준으로 지급까지 2주에서 3주 가량 소요됩니다\n1단위기간의 경우, 확인할 사항이 많아 시간이 다소 소요될 수 있다는 점 참고 부탁드립니다."
    },
    "재학생_맞춤형": {
        "keywords": ["재학생", "맞춤형", "고용서비스", "점프업", "빌드업"],
        "question": "현재 재학생 맞춤형 고용서비스 사업에 참여 중입니다. 훈련장려금 받을 수 있을까요?",
        "answer": "재학생 맞춤형 고용서비스(일명 점프업프로젝트, 빌드업프로젝트)에 참여 중이면서 수당을 지급받고 있는 경우에는 훈련장려금과 중복이 불가합니다. 단, 학교측에서 발급해주는 참여확인서 상에 해당 과정 훈련기간 중 어떠한 수당도 지급받지 않았다는 사실이 증빙되면 훈련장려금 지급이 가능합니다."
    },
    "사업체_정리": {
        "keywords": ["사업체", "정리", "자영업자", "폐업", "증명원"],
        "question": "사업체를 정리했습니다. 훈련장려금을 받을 수 있을까요?",
        "answer": "현재 시스템 상에 (영세)자영업자로 등록된 경우, 사업자등록증을 갖고 있다는 것만으로도 훈련장려금이 부지급 처리 됩니다.\n단, 사업체를 정리하여 폐업사실증명원을 제출하면 폐업일 이후부터 일할계산되어 지급이 가능합니다."
    },
    "웹캠_필요": {
        "keywords": ["웹캠", "필요", "꺼도", "개강전", "구비"],
        "question": "웹캠이 필요한가요? 꺼놔도 되나요? (멋사에서는 당연하다고 생각하여 상페에 웹캠구비 안써있음)",
        "answer": "오프라인과 동일하게 진행하는 온라인 수업이기때문에 '개강 전' 반드시 웹캠은 구비하셔야 하고 불가할 시 폰이나 태블릿 으로라도 접속을 해야 함을 안내"
    },
    "줌_두개접속": {
        "keywords": ["강의", "수강용", "PC", "실습용", "데스크탑", "두개"],
        "question": "강의 수강용 PC랑 실습용 데스크탑 두개로 줌 접속해도 되나요?",
        "answer": "수강용 PC를 별도로 둘 경우 줌 접속은 '홍길동 - 수강용'으로 접속해 달라고 답변"
    },
    "쉬는시간_카메라": {
        "keywords": ["쉬는시간", "카메라", "꺼도", "얼굴", "노출"],
        "question": "쉬는 시간에 카메라 꺼도 되나요?",
        "answer": "된다고 답변 다만, 모든 수업시간에는 얼굴 노출 필수를 안내"
    },
    "교재_다름": {
        "keywords": ["교재", "배송", "강의내용", "다른", "참고자료"],
        "question": "교재 배송받은거랑 강의내용이 다른데요?",
        "answer": "배송된 교재는 참고자료로 사용하는 용도이며, 주 강의자료는 주강사님이 작성해주시는 내용으로 강의합니다."
    },
    "질의응답": {
        "keywords": ["수업", "마치고", "궁금한", "디코", "물어봐도"],
        "question": "수업 마치고 궁금한거 생기면 디코에 물어봐도 되나요?",
        "answer": "수업관련 문의는 수업시간 이내를 활용해 주세요. 야간 답변은 어렵습니다."
    },
    "평가_설문": {
        "keywords": ["평가", "설문", "프로젝트", "제출", "기간"],
        "question": "평가, 설문, 프로젝트 제출 기간 지난 후에 다시하고 싶어요.",
        "answer": "기간이 지난후는 불가 함을 안내"
    },
    "수료생_DB": {
        "keywords": ["훈련생", "수료생", "DB", "설문조사", "응답"],
        "question": "훈련생/수료생 DB 설문조사에 꼭 응답해야 하나요?",
        "answer": "수료생 DB 설문조사는 수료 후 취업 연계 프로그램 운영을 위한 중요한 기초 자료일 뿐만 아니라, B2B 채용 연계 진행에 있어 꼭 필요한 정보를 취합하는 절차입니다.\n따라서, 다소 번거로우시더라도 설문조사 내 모든 항목에 대해 정확하게 응답해주시면 감사하겠습니다."
    },
    "특강_서류작성": {
        "keywords": ["이력서", "자기소개서", "포트폴리오", "작성", "방법"],
        "question": "이력서, 자기소개서, 포트폴리오 작성 방법을 알려주실 수 있나요?",
        "answer": "2025년 2월 현재 멋사 KDT 수료생을 위한 서류/면접 전형 준비 방법 특강 VOD 자료를 준비 중에 있습니다.\n해당 자료가 준비되는대로 각 교육과정별 디스코드 및 수료생 디스코드(세렝게티)를 통해 관련 사항을 별도 공지 드릴 예정입니다."
    },
    "커리어_상담": {
        "keywords": ["서류", "면접", "준비", "커리어", "코치", "상담"],
        "question": "서류 전형, 면접 전형 준비 과정에서 커리어 코치님의 상담을 받을 수 있나요?",
        "answer": "2025년 2월 현재 멋사 홈페이지 내 LMS 시스템을 활용한 상담 프로그램 신설을 준비하고 있습니다.\n해당 프로그램 운영이 시작되는대로 각 교육과정별 디스코드 및 수료생 디스코드(세렝게티)를 통해 공지 드릴 예정입니다."
    },
    "채용_연계": {
        "keywords": ["멋쟁이사자처럼", "KDT", "수료생", "채용", "연계"],
        "question": "멋쟁이사자처럼 KDT 수료생을 위한 채용 연계 프로그램도 있나요?",
        "answer": "멋사 KDT 수료생을 위해 다양한 회사를 대상으로 채용 연계 기회를 발굴 중에 있으며, 신규 포지션 오픈 시 개별 공지를 진행하고 있습니다.\n따라서, 개별 공지 시 빠르게 지원 절차를 진행할 수 있도록 언제든지 제출 가능한 이력서/자기소개서/포트폴리오를 준비해주시길 부탁 드립니다."
    },
    "인턴십": {
        "keywords": ["멋쟁이사자처럼", "KDT", "수료생", "인턴십", "크로스도메인"],
        "question": "멋쟁이사자처럼 KDT 수료생만을 위한 인턴십 프로그램도 있나요?",
        "answer": "멋사 KDT 부트캠프 중 일부 과정은 수료생 전용 크로스 도메인 인턴십 프로그램을 운영 중에 있습니다.\n구체적인 운영 시기/형태는 기수별로 다르기 때문에 구체적인 사항은 개별 안내 시 해당 공지 내용을 참조해주시면 감사하겠습니다."
    },
    "세렝게티": {
        "keywords": ["취업", "지원", "프로그램", "소식", "공지"],
        "question": "취업 지원 프로그램 소식은 어디로 공지되나요?",
        "answer": "커리어팀 시행 취업지원 프로그램의 경우, 멋사 KDT 수료생 커뮤니티인 디스코드 세렝게티 채널을 통해 가장 우선적으로 공지하고 있습니다.\n향후 다양한 취업 관련 정보도 세렝게티를 통해 공지할 예정이니 KDT 부트캠프 수료 후에는 꼭 세렝게티에 가입해주시길 부탁 드립니다.\n(디스코드 세렝게티 가입 주소 : KDT 부트캠프 수료 시 각 교육과정 담당자를 통해 안내)"
    },
    "휴가": {
        "keywords": ["휴가", "교육기간", "6개월", "한달", "한개"],
        "question": "해당 과정에는 휴가가 있나요? 매일 수업이 진행되는 건가요?",
        "answer": "휴가는 교육 기간 6개월 이상 진행되는 과정에 한하여 한 달에 한 개씩 사용할 수 있습니다.\n자세한 사항은 담당 교육 매니저님께 문의하여 주세요."
    },
    "다시보기": {
        "keywords": ["복습", "다시보기", "제공", "KDT", "지침"],
        "question": "복습을 하고 싶은데 다시보기 제공이 되나요?",
        "answer": "KDT 지침 상 다시보기 제공이 어렵습니다. 꼭 해당 교육 시간에 출석하여 교육을 들어주세요."
    },
    "노트북_대여": {
        "keywords": ["노트북", "대여", "어떻게", "개강일", "일주일"],
        "question": "노트북 대여는 어떻게 이루어지나요?",
        "answer": "개강일 기준 일주일 이내로 노트북 대여 신청을 받아 신청자에 한하여 대여해드리고 있습니다."
    },
    "오프라인_공간": {
        "keywords": ["오프라인", "공간", "대여", "상세페이지", "프로젝트"],
        "question": "상세페이지 내에 있는 오프라인 공간 대여는 무엇인가요?",
        "answer": "프로젝트 기간에 신청 조에 한하여 오프라인 공간을 대여해드리고 있습니다. 자세한 문의는 담당 교육 매니저에게 문의하여 주세요."
    },
    "교재_수령": {
        "keywords": ["교재", "언제", "받기", "개강일", "배송"],
        "question": "교재는 언제 받을 수 있나요?",
        "answer": "(운영계획서 상 교재가 있는 과정의 경우에만 해당) 교재는 개강일 기준 일주일 이내로 주소를 취합하여 배송해드리고 있습니다. 자세한 문의는 담당 교육 매니저에게 문의해주세요."
    },
    "계좌_등록": {
        "keywords": ["훈련장려금", "계좌", "등록", "고용24", "요청"],
        "question": "훈련 장려금 계좌 등록은 어떻게 하나요?",
        "answer": "고용24 사이트에 접속하셔서 직접 등록하시거나, 교육행정 채널을 통해 행정 담당자님들께 요청하시면 됩니다!"
    }
}

# FastAPI 앱 초기화
app = FastAPI(
    title="라이언 헬퍼 AI 챗봇 & 검색 엔진 API",
    version="3.0.0",
    description="""
## 🤖 라이언 헬퍼 - 훈련생을 위한 스마트 도우미 API

### 🚀 주요 모드
- 🔍 **검색 엔진 모드**: 키워드 검색으로 관련 질문들을 모두 나열
- 💬 **채팅 모드**: AI와의 대화형 상호작용

### 📚 핵심 기능
- 🔍 **스마트 검색**: 키워드 기반으로 관련 질문들을 점수순 정렬
- 🤖 **하이브리드 AI**: 키워드 기반 + Ollama GPT 모델
- 📝 **훈련 정보**: 훈련장려금, 출결, 공결 관련 즉시 답변
- 🖥️ **교육 지원**: 줌, 노트북, 교재 관련 안내
- 💼 **커리어 지원**: 취업, 인턴십, 포트폴리오 상담
- 💬 **대화 기록**: 세션별 대화 내용 저장 및 관리

### 🔧 시스템 구조

#### 🔍 검색 엔진 모드
- **입력**: 검색 키워드 (예: "훈련장려금", "출결")
- **처리**: 47개 QA 데이터베이스에서 관련도 점수 계산
- **출력**: 관련 질문들을 점수순으로 정렬하여 반환
- **장점**: 한 번에 모든 관련 정보 확인 가능

#### 💬 채팅 모드  
- **1단계**: 키워드 기반 빠른 응답
- **2단계**: AI 모델 생성 응답 (Ollama GPT-OSS-20B)
- **백업**: 연결 실패 시 기본 안내 응답

### 🎯 지원 주제 (47개 카테고리)
- **💰 훈련장려금**: 계좌 변경, 금액, 지급시기, 수령 조건
- **📋 출결관리**: QR코드, 지각, 조퇴, 외출, 공결 신청
- **🖥️ 교육도구**: 줌 설정, 노트북 대여/반납, 교재 수령
- **🎓 학습지원**: 기초클래스, OT, 녹화본, 과제 제출
- **💼 커리어**: 수료 후 취업, 조기취업, 인턴십, 특강

### 🔄 개발 환경
- **🔗Base URL**: `http://localhost:8001`
- **📖API 문서**: `/docs` (Swagger UI)
- **🔧대안 문서**: `/redoc` (ReDoc)

### 💡 사용 플로우

#### 🔍 검색 엔진 모드
```bash
# 관련 질문 검색 (추천)
GET /search?query=훈련장려금&limit=10&min_score=0.1

# 응답 예시
{
  "query": "훈련장려금",
  "total_found": 5,
  "showing": 5,
  "results": [
    {
      "id": "훈련장려금_금액",
      "question": "훈련장려금은 얼마인가요?",
      "answer_preview": "훈련장려금은 하루 수업을 모두 참여시 일일 15,800원이...",
      "matched_keywords": ["훈련장려금", "얼마", "일일", "지급"],
      "score": 5.56
    }
  ]
}
```

#### 💬 채팅 모드
```bash
# AI 챗봇과 대화
POST /chat
{
  "prompt": "훈련장려금은 얼마인가요?",
  "use_ollama": true
}
```

### 🔗 API 엔드포인트

#### 🔍 검색 관련
- `GET /search` - 키워드로 관련 질문 검색
- `GET /qa-list` - 전체 QA 목록 조회
- `GET /qa-list?keyword=훈련장려금` - 키워드별 필터링

#### 💬 채팅 관련  
- `POST /chat` - AI 챗봇과 대화
- `GET /health` - 서버 상태 확인
- `GET /info` - 시스템 정보

#### 📝 세션 관리
- `POST /sessions` - 새 대화 세션 생성
- `GET /sessions` - 세션 목록 조회
- `GET /sessions/{id}/messages` - 세션 메시지 조회

### 📊 검색 점수 계산 방식
- **정확한 키워드 매칭**: 5점
- **부분 키워드 매칭**: 2점
- **질문 유사도**: 최대 1점  
- **답변 유사도**: 최대 0.5점

### 📞 문의
라이언 헬퍼 개발팀

**License**: MIT
    """,
    contact={
        "name": "라이언 헬퍼 개발팀",
        "url": "https://github.com/lionhelper/chatbot",
        "email": "dev@lionhelper.com"
    },
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT"
    },
    servers=[
        {
            "url": "https://lionhelper.onrender.com",
            "description": "운영 서버 (Render.com)"
        },
        {
            "url": "http://localhost:8000",
            "description": "로컬 개발 서버"
        },
        {
            "url": "http://localhost:8001", 
            "description": "테스트 서버"
        }
    ],
    tags_metadata=[
        {
            "name": "Chat",
            "description": "🤖 AI 챗봇 - 하이브리드 시스템을 사용하여 대화를 수행합니다"
        },
        {
            "name": "Health",
            "description": "🔍 서버 상태 - 서버 및 모델 상태를 확인합니다"
        },
        {
            "name": "Info",
            "description": "ℹ️ 시스템 정보 - 모델 및 기능 정보를 제공합니다"
        },
        {
            "name": "QA",
            "description": "❓ QA 관리 - 등록된 질문답변 목록을 관리합니다"
        },
        {
            "name": "Sessions",
            "description": "💬 대화 기록 - 채팅 세션 및 메시지 관리"
        },
        {
            "name": "Auth",
            "description": "🔐 인증 관리 - Google OAuth 로그인 및 사용자 인증"
        },
        {
            "name": "Search",
            "description": "🔍 검색 엔진 - 관련 질문들을 점수순으로 검색하고 반환"
        },
        {
            "name": "Slack",
            "description": "🔔 슬랙 연동 - 슬랙 채널에서 이슈 메시지를 수집하고 관리"
        },
        {
            "name": "Feedback",
            "description": "📝 피드백 시스템 - 답변 품질 개선을 위한 사용자 피드백 수집 및 분석"
        }
    ]
)

# CORS 설정 (Swagger UI와 프론트엔드 호환)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 도메인 허용 (개발용)
    allow_credentials=False,  # 개발 중에는 false로 설정
    allow_methods=["*"],  # 모든 메서드 허용
    allow_headers=["*"],  # 모든 헤더 허용
    expose_headers=["*"],
    max_age=86400
)

# 추가 CORS 미들웨어 (강제 헤더 추가)
@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    """모든 응답에 CORS 헤더 강제 추가"""
    response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS, PATCH"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Expose-Headers"] = "*"
    return response

# 전역 예외 핸들러 추가
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """모든 예외에 대해 JSON 응답을 보장합니다."""
    logger.error(f"예상치 못한 오류: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"내부 서버 오류: {str(exc)}"},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*"
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """요청 검증 오류에 대한 JSON 응답을 보장합니다."""
    logger.error(f"요청 검증 오류: {str(exc)}")
    return JSONResponse(
        status_code=422,
        content={"detail": "요청 데이터가 유효하지 않습니다.", "errors": exc.errors()},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*"
        }
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 예외에 대한 JSON 응답을 보장합니다."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "*"
        }
    )

# 정적 파일 서빙 설정
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    pass

# 앱 시작 시 데이터베이스 초기화
@app.on_event("startup")
async def startup_event():
    """앱 시작 시 데이터베이스 초기화"""
    try:
        logger.info("데이터베이스 초기화 시작...")
        init_database()
        logger.info("데이터베이스 초기화 완료!")
    except Exception as e:
        logger.error(f"데이터베이스 초기화 실패: {e}")
        # 데이터베이스 초기화 실패해도 앱은 계속 실행
        pass

print("🤖 Claude + 키워드 기반 지능형 AI 챗봇 시스템이 로드되었습니다.")
if claude_client:
    print("Claude-3-Haiku: 활성화됨")
else:
    print("Claude-3-Haiku: 비활성화됨 (API 키 확인 필요)")

# CORS preflight 요청을 위한 OPTIONS 핸들러
@app.options("/{full_path:path}")
async def options_handler(request: Request, full_path: str):
    """모든 경로에 대한 OPTIONS 요청 처리"""
    return JSONResponse(
        content="OK",
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
            "Access-Control-Allow-Headers": "Accept, Accept-Language, Content-Language, Content-Type, Authorization, X-Requested-With, Origin",
            "Access-Control-Max-Age": "86400"
        }
    )

# Pydantic 모델
class ChatRequest(BaseModel):
    """
    ## 🧠 Claude 지능형 챗봇 요청 모델
    
    Claude-3-Haiku + Knowledge Base 지능형 시스템
    """
    prompt: str = Field(..., description="사용자 질문 또는 메시지", example="안녕? 훈련장려금 언제 받을 수 있어?")
    max_new_tokens: Optional[int] = Field(600, description="Claude 응답 최대 토큰 수 (권장: 600)", example=600, ge=50, le=2048)
    temperature: Optional[float] = Field(0.7, description="Claude 창의성 조절 (권장: 0.7)", example=0.7, ge=0.0, le=2.0)
    top_p: Optional[float] = Field(0.9, description="확률 임계값 (0.0-1.0)", example=0.9, ge=0.0, le=1.0)
    use_claude: Optional[bool] = Field(True, description="🧠 Claude 지능형 응답 사용 (기본값: true)", example=True)
    session_id: Optional[str] = Field(None, description="대화 세션 ID (대화 기록용)", example="claude-chat-001")

    class Config:
        schema_extra = {
            "examples": {
                "claude_enhanced": {
                    "summary": "🧠 Claude 지능형 답변 (추천)",
                    "description": "Claude가 키워드 DB 참고해서 전문적 답변 생성",
                    "value": {
                        "prompt": "훈련장려금은 언제 받을 수 있나요?",
                        "use_claude": True,
                        "max_new_tokens": 1000,
                        "temperature": 0.7,
                        "session_id": "claude-enhanced-001"
                    }
                },
                "claude_general": {
                    "summary": "💬 Claude 일반 대화",
                    "description": "일반적인 질문이나 인사말에 대한 자연스러운 응답",
                    "value": {
                        "prompt": "안녕? 파이썬 코딩 질문해도 돼?",
                        "use_claude": True,
                        "session_id": "general-chat-001"
                    }
                },
                "keyword_fallback": {
                    "summary": "📚 키워드 응답 (Claude 비활성화)",
                    "description": "Claude 사용하지 않고 키워드 DB만 사용",
                    "value": {
                        "prompt": "출결 관리는 어떻게 하나요?",
                        "use_claude": False,
                        "session_id": "keyword-only-001"
                    }
                }
            }
        }

class RelatedQuestion(BaseModel):
    """관련 질문 모델"""
    id: str = Field(..., description="질문 고유 ID")
    question: str = Field(..., description="관련 질문")
    answer_preview: str = Field(..., description="답변 미리보기")
    score: float = Field(..., description="관련도 점수")
    matched_keywords: List[str] = Field(..., description="매칭된 키워드")

class ChatResponse(BaseModel):
    """
    ## 🧠 Claude 지능형 챗봇 응답 모델
    
    Claude + Knowledge Base 지능형 시스템의 응답
    """
    response: str = Field(..., description="Claude 지능형 응답 또는 키워드 기반 응답", example="안녕하세요! 훈련장려금에 대해 자세히 안내드리겠습니다...")
    model: str = Field(..., description="사용된 모델 (Claude + Knowledge Base/Keyword Database)", example="Claude-3-Haiku + Knowledge Base")
    status: str = Field(..., description="응답 상태 (success/error/fallback)", example="success")
    matched_keywords: Optional[List[str]] = Field(None, description="참고된 키워드 목록", example=["훈련장려금", "출석", "지급"])
    response_type: str = Field(..., description="응답 유형 (claude_enhanced/smart_keyword/fallback)", example="claude_enhanced")
    related_questions: Optional[List[RelatedQuestion]] = Field(None, description="관련 질문 목록 (키워드 DB)")
    total_related: Optional[int] = Field(None, description="관련 질문 총 개수")
    response_time_ms: Optional[float] = Field(None, description="응답 생성 시간 (밀리초)", example=1234.5)
    model_response_time_ms: Optional[float] = Field(None, description="AI 모델 응답 시간 (밀리초)", example=987.3)

    class Config:
        schema_extra = {
            "examples": {
                "claude_enhanced_response": {
                    "summary": "🧠 Claude 지능형 응답",
                    "description": "Claude가 키워드 DB 참고해서 생성한 전문적 답변",
                    "value": {
                        "response": "안녕하세요! 훈련장려금에 대해 안내드리겠습니다.\n\n💰 **훈련장려금 지급 기준:**\n- 일일 15,800원 지급\n- 하루 수업을 모두 참여해야 함\n- 지각, 조퇴, 외출 시 지급 불가\n\n📅 **지급 시기:**\n- 단위기간 마감 후 2-3주 소요\n- 80% 이상 출석률 유지 필요\n\n💡 **추가 팁:**\n- HRD앱으로 출결 체크 필수\n- 공결 신청은 미리 해주세요!\n\n궁금한 점이 더 있으시면 언제든 말씀해 주세요! 😊",
                        "model": "Claude-3-Haiku + Knowledge Base",
                        "status": "success",
                        "matched_keywords": ["훈련장려금", "출석", "지급"],
                        "response_type": "claude_enhanced",
                        "related_questions": [
                            {
                                "id": "qa_123",
                                "question": "훈련장려금 지급 조건은?",
                                "answer_preview": "하루 수업을 모두 참여시 일일 15,800원...",
                                "score": 0.95,
                                "matched_keywords": ["훈련장려금", "지급"]
                            }
                        ],
                        "total_related": 5
                    }
                },
                "claude_general_response": {
                    "summary": "💬 Claude 일반 대화 응답",
                    "description": "일반적인 질문에 대한 친근한 Claude 응답",
                    "value": {
                        "response": "안녕하세요! 네, 파이썬 코딩 질문 언제든 환영합니다! 🐍\n\n어떤 부분이 궁금하신가요? 기초 문법부터 고급 기능까지 도움을 드릴 수 있어요. 웹 개발, 데이터 분석, 알고리즘 등 어떤 분야든 편하게 질문해 주세요!\n\n같이 코딩 실력을 늘려가봐요! 💪",
                        "model": "Claude-3-Haiku + Knowledge Base",
                        "status": "success",
                        "matched_keywords": [],
                        "response_type": "claude_enhanced",
                        "related_questions": [],
                        "total_related": 0
                    }
                },
                "keyword_fallback_response": {
                    "summary": "📚 키워드 DB 응답 (Claude 실패 시)",
                    "description": "Claude 사용 불가 시 키워드 DB 기반 응답",
                    "value": {
                        "response": "훈련장려금은 해당 과정의 단위기간 마감일을 기준으로 지급까지 2주에서 3주 가량 소요됩니다.",
                        "model": "Keyword Database",
                        "status": "success",
                        "matched_keywords": ["훈련장려금", "언제", "받기"],
                        "response_type": "smart_keyword",
                "related_questions": [
                    {
                                "id": "1",
                                "question": "훈련장려금 금액은 얼마인가요?",
                                "answer_preview": "하루 수업을 모두 참여시 일일 15,800원...",
                                "score": 0.9,
                                "matched_keywords": ["훈련장려금", "금액"]
                            }
                        ],
                        "total_related": 5
                    }
                }
            }
        }

class User(BaseModel):
    """사용자 정보 모델"""
    id: str = Field(..., description="사용자 고유 ID")
    email: str = Field(..., description="이메일 주소")
    name: str = Field(..., description="사용자 이름")
    picture: Optional[str] = Field(None, description="프로필 사진 URL")
    created_at: str = Field(..., description="계정 생성일")

class Token(BaseModel):
    """토큰 응답 모델"""
    access_token: str = Field(..., description="JWT 액세스 토큰")
    token_type: str = Field(..., description="토큰 타입", example="bearer")
    expires_in: int = Field(..., description="토큰 만료 시간(초)", example=1800)
    user: User = Field(..., description="사용자 정보")

class LoginResponse(BaseModel):
    """로그인 응답 모델"""
    success: bool = Field(..., description="로그인 성공 여부")
    message: str = Field(..., description="응답 메시지")
    token: Optional[Token] = Field(None, description="토큰 정보 (성공 시)")
    user: Optional[User] = Field(None, description="사용자 정보 (성공 시)")

class SessionCreate(BaseModel):
    """새 세션 생성 요청 모델"""
    title: Optional[str] = Field("새로운 대화", description="세션 제목", example="훈련장려금 문의")

    class Config:
        schema_extra = {
            "example": {
                "title": "출결 및 훈련장려금 문의"
            }
        }

class Session(BaseModel):
    """세션 정보 모델"""
    id: str = Field(..., description="세션 고유 ID", example="123e4567-e89b-12d3-a456-426614174000")
    title: str = Field(..., description="세션 제목", example="출결 및 훈련장려금 문의")
    created_at: str = Field(..., description="생성 시간", example="2024-01-15 10:30:00")
    updated_at: str = Field(..., description="최종 업데이트 시간", example="2024-01-15 11:45:00")

    class Config:
        schema_extra = {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "title": "출결 및 훈련장려금 문의",
                "created_at": "2024-01-15 10:30:00",
                "updated_at": "2024-01-15 11:45:00"
            }
        }
    
class Message(BaseModel):
    """메시지 모델"""
    id: str = Field(..., description="메시지 고유 ID", example="456e7890-e89b-12d3-a456-426614174001")
    session_id: str = Field(..., description="세션 ID", example="123e4567-e89b-12d3-a456-426614174000")
    role: str = Field(..., description="발신자 (user/assistant)", example="user")
    content: str = Field(..., description="메시지 내용", example="QR코드 찍는 걸 깜빡했는데 출결정정 가능한가요?")
    response_type: Optional[str] = Field(None, description="응답 유형", example="keyword")
    model_used: Optional[str] = Field(None, description="사용된 모델명", example="Keyword-based Fast Response System")
    created_at: str = Field(..., description="생성 시간", example="2024-01-15 10:30:00")

    class Config:
        schema_extra = {
            "example": {
                "id": "456e7890-e89b-12d3-a456-426614174001",
                "session_id": "123e4567-e89b-12d3-a456-426614174000",
                "role": "user",
                "content": "QR코드 찍는 걸 깜빡했는데 출결정정 가능한가요?",
                "response_type": None,
                "model_used": None,
                "created_at": "2024-01-15 10:30:00"
            }
        }

# 슬랙 관련 모델들
class SlackIssue(BaseModel):
    """슬랙 이슈 모델"""
    id: str = Field(..., description="이슈 고유 ID")
    project: str = Field(..., description="프로젝트/과정명")
    issue_type: str = Field(..., description="이슈 유형")
    author: str = Field(..., description="작성자")
    content: str = Field(..., description="이슈 내용")
    raw_message: str = Field(..., description="원본 메시지")
    channel_id: Optional[str] = Field(None, description="채널 ID")
    timestamp: Optional[str] = Field(None, description="타임스탬프")
    slack_ts: Optional[str] = Field(None, description="슬랙 타임스탬프")
    created_at: str = Field(..., description="생성 시간")

class SlackSyncRequest(BaseModel):
    """슬랙 동기화 요청 모델"""
    hours: Optional[int] = Field(24, description="동기화할 시간 범위 (시간)", example=24)
    force: Optional[bool] = Field(False, description="강제 동기화 여부", example=False)

class FeedbackRequest(BaseModel):
    """답변 피드백 요청 모델"""
    session_id: str = Field(..., description="세션 ID")
    message_id: str = Field(..., description="메시지 ID")
    feedback_type: str = Field(..., description="피드백 유형", example="negative")
    feedback_content: Optional[str] = Field(None, description="피드백 내용")
    user_correction: Optional[str] = Field(None, description="사용자 수정 내용")

class ImprovementSuggestion(BaseModel):
    """답변 개선 제안 모델"""
    issue_type: str = Field(..., description="이슈 유형")
    current_answer: str = Field(..., description="현재 답변")
    suggested_answer: str = Field(..., description="개선된 답변")
    improvement_reason: str = Field(..., description="개선 이유")

# 슬랙 관련 함수들
def parse_slack_issue_message(text: str, user_name: str = None) -> Optional[Dict[str, str]]:
    """슬랙 메시지에서 이슈 정보를 파싱합니다."""
    # 멘션 태그가 포함된 메시지인지 확인 (@here, @everyone, @channel)
    has_mention = any(mention in text for mention in ["<@here>", "<@everyone>", "<@channel>" ,"<!here>", "<!everyone>", "<!channel>"])
    
    # 특정 사용자들의 메시지인지 확인 (장지연, 김은지)
    target_users = ["장지연", "김은지"]
    is_target_user = user_name and user_name in target_users
    
    # 멘션이나 특정 사용자가 아니면 None 반환
    if not has_mention and not is_target_user:
        return None
    
    # 기본 정보 추출
    issue_data = {}
    
    # 과정/프로젝트 추출 (정형화된 양식이 있으면 사용, 없으면 기본값)
    project_match = re.search(r'과정[:：]\s*([^\n]+)', text)
    if project_match:
        issue_data['project'] = project_match.group(1).strip()
    else:
        # 정형화된 양식이 없으면 메시지에서 키워드 기반으로 프로젝트 추정
        if any(keyword in text for keyword in ["프론트엔드", "frontend", "Front-end", "React", "Vue", "Angular"]):
            issue_data['project'] = "프론트엔드 관련"
        elif any(keyword in text for keyword in ["백엔드", "backend", "Back-end", "Django", "Spring", "Node.js"]):
            issue_data['project'] = "백엔드 관련"
        elif any(keyword in text for keyword in ["훈련장려금", "장려금", "출결", "공결"]):
            issue_data['project'] = "행정 관련"
        else:
            issue_data['project'] = "일반 공지"
    
    # 내용 추출 (정형화된 양식이 있으면 사용, 없으면 전체 메시지)
    content_match = re.search(r'내용[:：]\s*([^\n]+)', text)
    if content_match:
        issue_data['content'] = content_match.group(1).strip()
    else:
        # 멘션 태그를 제거하고 메시지 내용만 추출
        content = re.sub(r'<@[^>]+>', '', text).strip()
        content = re.sub(r'<!here>|<!everyone>|<!channel>', '', content).strip()
        issue_data['content'] = content if content else "멘션 메시지"
    
    # 작성자 추출 (정형화된 양식이 있으면 사용, 없으면 기본값)
    author_match = re.search(r'작성자[:：]\s*([^\n]+)', text)
    if author_match:
        issue_data['author'] = author_match.group(1).strip()
    elif is_target_user:
        # 특정 사용자의 메시지인 경우 해당 사용자명 사용
        issue_data['author'] = user_name
    else:
        issue_data['author'] = "행정 담당자"
    
    # 이슈 유형 분류
    issue_type = "일반"
    if any(keyword in text for keyword in ["프론트엔드", "frontend", "Front-end", "React", "Vue", "Angular"]):
        issue_type = "프론트엔드"
    elif any(keyword in text for keyword in ["백엔드", "backend", "Back-end", "Django", "Spring", "Node.js"]):
        issue_type = "백엔드"
    elif any(keyword in text for keyword in ["훈련장려금", "장려금"]):
        issue_type = "훈련장려금"
    elif any(keyword in text for keyword in ["환경설정", "설정", "환경"]):
        issue_type = "환경설정"
    elif any(keyword in text for keyword in ["출결", "공결", "지각", "조퇴", "결석"]):
        issue_type = "출결관리"
    elif any(keyword in text for keyword in ["공지", "안내", "알림"]):
        issue_type = "공지사항"
    elif is_target_user:
        # 특정 사용자의 메시지인 경우 "담당자 메시지"로 분류
        issue_type = "담당자 메시지"
    
    issue_data['issue_type'] = issue_type
    
    # 멘션 태그가 있으면 무조건 저장 (정형화된 양식 불필요)
    return issue_data

def save_slack_issue(issue_data: Dict[str, str], raw_message: str, channel_id: str = None, timestamp: str = None, slack_ts: str = None) -> str:
    """파싱된 슬랙 이슈를 데이터베이스에 저장합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    issue_id = str(uuid.uuid4())
    
    try:
        cursor.execute('''
            INSERT INTO slack_issues (id, project, issue_type, author, content, raw_message, channel_id, timestamp, slack_ts)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            issue_id,
            issue_data['project'],
            issue_data['issue_type'],
            issue_data['author'],
            issue_data['content'],
            raw_message,
            channel_id,
            timestamp,
            slack_ts
        ))
        
        conn.commit()
        logger.info(f"슬랙 이슈 저장 완료: {issue_id}")
        return issue_id
        
    except psycopg2.IntegrityError as e:
        if "duplicate key value" in str(e):
            logger.info(f"이미 존재하는 슬랙 메시지: {slack_ts}")
            return None
        raise
    finally:
        conn.close()

def get_slack_issues(limit: int = 50, project: str = None) -> List[SlackIssue]:
    """저장된 슬랙 이슈들을 조회합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        if project:
            cursor.execute('''
                SELECT id, project, issue_type, author, content, raw_message, channel_id, timestamp, slack_ts, created_at
                FROM slack_issues 
                WHERE project LIKE %s
                ORDER BY created_at DESC 
                LIMIT %s
            ''', (f'%{project}%', limit))
        else:
            cursor.execute('''
                SELECT id, project, issue_type, author, content, raw_message, channel_id, timestamp, slack_ts, created_at
                FROM slack_issues 
                ORDER BY created_at DESC 
                LIMIT %s
            ''', (limit,))
        
        rows = cursor.fetchall()
        issues = []
        
        for row in rows:
            # created_at을 문자열로 변환
            created_at_str = row[9].isoformat() if hasattr(row[9], 'isoformat') else str(row[9])
            
            issues.append(SlackIssue(
                id=row[0],
                project=row[1],
                issue_type=row[2],
                author=row[3],
                content=row[4],
                raw_message=row[5],
                channel_id=row[6],
                timestamp=row[7],
                slack_ts=row[8],
                created_at=created_at_str
            ))
        
        return issues
        
    finally:
        conn.close()

async def fetch_slack_messages(hours: int = 24) -> List[Dict[str, Any]]:
    """슬랙 채널에서 메시지를 가져옵니다."""
    if not slack_client:
        raise HTTPException(status_code=500, detail="슬랙 봇 토큰이 설정되지 않았습니다")
    
    try:
        # 지정된 시간 이전의 타임스탬프 계산
        oldest_time = time.time() - (hours * 3600)
        
        # 채널 메시지 가져오기
        response = slack_client.conversations_history(
            channel=SLACK_CHANNEL_ID,
            oldest=str(oldest_time),
            limit=100
        )
        
        if not response["ok"]:
            raise HTTPException(status_code=500, detail=f"슬랙 API 오류: {response.get('error', 'Unknown error')}")
        
        return response["messages"]
        
    except SlackApiError as e:
        logger.error(f"슬랙 API 오류: {e}")
        error_detail = f"슬랙 API 오류: {e.response['error'] if hasattr(e, 'response') and e.response else str(e)}"
        raise HTTPException(status_code=500, detail=error_detail)

async def sync_slack_issues(hours: int = 24, force: bool = False) -> Dict[str, Any]:
    """슬랙 채널에서 이슈 메시지를 동기화합니다."""
    try:
        messages = await fetch_slack_messages(hours)
        
        new_issues = 0
        skipped_issues = 0
        errors = 0
        
        for message in messages:
            # 봇 메시지나 편집된 메시지는 무시
            if message.get("bot_id") or message.get("subtype") == "message_changed":
                continue
            
            text = message.get("text", "")
            slack_ts = message.get("ts")
            user_id = message.get("user", "")
            
            # 사용자 정보 가져오기 (슬랙 API를 통해 실제 이름 조회)
            user_name = None
            if user_id:
                try:
                    user_info = slack_client.users_info(user=user_id)
                    if user_info["ok"]:
                        user_name = user_info["user"].get("real_name", "")
                except Exception as e:
                    logger.warning(f"사용자 정보 조회 실패: {e}")
            
            # 이슈 메시지인지 파싱 시도 (사용자 정보 포함)
            issue_data = parse_slack_issue_message(text, user_name)
            if not issue_data:
                continue
            
            try:
                # 데이터베이스에 저장
                issue_id = save_slack_issue(
                    issue_data=issue_data,
                    raw_message=text,
                    channel_id=SLACK_CHANNEL_ID,
                    timestamp=message.get("ts"),
                    slack_ts=slack_ts
                )
                
                if issue_id:
                    new_issues += 1
                    logger.info(f"새로운 이슈 저장: {issue_data['project']} - {issue_data['content'][:50]}...")
                else:
                    skipped_issues += 1
                    
            except Exception as e:
                logger.error(f"이슈 저장 중 오류: {e}")
                errors += 1
        
        return {
            "success": True,
            "message": f"동기화 완료: 새로운 이슈 {new_issues}개, 건너뛴 이슈 {skipped_issues}개, 오류 {errors}개",
            "new_issues": new_issues,
            "skipped_issues": skipped_issues,
            "errors": errors,
            "total_messages": len(messages)
        }
        
    except Exception as e:
        logger.error(f"슬랙 동기화 오류: {e}", exc_info=True)
        error_msg = str(e) if str(e) else f"알 수 없는 오류: {type(e).__name__}"
        return {
            "success": False,
            "message": f"동기화 실패: {error_msg}",
            "new_issues": 0,
            "skipped_issues": 0,
            "errors": 1,
            "error_details": {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "slack_client_available": bool(slack_client),
                "slack_channel_id": SLACK_CHANNEL_ID
            }
        }

def save_answer_feedback(session_id: str, message_id: str, user_question: str, ai_answer: str, 
                        feedback_type: str, feedback_content: str = None, user_correction: str = None) -> bool:
    """답변 피드백을 데이터베이스에 저장합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        feedback_id = str(uuid.uuid4())
        cursor.execute('''
            INSERT INTO answer_feedback 
            (id, session_id, message_id, user_question, ai_answer, feedback_type, feedback_content, user_correction)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (feedback_id, session_id, message_id, user_question, ai_answer, feedback_type, feedback_content, user_correction))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logging.error(f"피드백 저장 오류: {e}")
        return False

def analyze_feedback_patterns() -> Dict[str, Any]:
    """피드백 패턴을 분석하여 개선점을 찾습니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 부정적 피드백이 많은 질문 유형 분석
        cursor.execute('''
            SELECT user_question, COUNT(*) as negative_count
            FROM answer_feedback 
            WHERE feedback_type = 'negative'
            GROUP BY user_question
            ORDER BY negative_count DESC
            LIMIT 10
        ''')
        problematic_questions = cursor.fetchall()
        
        # 자주 수정되는 답변 패턴 분석
        cursor.execute('''
            SELECT user_correction, COUNT(*) as correction_count
            FROM answer_feedback 
            WHERE feedback_type = 'correction' AND user_correction IS NOT NULL
            GROUP BY user_correction
            ORDER BY correction_count DESC
            LIMIT 10
        ''')
        common_corrections = cursor.fetchall()
        
        # 전체 피드백 통계
        cursor.execute('''
            SELECT feedback_type, COUNT(*) as count
            FROM answer_feedback
            GROUP BY feedback_type
        ''')
        feedback_stats = cursor.fetchall()
        
        conn.close()
        
        return {
            "problematic_questions": [{"question": q[0], "count": q[1]} for q in problematic_questions],
            "common_corrections": [{"correction": c[0], "count": c[1]} for c in common_corrections],
            "feedback_stats": [{"type": f[0], "count": f[1]} for f in feedback_stats]
        }
    except Exception as e:
        logging.error(f"피드백 분석 오류: {e}")
        return {}

def get_improvement_suggestions_from_issues() -> List[Dict[str, str]]:
    """슬랙 이슈 데이터를 기반으로 답변 개선 제안을 생성합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # 최근 이슈들 가져오기
        cursor.execute('''
            SELECT project, issue_type, content, author
            FROM slack_issues
            ORDER BY created_at DESC
            LIMIT 20
        ''')
        recent_issues = cursor.fetchall()
        
        suggestions = []
        for issue in recent_issues:
            project, issue_type, content, author = issue
            
            # 이슈 유형별 개선 제안 생성
            if "정확도" in content or "틀린" in content or "잘못" in content:
                suggestions.append({
                    "issue_type": "답변 정확도",
                    "description": f"{project}에서 {issue_type} 관련 정확도 문제 발생",
                    "suggestion": "해당 분야의 QA 데이터베이스 업데이트 및 검증 강화 필요",
                    "priority": "high"
                })
            elif "느린" in content or "속도" in content:
                suggestions.append({
                    "issue_type": "응답 속도",
                    "description": f"{project}에서 응답 속도 문제 발생",
                    "suggestion": "캐싱 시스템 개선 및 응답 최적화 필요",
                    "priority": "medium"
                })
        
        conn.close()
        return suggestions
    except Exception as e:
        logging.error(f"개선 제안 생성 오류: {e}")
        return []

def analyze_question_intent(user_input: str) -> dict:
    """질문의 의도를 분석하여 카테고리와 유형을 반환합니다."""
    input_lower = user_input.lower().strip()
    
    # 일반적인 인사말/대화 패턴 (항상 Claude가 처리해야 함)
    general_greetings = ["hi", "hello", "안녕", "헬로", "하이", "좋은아침", "안녕하세요", "반가워", "처음뵙겠습니다"]
    general_conversation = ["어떻게", "무엇", "뭐해", "잘지내", "기분", "날씨", "감사", "고마워", "미안", "죄송"]
    code_questions = ["코드", "프로그래밍", "개발", "파이썬", "자바스크립트", "html", "css", "알고리즘", "함수", "변수"]
    general_questions = ["질문", "받아주", "도와주", "할 수 있", "가능한", "어떤", "무슨", "왜", "설명해"]
    
    # 일반 대화 패턴 체크 (확장된 패턴)
    is_general_conversation = any(pattern in input_lower for pattern in 
                                general_greetings + general_conversation + code_questions + general_questions)
    
    # 질문 유형 분류
    intent_patterns = {
        "금액_문의": ["얼마", "금액", "돈", "원", "비용", "가격"],
        "시기_문의": ["언제", "몇일", "시간", "기간", "때", "일정"],
        "방법_문의": ["어떻게", "방법", "어디서", "누구", "절차", "과정"],
        "가능_여부": ["가능", "될까", "되나", "할 수 있", "괜찮", "상관없"],
        "조건_문의": ["조건", "요구사항", "필요", "기준", "자격"],
        "문제_해결": ["안돼", "안되", "오류", "문제", "고장", "실패", "불가"]
    }
    
    # 주제 카테고리 분류 (확장된 키워드 매핑)
    topic_categories = {
        "훈련장려금": ["훈련장려금", "장려금", "수당", "지급", "입금", "계좌", "15800", "15,800"],
        "출결관리": ["출결", "출석", "지각", "조퇴", "외출", "결석", "QR", "체크", "입실", "퇴실", "HRD", "앱", "스크린샷"],
        "공결신청": ["공결", "병원", "진료", "입원", "예비군", "결혼", "상", "진단서", "처방전", "치과", "사랑니"],
        "교육도구": ["줌", "zoom", "노트북", "맥북", "교재", "캠", "배경", "설정", "화면", "웹캠", "카메라"],
        "행정업무": ["서류", "증명서", "신청", "변경", "계좌", "휴가", "실업급여", "수강증명서", "이사", "주소"],
        "수료_취업": ["수료", "취업", "인턴", "포트폴리오", "면접", "조기취업", "중도포기", "80%", "출석률"],
        "기초교육": ["기초클래스", "OT", "등록", "훈련생", "내일배움카드", "국취제", "국민취업지원제도"],
        "규정준수": ["해외여행", "해외출국", "장소이동", "개인소지", "화장실", "자리비움", "녹화본"]
    }
    
    # 타사 교육기관 키워드들 (제한 대상) - 멋쟁이사자처럼은 제외
    competitor_keywords = [
        "스파르타", "코딩클럽", "코딩 클럽", "코드스테이츠", "코드스테이츠",
        "위코드", "wecode", "바닐라코딩", "바닐라 코딩", "패스트캠퍼스",
        "패스트 캠퍼스", "프로그래머스", "프로그래머스", "이노베이션",
        "부트캠프", "코딩학원", "코딩 학원", "it학원", "it 학원",
        "개발자교육", "개발자 교육", "프로그래밍학원", "프로그래밍 학원"
    ]
    
    # 자사 키워드 (멋쟁이사자처럼 관련)
    company_keywords = [
        "멋쟁이사자처럼", "멋사", "kdt", "k-digital", "k digital"
    ]
    
    detected_intent = "일반_문의"
    detected_topic = "기타"
    confidence = 0.0
    
    # 타사 교육기관 관련 질문인지 확인 (자사 키워드가 포함된 경우 제외)
    has_competitor_keywords = any(keyword in input_lower for keyword in competitor_keywords)
    has_company_keywords = any(keyword in input_lower for keyword in company_keywords)
    is_competitor_question = has_competitor_keywords and not has_company_keywords
    
    # 일반 대화인 경우 특별 처리
    if is_general_conversation:
        detected_topic = "일반대화"
        confidence = 0.0  # 키워드 매칭 점수를 낮춤
    elif is_competitor_question:
        detected_topic = "타사정보"
        confidence = 1.0  # 타사 정보는 높은 신뢰도로 감지
    else:
        # 의도 분석
        for intent, keywords in intent_patterns.items():
            matches = sum(1 for keyword in keywords if keyword in input_lower)
            if matches > 0:
                detected_intent = intent
                confidence += matches * 0.2
                break
    
    # 주제 분석
    for topic, keywords in topic_categories.items():
        matches = sum(1 for keyword in keywords if keyword in input_lower)
        if matches > 0:
            detected_topic = topic
            confidence += matches * 0.3
            break
    
    return {
        "intent": detected_intent,
        "topic": detected_topic,
        "confidence": min(confidence, 1.0),
        "input_length": len(user_input),
        "question_words": len([w for w in input_lower.split() if w in ["뭐", "무엇", "어떤", "왜", "어디", "언제", "누구", "어떻게"]]),
        "is_general_conversation": is_general_conversation,
        "is_competitor_question": is_competitor_question
    }

def find_best_match(user_input: str) -> tuple:
    """사용자 입력과 가장 잘 매칭되는 QA를 찾습니다."""
    user_input_lower = user_input.lower().strip()
    best_match = None
    best_score = 0
    matched_keywords = []
    
    for qa_id, qa_data in QA_DATABASE.items():
        score = 0
        keywords_found = []
        
        # 1. 정확한 키워드 매칭 (높은 가중치)
        for keyword in qa_data["keywords"]:
            keyword_lower = keyword.lower()
            if keyword_lower in user_input_lower:
                score += 5  # 정확한 매칭은 높은 점수
                keywords_found.append(keyword)
        
        # 2. 부분 키워드 매칭 (중간 가중치)
        for keyword in qa_data["keywords"]:
            keyword_lower = keyword.lower()
            if len(keyword_lower) >= 2:  # 2글자 이상 키워드만
                # 사용자 입력의 각 단어와 비교
                user_words = user_input_lower.replace('?', '').replace('!', '').replace('.', '').split()
                for word in user_words:
                    if len(word) >= 2:
                        # 키워드가 단어에 포함되거나, 단어가 키워드에 포함되는 경우
                        if (keyword_lower in word or word in keyword_lower) and keyword not in keywords_found:
                            score += 2  # 부분 매칭은 중간 점수
                            keywords_found.append(keyword)
        
        # 3. 질문 유사도 (낮은 가중치)
        question_similarity = SequenceMatcher(None, user_input_lower, qa_data["question"].lower()).ratio()
        if question_similarity > 0.3:  # 30% 이상 유사할 때만
            score += question_similarity * 1  # 낮은 가중치
        
        # 4. 답변 내용 유사도 (매우 낮은 가중치)
        answer_similarity = SequenceMatcher(None, user_input_lower, qa_data["answer"].lower()).ratio()
        if answer_similarity > 0.4:  # 40% 이상 유사할 때만
            score += answer_similarity * 0.5  # 매우 낮은 가중치
        
        if score > best_score:
            best_score = score
            best_match = qa_data
            matched_keywords = keywords_found
    return best_match, best_score, matched_keywords

def find_related_questions_smart(user_input: str, limit: int = 5, min_score: float = 0.5, context_keywords: List[str] = None) -> List[dict]:
    """지능적인 매칭 시스템으로 관련된 질문들을 점수순으로 반환합니다."""
    user_input_lower = user_input.lower().strip()
    related_questions = []
    
    # 질문 의도 분석
    intent_analysis = analyze_question_intent(user_input)
    logger.info(f"질문 의도 분석: {intent_analysis}")
    
    # 맥락 키워드가 있으면 추가 가중치 적용
    context_boost = {}
    if context_keywords:
        for keyword in context_keywords:
            context_boost[keyword.lower()] = 1.5
    
    for qa_id, qa_data in QA_DATABASE.items():
        score = 0
        keywords_found = []
        relevance_factors = []
        
        # 1. 의도 기반 매칭 (새로운 최우선 매칭)
        qa_intent = analyze_question_intent(qa_data["question"])
        if qa_intent["intent"] == intent_analysis["intent"] and qa_intent["topic"] == intent_analysis["topic"]:
            score += 10  # 의도와 주제가 모두 같으면 최고 점수
            relevance_factors.append("intent_topic_match")
        elif qa_intent["intent"] == intent_analysis["intent"]:
            score += 6  # 의도만 같아도 높은 점수
            relevance_factors.append("intent_match")
        elif qa_intent["topic"] == intent_analysis["topic"]:
            score += 4  # 주제만 같아도 점수 부여
            relevance_factors.append("topic_match")
        
        # 2. 정확한 키워드 매칭 (기존 방식 개선)
        for keyword in qa_data["keywords"]:
            keyword_lower = keyword.lower()
            if keyword_lower in user_input_lower:
                base_score = 3  # 의도 매칭보다 낮게 조정
                # 맥락 가중치 적용
                if keyword_lower in context_boost:
                    base_score *= context_boost[keyword_lower]
                score += base_score
                keywords_found.append(keyword)
                relevance_factors.append("exact_keyword")
        
        # 3. 의미론적 유사도 (개선된 버전)
        question_similarity = SequenceMatcher(None, user_input_lower, qa_data["question"].lower()).ratio()
        if question_similarity > 0.4:  # 임계값 상향 조정
            score += question_similarity * 3  # 가중치 증가
            relevance_factors.append("question_similarity")
        
        # 4. 답변 품질 점수 (답변 길이와 구체성 고려)
        answer_quality = min(len(qa_data["answer"]) / 100, 2.0)  # 답변 길이 기반 품질 점수
        if any(word in qa_data["answer"] for word in ["예를 들어", "다만", "단,", "참고", "자세한"]):
            answer_quality += 0.5  # 구체적인 설명이 있으면 추가 점수
        score += answer_quality
        
        # 5. 부분 키워드 매칭 (기존 방식 유지하되 가중치 조정)
        for keyword in qa_data["keywords"]:
            keyword_lower = keyword.lower()
            if len(keyword_lower) >= 2:
                user_words = user_input_lower.replace('?', '').replace('!', '').replace('.', '').split()
                for word in user_words:
                    if len(word) >= 2:
                        if (keyword_lower in word or word in keyword_lower) and keyword not in keywords_found:
                            base_score = 1  # 점수 축소
                            if keyword_lower in context_boost:
                                base_score *= context_boost[keyword_lower]
                            score += base_score
                            keywords_found.append(keyword)
                            relevance_factors.append("partial_keyword")
        
        # 최소 점수 이상인 경우만 포함
        if score >= min_score:
            related_questions.append({
                "id": qa_id,
                "question": qa_data["question"],
                "answer": qa_data["answer"],
                "score": round(score, 2),
                "matched_keywords": keywords_found,
                "relevance_factors": relevance_factors,
                "intent": qa_intent["intent"],
                "topic": qa_intent["topic"]
            })
    
    # 점수순으로 정렬하고 제한된 개수만 반환
    related_questions.sort(key=lambda x: x["score"], reverse=True)
    return related_questions[:limit]

def find_related_questions(user_input: str, limit: int = 5, min_score: float = 0.5, context_keywords: List[str] = None) -> List[dict]:
    """사용자 입력과 관련된 여러 질문들을 점수순으로 반환합니다. (하위 호환성 유지)"""
    return find_related_questions_smart(user_input, limit, min_score, context_keywords)

def get_context_keywords(session_id: str) -> List[str]:
    """세션의 이전 대화에서 자주 나온 키워드들을 추출합니다."""
    if not session_id:
        return []
    
    try:
        messages = get_session_messages(session_id)
        keyword_count = {}
        
        # 최근 5개 메시지만 분석 (너무 오래된 대화는 제외)
        recent_messages = messages[-10:] if len(messages) > 10 else messages
        
        for message in recent_messages:
            if message.role == "user":  # 사용자 메시지만 분석
                content_lower = message.content.lower()
                
                # QA 데이터베이스의 모든 키워드와 매칭
                for qa_id, qa_data in QA_DATABASE.items():
                    for keyword in qa_data["keywords"]:
                        keyword_lower = keyword.lower()
                        if keyword_lower in content_lower:
                            keyword_count[keyword_lower] = keyword_count.get(keyword_lower, 0) + 1
        
        # 빈도순으로 정렬하여 상위 키워드 반환
        sorted_keywords = sorted(keyword_count.items(), key=lambda x: x[1], reverse=True)
        return [keyword for keyword, count in sorted_keywords[:5]]  # 상위 5개 키워드
        
    except Exception as e:
        logger.warning(f"컨텍스트 키워드 추출 실패: {str(e)}")
        return []

def get_conversation_context(session_id: str, max_messages: int = 6) -> str:
    """세션의 최근 대화 내용을 컨텍스트로 반환합니다."""
    if not session_id:
        return ""
    
    try:
        messages = get_session_messages(session_id)
        if not messages:
            return ""
        
        # 최근 대화만 가져오기 (너무 오래된 것은 제외)
        recent_messages = messages[-max_messages:] if len(messages) > max_messages else messages
        
        context_parts = []
        for message in recent_messages:
            role_name = "사용자" if message.role == "user" else "상담사"
            context_parts.append(f"{role_name}: {message.content}")
        
        if context_parts:
            return "\n".join(context_parts)
        return ""
        
    except Exception as e:
        logger.warning(f"대화 컨텍스트 추출 실패: {str(e)}")
        return ""

def get_conversation_summary(session_id: str) -> str:
    """세션의 대화 주제와 맥락을 요약합니다."""
    if not session_id:
        return ""
    
    try:
        messages = get_session_messages(session_id)
        if not messages or len(messages) < 2:
            return ""
        
        # 사용자 메시지들만 추출하여 주제 파악
        user_messages = [msg.content for msg in messages if msg.role == "user"]
        if not user_messages:
            return ""
        
        # 최근 3개 사용자 메시지로 주제 파악
        recent_topics = user_messages[-3:] if len(user_messages) >= 3 else user_messages
        
        # 간단한 주제 키워드 추출
        topic_keywords = []
        for message in recent_topics:
            content_lower = message.lower()
            # 주요 키워드들 체크
            if any(word in content_lower for word in ["훈련장려금", "장려금", "지급"]):
                topic_keywords.append("훈련장려금")
            if any(word in content_lower for word in ["출결", "출석", "지각", "조퇴"]):
                topic_keywords.append("출결관리")
            if any(word in content_lower for word in ["공결", "결석", "병가"]):
                topic_keywords.append("공결신청")
            if any(word in content_lower for word in ["줌", "온라인", "수업"]):
                topic_keywords.append("온라인수업")
            if any(word in content_lower for word in ["노트북", "대여", "기기"]):
                topic_keywords.append("노트북대여")
        
        # 중복 제거하고 주제 요약
        unique_topics = list(set(topic_keywords))
        if unique_topics:
            return f"이전 대화 주제: {', '.join(unique_topics)}"
        return ""
        
    except Exception as e:
        logger.warning(f"대화 요약 생성 실패: {str(e)}")
        return ""

def get_conversation_flow(session_id: str) -> str:
    """대화의 흐름과 맥락을 파악합니다."""
    if not session_id:
        return ""
    
    try:
        messages = get_session_messages(session_id)
        if not messages or len(messages) < 4:
            return ""
        
        # 최근 대화 흐름 분석
        recent_messages = messages[-6:] if len(messages) > 6 else messages
        
        flow_indicators = []
        
        # 질문 패턴 분석
        for i, message in enumerate(recent_messages):
            if message.role == "user":
                content_lower = message.content.lower()
                
                # 연속 질문 패턴
                if any(word in content_lower for word in ["그러면", "그럼", "그래서", "그렇다면"]):
                    flow_indicators.append("연속 질문")
                
                # 구체화 질문 패턴
                if any(word in content_lower for word in ["몇", "얼마", "언제", "어떻게", "왜"]):
                    flow_indicators.append("구체적 질문")
                
                # 확인 질문 패턴
                if any(word in content_lower for word in ["괜찮", "가능", "되나", "할 수 있"]):
                    flow_indicators.append("확인 질문")
        
        if flow_indicators:
            return f"대화 흐름: {', '.join(set(flow_indicators))}"
        return ""
        
    except Exception as e:
        logger.warning(f"대화 흐름 분석 실패: {str(e)}")
        return ""

def get_user_context(session_id: str) -> str:
    """사용자의 상황과 맥락을 파악합니다."""
    if not session_id:
        return ""
    
    try:
        messages = get_session_messages(session_id)
        if not messages:
            return ""
        
        # 사용자 메시지에서 상황 파악
        user_messages = [msg.content for msg in messages if msg.role == "user"]
        if not user_messages:
            return ""
        
        context_indicators = []
        
        for message in user_messages:
            content_lower = message.lower()
            
            # 긴급성 표현
            if any(word in content_lower for word in ["급해", "빨리", "어떻게 해야", "도와줘"]):
                context_indicators.append("긴급 상황")
            
            # 불안감 표현
            if any(word in content_lower for word in ["걱정", "불안", "어떻게 될까", "괜찮을까"]):
                context_indicators.append("불안감")
            
            # 구체적 상황
            if any(word in content_lower for word in ["몇 일", "몇 번", "몇 개", "얼마나"]):
                context_indicators.append("구체적 상황")
        
        if context_indicators:
            return f"사용자 상황: {', '.join(set(context_indicators))}"
        return ""
        
    except Exception as e:
        logger.warning(f"사용자 맥락 분석 실패: {str(e)}")
        return ""

def get_conversation_memory(session_id: str) -> str:
    """대화에서 언급된 구체적인 정보들을 기억합니다."""
    if not session_id:
        return ""
    
    try:
        messages = get_session_messages(session_id)
        if not messages:
            return ""
        
        memory_items = []
        
        # 최근 대화에서 구체적인 정보 추출
        recent_messages = messages[-8:] if len(messages) > 8 else messages
        
        for message in recent_messages:
            if message.role == "user":
                content = message.content
                
                # 숫자 정보 추출 (일수, 횟수 등)
                import re
                numbers = re.findall(r'\d+', content)
                if numbers:
                    for num in numbers:
                        if any(word in content.lower() for word in ["일", "번", "개", "회"]):
                            memory_items.append(f"사용자가 언급한 숫자: {num}")
                
                # 구체적인 상황 추출
                if "16일" in content:
                    memory_items.append("16일 출석 관련 질문")
                if "80%" in content:
                    memory_items.append("80% 출석률 관련 질문")
                if "공결" in content:
                    memory_items.append("공결 관련 질문")
                if "훈련장려금" in content:
                    memory_items.append("훈련장려금 관련 질문")
        
        if memory_items:
            return f"대화 기억: {', '.join(set(memory_items))}"
        return ""
        
    except Exception as e:
        logger.warning(f"대화 기억 분석 실패: {str(e)}")
        return ""

def create_session(title: str = "새로운 대화") -> str:
    """새로운 채팅 세션 생성"""
    session_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO sessions (id, title) VALUES (?, ?)
    ''', (session_id, title))
    
    conn.commit()
    conn.close()
    return session_id

def save_message(session_id: str, role: str, content: str, response_type: str = None, model_used: str = None) -> str:
    """메시지 저장"""
    message_id = str(uuid.uuid4())
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO messages (id, session_id, role, content, response_type, model_used)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (message_id, session_id, role, content, response_type, model_used))
    
    # 세션 업데이트 시간 갱신
    cursor.execute('''
        UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = %s
    ''', (session_id,))
    
    conn.commit()
    conn.close()
    return message_id

def get_sessions() -> List[Session]:
    """모든 세션 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, title, created_at, updated_at 
        FROM sessions 
        ORDER BY updated_at DESC
    ''')
    
    sessions = []
    for row in cursor.fetchall():
        sessions.append(Session(
            id=row[0],
            title=row[1],
            created_at=row[2],
            updated_at=row[3]
        ))
    
    conn.close()
    return sessions

def get_session_messages(session_id: str) -> List[Message]:
    """특정 세션의 메시지 목록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, session_id, role, content, response_type, model_used, created_at
        FROM messages 
        WHERE session_id = %s
        ORDER BY created_at ASC
    ''', (session_id,))
    
    messages = []
    for row in cursor.fetchall():
        messages.append(Message(
            id=row[0],
            session_id=row[1],
            role=row[2],
            content=row[3],
            response_type=row[4],
            model_used=row[5],
            created_at=row[6]
        ))
    
    conn.close()
    return messages

def delete_session(session_id: str):
    """세션과 관련 메시지 삭제"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM messages WHERE session_id = %s', (session_id,))
    cursor.execute('DELETE FROM sessions WHERE id = %s', (session_id,))
    
    conn.commit()
    conn.close()

def update_session_title(session_id: str, title: str):
    """세션 제목 업데이트"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = %s
    ''', (title, session_id))
    
    conn.commit()
    conn.close()

async def call_claude(user_prompt: str, max_tokens: int = 1000, temperature: float = 0.7, context_data: List[dict] = None) -> Optional[str]:
    """Claude API를 사용하여 응답 생성"""
    if not claude_client:
        logger.warning("Claude 클라이언트가 초기화되지 않았습니다")
        return None
    
    try:
        # 컨텍스트가 있는 경우 프롬프트에 포함
        if context_data:
            context_info = "\n".join([f"Q: {item['question']}\nA: {item['answer']}" for item in context_data[:3]])
            enhanced_prompt = f"""다음은 관련된 정보입니다:
{context_info}

위 정보를 참고하여 다음 질문에 한국어로 답변해주세요:
{user_prompt}

답변 시 주의사항:
- 정확하고 도움이 되는 정보를 제공해주세요
- 한국어로 자연스럽게 답변해주세요
- 관련 정보가 있다면 활용하되, 없다면 일반적인 지식으로 답변해주세요"""
        else:
            enhanced_prompt = f"""다음 질문에 한국어로 친절하고 도움이 되는 답변을 해주세요:
{user_prompt}

답변 시 주의사항:
- 정확하고 유용한 정보를 제공해주세요
- 한국어로 자연스럽게 답변해주세요
- 친근하고 전문적인 톤으로 답변해주세요"""
        
        # Claude API 호출
        response = claude_client.make_request(enhanced_prompt, max_tokens)
        
        if response:
            logger.info("Claude API 호출 성공")
            return response.strip()
        else:
            logger.warning("Claude API 응답이 비어있습니다")
            return None
            
    except Exception as e:
        logger.error(f"Claude API 호출 실패: {str(e)}")
        return None

async def call_claude_with_knowledge(user_prompt: str, keyword_matches: List[dict] = None, max_tokens: int = 1000, session_id: str = None) -> tuple[Optional[str], Optional[float]]:
    """Claude가 키워드 DB 정보와 대화 컨텍스트를 참고해서 지능적인 답변을 생성
    
    Returns:
        tuple[Optional[str], Optional[float]]: (응답 텍스트, 응답 시간(ms))
    """
    if not claude_client:
        logger.warning("Claude 클라이언트가 초기화되지 않았습니다")
        return None, None
    
    try:
        # Claude API 호출 시간 측정 시작
        model_start_time = time.time()
        # 대화 컨텍스트 가져오기
        conversation_context = ""
        conversation_summary = ""
        conversation_flow = ""
        user_context = ""
        conversation_memory = ""
        if session_id:
            conversation_context = get_conversation_context(session_id)
            conversation_summary = get_conversation_summary(session_id)
            conversation_flow = get_conversation_flow(session_id)
            user_context = get_user_context(session_id)
            conversation_memory = get_conversation_memory(session_id)
        
        # 훈련 전문가로서의 시스템 컨텍스트 (최적화됨)
        system_context = """멋쟁이사자처럼 K-Digital Training 부트캠프 전문 AI 상담사입니다.

역할: 훈련생 질문에 정확하고 친절하게 답변, 규정/절차 명확 안내

전문분야: 훈련장려금(일일 15,800원, 80% 출석), 출결관리(QR체크, HRD앱), 공결신청, 온라인수업(줌), 노트북 대여, 수료조건

⚠️ 멋쟁이사자처럼 부트캠프 관련 정보만 제공. 타 기관 질문 시 정중히 거절."""

        # 대화 컨텍스트가 있는 경우 추가
        context_section = ""
        if conversation_context:
            context_section = f"""

💬 이전 대화: {conversation_context}
{conversation_summary}{conversation_flow}{user_context}{conversation_memory}
위 내용 참고하여 연속성 있게 답변."""

        if keyword_matches and len(keyword_matches) > 0:
            # 키워드 매칭된 정보들을 참고 자료로 활용 (최적화: 상위 2개, 100자)
            reference_info = "\n\n📚 참고:\n"
            for i, match in enumerate(keyword_matches[:2], 1):  # 상위 2개만
                reference_info += f"{i}. Q: {match['question']}\n"
                reference_info += f"   A: {match['answer'][:100]}{'...' if len(match['answer']) > 100 else ''}\n\n"
            
            enhanced_prompt = f"""{system_context}{context_section}

{reference_info}위 참고 정보를 바탕으로 다음 질문에 정확하고 자연스럽게 답변해주세요:

질문: {user_prompt}

답변 가이드: 참고 정보 기반 자연스러운 설명, 이전 대화 맥락 유지, 친근하고 전문적인 톤, 단계별 설명. 타사 질문은 정중히 거절."""
        else:
            # 키워드 매칭이 없는 경우 일반 대화
            enhanced_prompt = f"""{system_context}{context_section}

다음 질문에 멋쟁이사자처럼 부트캠프 상담사로서 답변해주세요:

질문: {user_prompt}

답변 가이드: 친근하고 도움되는 톤, 이전 대화 맥락 유지, 부트캠프 관련 정보 제공. 타사 질문은 정중히 거절."""
        
        # Claude API 호출
        response = claude_client.make_request(enhanced_prompt, max_tokens)
        
        # Claude API 호출 시간 측정 종료
        model_end_time = time.time()
        model_response_time_ms = (model_end_time - model_start_time) * 1000
        
        if response:
            logger.info(f"Claude 지식 기반 응답 생성 성공 (응답 시간: {model_response_time_ms:.2f}ms)")
            return response.strip(), model_response_time_ms
        else:
            logger.warning("Claude 지식 기반 응답이 비어있습니다")
            return None, model_response_time_ms
            
    except Exception as e:
        logger.error(f"Claude 지식 기반 응답 실패: {str(e)}")
        return None, None


@app.get(
    "/",
    summary="🏠 메인 페이지",
    description="라이언 헬퍼 AI 챗봇의 메인 페이지를 반환합니다. 정적 파일이 있으면 HTML을, 없으면 API 정보를 반환합니다.",
    response_description="메인 페이지 HTML 또는 API 상태 정보",
    tags=["Info"]
)
async def root():
    """
    ## 🏠 루트 엔드포인트
    
    라이언 헬퍼 AI 챗봇 서비스의 메인 페이지입니다.
    
    ### 📋 응답 데이터
    - **message**: 서비스 설명
    - **status**: 서버 상태
    - **model**: 사용 중인 AI 모델
    - **language**: 지원 언어
    """
    try:
        return FileResponse("static/index.html")
    except:
        return {
            "message": "라이언 헬퍼 AI 챗봇 API (하이브리드 시스템)", 
            "status": "running",
            "model": f"Keyword-based + {OLLAMA_MODEL}",
            "language": "Korean",
            "features": [
                "키워드 기반 빠른 응답",
                "AI 생성 응답 (Ollama)",
                "훈련 관련 정보 제공",
                "대화 기록 관리"
            ]
        }

@app.post(
    "/chat",
    response_model=ChatResponse,
    summary="🤖 멀티 AI 챗봇 대화",
    description="""
    ## 🚀 하이브리드 AI 시스템
    
    **Claude-3-Haiku** + **키워드 DB**를 활용한 지능형 챗봇
    
    ### 🎯 **AI 모델 우선순위**
    1. **Claude-3-Haiku** (기본) - 모든 대화와 전문 정보 처리
    2. **키워드 DB** (전문) - 훈련장려금, 출결 등 전문 정보
    
    ### 💡 **사용법**
    - `use_claude: true` (기본값) → Claude 지능형 응답 사용
    - `use_claude: false` → 키워드 DB만 사용
    
    ### 📝 **질문 예시**
    - 일반 대화: "안녕?", "코딩 질문 가능해?"
    - 전문 정보: "훈련장려금은 얼마인가요?"
    """,
    response_description="Claude 지능형 응답 및 메타데이터 (Enhanced/Keyword)",
    tags=["Chat"]
)
async def chat_with_hybrid(request: ChatRequest):
    """
    ## 🧠 Claude 지능형 AI 챗봇과 대화
    
    Claude가 키워드 DB를 참고해서 지능적이고 자연스러운 답변을 생성하는 시스템입니다.
    
    ### 🚀 처리 방식 (NEW!)
    1. **키워드 검색**: 관련 정보를 DB에서 검색
    2. **Claude 분석**: 검색된 정보를 참고해서 지능적 답변 생성
    3. **자연스러운 응답**: 기계적이지 않은 상담사 톤의 답변 제공
    
    ### 📝 요청 데이터
    - **prompt**: 사용자 질문 (필수)
    - **max_new_tokens**: Claude 응답 길이 (기본값: 1000)
    - **temperature**: 창의성 조절 (기본값: 0.7)
    - **use_claude**: Claude 사용 여부 (기본값: true)
    - **session_id**: 대화 세션 ID (선택사항)
    
    ### 🎯 응답 유형
    - **claude_enhanced**: Claude가 키워드 DB 참고한 지능적 응답
    - **keyword**: 키워드 기반 응답 (Claude 실패 시)
    - **fallback**: 기본 안내 응답
    
    ### 💡 주요 기능
    - 🎓 훈련장려금, 출결, 공결 관련 전문 상담
    - 💻 줌, 수업, 노트북 관련 자세한 안내
    - 🚀 취업, 인턴십, 커리어 맞춤 조언
    - 📚 추가 팁과 단계별 가이드 제공
    - 🤝 친근하고 전문적인 상담사 톤
    """
    
    # 전체 응답 시간 측정 시작
    total_start_time = time.time()
    model_response_time_ms = None
    
    try:
        # 입력 검증
        if not request.prompt or not request.prompt.strip():
            raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")
        
        # 간단한 로깅 (선택적)
        logger.info(f"사용자 질문: {request.prompt}")
        
        # 🚀 지능형 Claude 시스템: 키워드 DB + AI 하이브리드
        if request.use_claude:
            logger.info("🧠 Claude 지능형 응답 시스템 시작")
            
            # 1단계: 관련 키워드 정보 검색
            related_data = find_related_questions_smart(
                request.prompt, 
                limit=5,
                min_score=0.2,
                context_keywords=[]
            )
            
            # 2단계: Claude가 키워드 정보를 참고해서 지능적 답변 생성
            try:
                ai_response, model_response_time_ms = await call_claude_with_knowledge(
                    request.prompt,
                    keyword_matches=related_data,
                    max_tokens=request.max_new_tokens,
                    session_id=request.session_id
                )
                
                if ai_response and len(ai_response.strip()) > 10:
                    # 관련 질문들 변환
                    related_questions = []
                    if related_data:
                        for rq in related_data[:4]:
                            related_questions.append(RelatedQuestion(
                                id=str(rq.get("id", "unknown")),
                                question=rq["question"],
                                answer_preview=rq["answer"][:100] + "...",
                                score=rq["score"],
                                matched_keywords=rq.get("matched_keywords", [])
                            ))
                    
                    # 📝 대화 기록 저장
                    if request.session_id:
                        try:
                            save_message(request.session_id, "user", request.prompt)
                            save_message(request.session_id, "assistant", ai_response, 
                                       response_type="claude_enhanced", model_used="Claude-3-Haiku + Knowledge Base")
                        except Exception as e:
                            logger.warning(f"대화 기록 저장 실패: {str(e)}")
                    
                    # 전체 응답 시간 계산
                    total_response_time_ms = (time.time() - total_start_time) * 1000
                    
                    logger.info(f"✅ Claude 지능형 응답 생성 성공 (전체: {total_response_time_ms:.2f}ms, 모델: {model_response_time_ms:.2f}ms)")
                    return ChatResponse(
                        response=ai_response,
                        model="Claude-3-Haiku + Knowledge Base",
                        status="success",
                        matched_keywords=[kw for item in related_data for kw in item.get("matched_keywords", [])][:5],
                        response_type="claude_enhanced",
                        related_questions=related_questions,
                        total_related=len(related_data),
                        response_time_ms=total_response_time_ms,
                        model_response_time_ms=model_response_time_ms
                    )
                    
            except Exception as e:
                logger.error(f"Claude 지능형 응답 실패: {str(e)}")
                # Claude 실패 시 키워드 DB로 fallback
        
        # 🔍 Claude를 사용하지 않는 경우: 키워드 기반 처리
        else:
            logger.info("키워드 기반 처리 모드")
            
            # 질문 의도 분석
            user_intent = analyze_question_intent(request.prompt)
            logger.info(f"질문 의도 분석: {user_intent}")
            
            # 타사 정보 질문인 경우 제한 응답
            if user_intent.get("is_competitor_question", False):
                logger.info("타사 정보 질문 감지 - 제한 응답 제공")
                response = "죄송합니다. 저는 멋쟁이사자처럼 K-Digital Training 부트캠프와 관련된 질문만 답변드릴 수 있습니다. 멋쟁이사자처럼 부트캠프에 대해 궁금한 점이 있으시면 언제든지 물어보세요!"
            
            # 일반 대화인 경우 기본 응답 제공
            elif user_intent.get("is_general_conversation", False):
                logger.info("일반 대화 감지 - 기본 응답 제공")
                # 입력에 따른 적절한 응답 선택
                user_input_lower = request.prompt.lower().strip()
                
                if any(greeting in user_input_lower for greeting in ["hi", "hello", "안녕", "하이", "헬로"]):
                    response = "안녕하세요! 저는 멋쟁이사자처럼 K-Digital Training 부트캠프 전문 상담사입니다. 훈련장려금, 출결, 공결 등 무엇이든 궁금한 점을 물어보세요!"
                elif any(word in user_input_lower for word in ["감사", "고마워", "고맙"]):
                    response = "천만에요! 언제든지 궁금한 것이 있으시면 편하게 물어보세요."
                elif any(word in user_input_lower for word in ["잘지내", "어떻게", "뭐해"]):
                    response = "저는 훈련생 여러분을 돕기 위해 항상 대기하고 있어요! 궁금한 점이 있으시면 언제든 말씀해주세요."
                else:
                    response = "안녕하세요! 무엇을 도와드릴까요? 훈련장려금, 출결, 공결 등 궁금한 점을 물어보세요."
                
                total_response_time_ms = (time.time() - total_start_time) * 1000
                return ChatResponse(
                    response=response,
                    model="Smart Intent-based Response System",
                    status="greeting",
                    matched_keywords=[],
                    response_type="fallback",
                    related_questions=None,
                    total_related=0,
                    response_time_ms=total_response_time_ms,
                    model_response_time_ms=None
                )
            
            # 훈련 관련 질문인 경우 컨텍스트 검색 수행
            context_keywords = get_context_keywords(request.session_id) if request.session_id else []
            if context_keywords:
                logger.info(f"컨텍스트 키워드: {context_keywords}")
        
        # 🔍 키워드 기반 처리
        logger.info("키워드 기반 검색 모드 시작")
        
        # 📌 먼저 일반 대화 체크 (키워드 검색 전에)
        user_intent = analyze_question_intent(request.prompt)
        logger.info(f"질문 의도 분석: {user_intent}")
        
        # 타사 정보 질문인 경우 제한 응답
        if user_intent.get("is_competitor_question", False):
            logger.info("타사 정보 질문 감지 - 제한 응답 제공")
            response = "죄송합니다. 저는 멋쟁이사자처럼 K-Digital Training 부트캠프와 관련된 질문만 답변드릴 수 있습니다. 멋쟁이사자처럼 부트캠프에 대해 궁금한 점이 있으시면 언제든지 물어보세요!"
        
        # 일반 대화인 경우 키워드 검색 우회하고 바로 기본 응답
        elif user_intent.get("is_general_conversation", False):
            logger.info("일반 대화 감지 - 키워드 검색 우회하고 기본 응답 제공")
            user_input_lower = request.prompt.lower().strip()
            
            if any(greeting in user_input_lower for greeting in ["hi", "hello", "안녕", "하이", "헬로"]):
                response = "안녕하세요! 저는 멋쟁이사자처럼 K-Digital Training 부트캠프 전문 상담사입니다. 훈련장려금, 출결, 공결 등 무엇이든 궁금한 점을 물어보세요!"
            elif any(word in user_input_lower for word in ["감사", "고마워", "고맙"]):
                response = "천만에요! 언제든지 궁금한 것이 있으시면 편하게 물어보세요."
            elif any(word in user_input_lower for word in ["잘지내", "어떻게", "뭐해"]):
                response = "저는 훈련생 여러분을 돕기 위해 항상 대기하고 있어요! 궁금한 점이 있으시면 언제든 말씀해주세요."
            else:
                response = "안녕하세요! 무엇을 도와드릴까요? 훈련장려금, 출결, 공결 등 궁금한 점을 물어보세요."
            
            total_response_time_ms = (time.time() - total_start_time) * 1000
            return ChatResponse(
                response=response,
                model="Smart Intent-based Response System",
                status="greeting",
                matched_keywords=[],
                response_type="general_greeting",
                related_questions=None,
                total_related=0,
                response_time_ms=total_response_time_ms,
                model_response_time_ms=None
            )
        
        # 컨텍스트 키워드 추출
        context_keywords = get_context_keywords(request.session_id) if request.session_id else []
        if context_keywords:
            logger.info(f"컨텍스트 키워드: {context_keywords}")
        
        # 키워드 기반 빠른 응답 시도
        best_match, score, matched_keywords = find_best_match(request.prompt)
        
        # 관련 질문들 검색
        related_questions_data = find_related_questions_smart(
            request.prompt, 
            limit=8,
            min_score=0.2,
            context_keywords=context_keywords
        )
        related_questions = []
        
        # 🎯 키워드 기반 답변 선택 로직
        if related_questions_data and len(related_questions_data) > 0:
            # 최고 점수 질문을 주 답변으로 선택
            best_question = related_questions_data[0]
            
            # 🎯 훈련 관련 키워드에 대해서만 높은 품질 답변 제공
            if best_question["score"] > 4.0:  # 높은 신뢰도
                response = best_question["answer"]
                status = "success"
                response_type = "smart_keyword"
                model_name = "Smart Intent-based Response System"
                matched_keywords = best_question["matched_keywords"]
                
                # 관련 질문들만 별도로 준비 (답변에는 포함하지 않음)
                for rq in related_questions_data[1:]:
                    if rq["score"] > 1.5 and rq["id"] != best_question["id"]:  # 중복 제거
                        answer_preview = rq["answer"]
                        if len(answer_preview) > 80:
                            answer_preview = answer_preview[:80] + "..."
                        
                        related_questions.append(RelatedQuestion(
                            id=rq["id"],
                            question=rq["question"],
                            answer_preview=answer_preview,
                            score=rq["score"],
                            matched_keywords=rq["matched_keywords"]
                        ))
            
            elif best_question["score"] > 1.0:  # 중간 정도 관련성 (모든 키워드에 적용)
                response = best_question["answer"]
                status = "partial_match"
                response_type = "smart_keyword"
                model_name = "Smart Intent-based Response System"
                matched_keywords = best_question["matched_keywords"]
                
                # 관련 질문들 준비
                for rq in related_questions_data:
                    if rq["id"] != best_question["id"] and rq["score"] > 0.8:  # 메인 답변 제외
                        answer_preview = rq["answer"]
                        if len(answer_preview) > 80:
                            answer_preview = answer_preview[:80] + "..."
                        
                        related_questions.append(RelatedQuestion(
                            id=rq["id"],
                            question=rq["question"],
                            answer_preview=answer_preview,
                            score=rq["score"],
                            matched_keywords=rq["matched_keywords"]
                        ))
        else:
            # 매칭 실패 시 더 간단한 처리
            if related_questions_data and related_questions_data[0]["score"] > 0.5:
                # 낮은 점수지만 관련성이 있는 경우 가장 좋은 답변 하나만 제공
                best_question = related_questions_data[0]
                response = best_question["answer"]
                status = "low_confidence"
                response_type = "smart_keyword"
                model_name = "Smart Intent-based Response System"
                matched_keywords = best_question["matched_keywords"]
                
                # 나머지는 관련 질문으로만 제공
                for rq in related_questions_data[1:]:
                    if rq["score"] > 0.3:
                        answer_preview = rq["answer"]
                        if len(answer_preview) > 80:
                            answer_preview = answer_preview[:80] + "..."
                        
                        related_questions.append(RelatedQuestion(
                            id=rq["id"],
                            question=rq["question"],
                            answer_preview=answer_preview,
                            score=rq["score"],
                            matched_keywords=rq["matched_keywords"]
                        ))
            else:
                # 관련 없는 경우 기본 안내 메시지 제공
                response = "죄송합니다. 해당 질문에 대한 정확한 답변을 찾을 수 없습니다.\n\n구체적인 키워드(예: 훈련장려금, 출결, 줌 등)로 다시 질문해주시면 도움을 드릴 수 있습니다."
                status = "no_match"
                response_type = "fallback"
                model_name = "Smart Intent-based Response System"
                matched_keywords = []
        
        # 응답 데이터 유효성 검사
        if not response:
            response = "죄송합니다. 응답을 생성할 수 없습니다."
            status = "error"
        
        # 전체 응답 시간 계산
        total_response_time_ms = (time.time() - total_start_time) * 1000
        
        # 응답 객체 생성
        chat_response = ChatResponse(
            response=response,
            model=model_name,
            status=status,
            matched_keywords=matched_keywords if matched_keywords else [],
            response_type=response_type,
            related_questions=related_questions[:4] if related_questions else None,  # 최대 4개까지
            total_related=len(related_questions) if related_questions else 0,
            response_time_ms=total_response_time_ms,
            model_response_time_ms=model_response_time_ms
        )
        
        # 대화 기록 저장 (세션 ID가 있는 경우)
        if request.session_id:
            try:
                # 사용자 메시지 저장
                save_message(
                    request.session_id, 
                    "user", 
                    request.prompt
                )
                
                # 봇 응답 저장
                save_message(
                    request.session_id, 
                    "assistant", 
                    response,
                    response_type=response_type,
                    model_used=model_name
                )
                
                logger.info(f"대화 기록 저장 완료: session_id={request.session_id}")
            except Exception as e:
                logger.warning(f"대화 기록 저장 실패: {str(e)}")
        
        # 로그 추가 (질문-답변 쌍 기록)
        logger.info(f"챗봇 응답: response_type={response_type}, response_length={len(response)}")
        logger.info(f"응답 내용: {response[:100]}..." if len(response) > 100 else f"응답 내용: {response}")
        
        return chat_response
        
    except HTTPException:
        # HTTPException은 그대로 전달
        raise
    except Exception as e:
        logger.error(f"채팅 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"내부 서버 오류가 발생했습니다: {str(e)}")

@app.get(
    "/health",
    summary="🔍 서버 상태 확인",
    description="서버와 AI 모델의 상태를 확인합니다. 시스템 헬스체크 및 연결 상태를 점검할 수 있습니다.",
    response_description="서버 상태 및 모델 연결 정보",
    tags=["Health"]
)
def health_check():
    """
    ## 🔍 헬스체크 API
    
    서버와 AI 모델의 전반적인 상태를 확인합니다.
    
    ### 📊 체크 항목
    - **서버 상태**: 기본 서버 동작 확인
    - **Ollama 연결**: AI 모델 서버 연결 상태
    - **QA 데이터베이스**: 키워드 데이터 개수
    - **응답 모드**: 현재 설정된 응답 시스템
    
    ### 🎯 응답 상태
    - **healthy**: 정상 동작
    - **connected**: Ollama 연결 성공
    - **disconnected**: Ollama 연결 실패
    - **error**: Ollama 오류 발생
    """
    # Claude 상태 확인
    claude_status = "disconnected"
    if claude_client:
        try:
            # 간단한 연결 테스트
            test_result = claude_client.test_connection()
            claude_status = "connected" if test_result else "error"
        except:
            claude_status = "error"
    
    available_models = []
    if claude_status == "connected":
        available_models.append("Claude-3-Haiku")
    available_models.append("Keyword-based")
    
    return {
        "status": "healthy",
        "model": f"Intelligent: {' + '.join(available_models)}",
        "device": "CPU",
        "language": "Korean",
        "qa_count": len(QA_DATABASE),
        "claude_status": claude_status,
        "claude_available": bool(claude_client),
        "response_mode": "claude_enhanced_knowledge",
        "timeout_settings": "30s_graceful"
    }

@app.get(
    "/info",
    summary="ℹ️ 시스템 정보",
    description="AI 모델과 시스템 기능에 대한 상세 정보를 제공합니다.",
    response_description="모델 정보 및 시스템 기능 목록",
    tags=["Info"]
)
def get_info():
    """
    ## ℹ️ 시스템 정보 API
    
    사용 중인 AI 모델과 시스템의 주요 기능을 확인할 수 있습니다.
    
    ### 📋 제공 정보
    - **모델명**: 하이브리드 AI 시스템 정보
    - **모델 타입**: 시스템 구성 방식
    - **기능 목록**: 지원하는 주요 기능들
    - **QA 주제**: 키워드 기반 응답 가능한 주제들
    - **Ollama 모델**: 사용 중인 AI 모델명
    """
    available_ai_models = []
    if claude_client:
        available_ai_models.append("Claude-3-Haiku")
    
    return {
        "model_name": f"Intelligent System: {' + '.join(available_ai_models) if available_ai_models else 'Keyword-based'}",
        "model_type": "Claude-Enhanced Knowledge System",
        "description": "Claude가 키워드 DB를 참고해서 지능적 답변을 생성하는 시스템",
        "capabilities": [
            "한국어 대화",
            "지능형 질문 답변 (Claude + Knowledge Base)",
            "키워드 기반 정보 검색",
            "자연스러운 AI 응답",
            "훈련 관련 전문 정보 제공",
            "맥락 기반 추가 안내"
        ],
        "available_models": {
            "keyword_based": {
                "available": True,
                "qa_topics_count": len(QA_DATABASE)
            }
        },
        "qa_topics": list(QA_DATABASE.keys())
    }

@app.get(
    "/search",
    summary="🔍 검색 엔진 - 관련 질문 검색",
    description="검색어를 입력하면 관련된 모든 질문들을 관련도 점수순으로 반환합니다. 검색 엔진처럼 작동합니다.",
    response_description="관련 질문들과 점수 정보",
    tags=["Search"]
)
def search_questions(
    query: str,
    limit: Optional[int] = 10,
    min_score: Optional[float] = 0.1
):
    """
    ## 🔍 검색 엔진 - 관련 질문 검색
    
    사용자가 입력한 검색어와 관련된 모든 질문들을 관련도 점수순으로 반환합니다.
    기존 챗봇과 달리 단일 답변이 아닌 관련 질문들을 모두 나열하여 사용자가 선택할 수 있게 합니다.
    
    ### 🔍 쿼리 매개변수
    - **query**: 검색할 질문이나 키워드 (필수)
      - 예: "훈련장려금", "출결 관련", "줌 설정 방법"
    - **limit**: 최대 결과 개수 (기본값: 10)
    - **min_score**: 최소 관련도 점수 (기본값: 0.1)
    
    ### 📋 응답 정보
    - **query**: 검색한 질문/키워드
    - **total_found**: 조건을 만족하는 총 결과 개수
    - **results**: 검색 결과 배열 (관련도 점수순 정렬)
      - **id**: QA 고유 식별자
      - **question**: 질문 내용
      - **answer**: 답변 내용 (미리보기)
      - **keywords**: 매칭된 키워드 목록
      - **score**: 관련도 점수 (0.0-10.0)
      - **match_type**: 매칭 유형 (exact/partial/similarity)
    
    ### 🎯 활용 방법
    - **검색 엔진 형태**: 사용자가 검색하면 관련 질문들을 모두 표시
    - **FAQ 탐색**: 비슷한 질문들을 한 번에 확인
    - **키워드 기반 탐색**: 특정 주제의 모든 관련 정보 탐색
    
    ### 📊 점수 계산 방식
    - **정확한 키워드 매칭**: 5점
    - **부분 키워드 매칭**: 2점  
    - **질문 유사도**: 최대 1점
    - **답변 유사도**: 최대 0.5점
    """
    
    if not query or not query.strip():
        raise HTTPException(status_code=400, detail="검색어를 입력해주세요.")
    
    search_results = []
    query_lower = query.lower().strip()
    
    # 모든 QA에 대해 관련도 점수 계산
    for qa_id, qa_data in QA_DATABASE.items():
        score = 0
        matched_keywords = []
        match_types = []
        
        # 1. 정확한 키워드 매칭 (높은 가중치)
        for keyword in qa_data["keywords"]:
            keyword_lower = keyword.lower()
            if keyword_lower in query_lower:
                score += 5  # 정확한 매칭은 높은 점수
                matched_keywords.append(keyword)
                if "exact" not in match_types:
                    match_types.append("exact")
        
        # 2. 부분 키워드 매칭 (중간 가중치)
        for keyword in qa_data["keywords"]:
            keyword_lower = keyword.lower()
            if len(keyword_lower) >= 2:  # 2글자 이상 키워드만
                # 검색어의 각 단어와 비교
                query_words = query_lower.replace('?', '').replace('!', '').replace('.', '').split()
                for word in query_words:
                    if len(word) >= 2:
                        # 키워드가 단어에 포함되거나, 단어가 키워드에 포함되는 경우
                        if (keyword_lower in word or word in keyword_lower) and keyword not in matched_keywords:
                            score += 2  # 부분 매칭은 중간 점수
                            matched_keywords.append(keyword)
                            if "partial" not in match_types:
                                match_types.append("partial")
        
        # 3. 질문 유사도 (낮은 가중치)
        question_similarity = SequenceMatcher(None, query_lower, qa_data["question"].lower()).ratio()
        if question_similarity > 0.3:  # 30% 이상 유사할 때만
            score += question_similarity * 1  # 낮은 가중치
            if "similarity" not in match_types:
                match_types.append("similarity")
        
        # 4. 답변 내용 유사도 (매우 낮은 가중치)
        answer_similarity = SequenceMatcher(None, query_lower, qa_data["answer"].lower()).ratio()
        if answer_similarity > 0.4:  # 40% 이상 유사할 때만
            score += answer_similarity * 0.5  # 매우 낮은 가중치
            if "similarity" not in match_types:
                match_types.append("similarity")
        
        # 최소 점수 이상인 경우만 결과에 포함
        if score >= min_score:
            # 답변 미리보기 (100자 제한)
            answer_preview = qa_data["answer"]
            if len(answer_preview) > 100:
                answer_preview = answer_preview[:100] + "..."
            
            search_results.append({
                "id": qa_id,
                "question": qa_data["question"],
                "answer": qa_data["answer"],
                "answer_preview": answer_preview,
                "keywords": qa_data["keywords"],
                "matched_keywords": matched_keywords,
                "score": round(score, 2),
                "match_type": "/".join(match_types) if match_types else "none"
            })
    
    # 점수순으로 정렬 (높은 점수부터)
    search_results.sort(key=lambda x: x["score"], reverse=True)
    
    # 결과 개수 제한
    limited_results = search_results[:limit]
    
    return {
        "query": query,
        "total_found": len(search_results),
        "showing": len(limited_results),
        "min_score": min_score,
        "results": limited_results
    }

@app.get(
    "/qa-list",
    summary="❓ QA 목록 조회",
    description="키워드 기반 응답이 가능한 등록된 질문답변 목록을 확인합니다. 키워드로 필터링 가능합니다.",
    response_description="QA 목록과 키워드 정보",
    tags=["QA"]
)
def get_qa_list(keyword: Optional[str] = None):
    """
    ## ❓ QA 목록 조회 API
    
    시스템에 등록된 모든 질문답변 쌍을 조회하거나 특정 키워드로 필터링할 수 있습니다.
    이 API는 키워드 검색, QA 관리, 프론트엔드 연동에 사용됩니다.
    
    ### 🔍 쿼리 매개변수
    - **keyword**: 특정 키워드로 필터링 (선택사항)
      - 예: `?keyword=훈련장려금` - 훈련장려금 관련 QA만 조회
      - 예: `?keyword=출결` - 출결 관련 QA만 조회
      - 예: `?keyword=줌` - 줌 관련 QA만 조회
    
    ### 📋 응답 정보
    - **total_count**: 조회된 QA 총 개수
    - **keyword_filter**: 적용된 키워드 필터 (없으면 null)
    - **qa_list**: QA 목록 배열
      - **id**: QA 고유 식별자
      - **question**: 질문 내용
      - **answer**: 답변 내용
      - **keywords**: 매칭 키워드 목록
    
    ### 💡 활용 방법
    - **전체 QA 조회**: `/qa-list` - 모든 QA 목록
    - **키워드 검색**: `/qa-list?keyword=훈련장려금` - 특정 키워드 관련 QA
    - **프론트엔드 연동**: 메인 페이지 키워드 버튼 클릭 시 사용
    - **개발/테스트**: API 동작 확인 및 QA 데이터 검증
    
    ### 📊 주요 키워드 카테고리
    - **훈련장려금**: 계좌, 금액, 지급시기, 수령 관련
    - **출결**: QR코드, 지각, 결석, 공결 관련  
    - **줌**: 배경화면, 설정, 접속, 카메라 관련
    - **노트북**: 대여, 반납, 고장, 수리 관련
    - **교육**: 수업, 강의, 교재, 평가 관련
    - **행정**: 서류, 증명서, 계좌, 휴가 관련
    """
    qa_list = []
    
    for qa_id, qa_data in QA_DATABASE.items():
        # 키워드 필터링
        if keyword:
            # 키워드가 QA의 키워드 목록에 포함되는지 확인 (대소문자 무시)
            keyword_lower = keyword.lower()
            if not any(keyword_lower in kw.lower() for kw in qa_data["keywords"]):
                continue
        
        qa_list.append({
            "id": qa_id,
            "question": qa_data["question"],
            "answer": qa_data["answer"],
            "keywords": qa_data["keywords"]
        })
    
    return {
        "total_count": len(qa_list),
        "keyword_filter": keyword,
        "qa_list": qa_list
    }



# === 대화 기록 관리 API ===

@app.post(
    "/sessions",
    response_model=Session,
    summary="💬 새 대화 세션 생성",
    description="새로운 채팅 세션을 생성합니다. 대화 기록을 구분하여 관리할 수 있습니다.",
    response_description="생성된 세션 정보",
    tags=["Sessions"]
)
def create_new_session(session_data: SessionCreate):
    """
    ## 💬 새 대화 세션 생성
    
    새로운 채팅 세션을 생성하여 대화를 시작할 수 있습니다.
    
    ### 📝 요청 데이터
    - **title**: 세션 제목 (선택, 기본값: "새로운 대화")
    
    ### 📋 응답 데이터
    - **id**: 세션 고유 ID
    - **title**: 세션 제목
    - **created_at**: 생성 시간
    - **updated_at**: 최종 업데이트 시간
    
    ### 💡 활용 방법
    - 주제별로 대화를 구분하여 관리
    - 세션 ID를 챗봇 API에 전달하여 연속 대화
    - 대화 기록 추적 및 관리
    """
    session_id = create_session(session_data.title)
    sessions = get_sessions()
    for session in sessions:
        if session.id == session_id:
            return session
    raise HTTPException(status_code=500, detail="세션 생성에 실패했습니다.")

@app.get(
    "/sessions",
    response_model=List[Session],
    summary="📋 대화 세션 목록 조회",
    description="모든 채팅 세션의 목록을 최신순으로 조회합니다.",
    response_description="세션 목록 (최신순 정렬)",
    tags=["Sessions"]
)
def list_sessions():
    """
    ## 📋 대화 세션 목록 조회
    
    생성된 모든 채팅 세션을 최신 업데이트 순으로 조회합니다.
    
    ### 📋 응답 데이터
    - **Array of Session**: 세션 목록
      - **id**: 세션 고유 ID
      - **title**: 세션 제목
      - **created_at**: 생성 시간
      - **updated_at**: 최종 업데이트 시간
    
    ### 🔄 정렬 기준
    - 최근 업데이트된 세션이 먼저 표시
    - 활발한 대화 세션을 우선적으로 확인 가능
    """
    return get_sessions()

@app.get(
    "/sessions/{session_id}/messages",
    response_model=List[Message],
    summary="💬 세션 메시지 조회",
    description="특정 세션의 모든 메시지를 시간순으로 조회합니다.",
    response_description="메시지 목록 (시간순 정렬)",
    tags=["Sessions"]
)
def get_messages(session_id: str):
    """
    ## 💬 세션 메시지 조회
    
    특정 세션의 모든 대화 메시지를 시간 순서대로 조회합니다.
    
    ### 🔗 경로 매개변수
    - **session_id**: 세션 고유 ID
    
    ### 📋 응답 데이터
    - **Array of Message**: 메시지 목록
      - **id**: 메시지 고유 ID
      - **session_id**: 세션 ID
      - **role**: 발신자 (user/assistant)
      - **content**: 메시지 내용
      - **response_type**: 응답 유형 (keyword/ollama)
      - **model_used**: 사용된 모델명
      - **created_at**: 생성 시간
    
    ### 🔄 정렬 기준
    - 시간순 정렬 (오래된 메시지부터)
    - 대화 흐름을 자연스럽게 추적 가능
    """
    messages = get_session_messages(session_id)
    if not messages:
        # 빈 세션이거나 존재하지 않는 세션인지 확인
        sessions = get_sessions()
        session_exists = any(s.id == session_id for s in sessions)
        if not session_exists:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return messages

@app.delete(
    "/sessions/{session_id}",
    summary="🗑️ 세션 삭제",
    description="지정된 세션과 관련된 모든 메시지를 삭제합니다.",
    response_description="삭제 완료 메시지",
    tags=["Sessions"]
)
def remove_session(session_id: str):
    """
    ## 🗑️ 세션 삭제
    
    지정된 세션과 해당 세션의 모든 메시지를 영구적으로 삭제합니다.
    
    ### 🔗 경로 매개변수
    - **session_id**: 삭제할 세션 ID
    
    ### ⚠️ 주의사항
    - 삭제된 세션과 메시지는 복구할 수 없습니다
    - 삭제 전에 중요한 대화 내용을 백업하세요
    
    ### 📋 응답 데이터
    - **message**: 삭제 완료 메시지
    - **session_id**: 삭제된 세션 ID
    """
    try:
        delete_session(session_id)
        return {"message": "세션이 삭제되었습니다.", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"세션 삭제 중 오류가 발생했습니다: {str(e)}")

@app.put(
    "/sessions/{session_id}/title",
    summary="✏️ 세션 제목 변경",
    description="지정된 세션의 제목을 변경합니다.",
    response_description="제목 변경 완료 메시지",
    tags=["Sessions"]
)
def rename_session(session_id: str, title_data: dict):
    """
    ## ✏️ 세션 제목 변경
    
    지정된 세션의 제목을 새로운 제목으로 변경합니다.
    
    ### 🔗 경로 매개변수
    - **session_id**: 제목을 변경할 세션 ID
    
    ### 📝 요청 데이터
    - **title**: 새로운 세션 제목 (필수)
    
    ### 📋 응답 데이터
    - **message**: 변경 완료 메시지
    - **session_id**: 세션 ID
    - **title**: 변경된 제목
    
    ### 💡 활용 예시
    ```json
    {
      "title": "훈련장려금 및 출결 문의"
    }
    ```
    """
    title = title_data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="제목을 입력해주세요.")
    
    try:
        update_session_title(session_id, title)
        return {"message": "세션 제목이 변경되었습니다.", "session_id": session_id, "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제목 변경 중 오류가 발생했습니다: {str(e)}")

@app.get(
    "/sessions/{session_id}",
    response_model=Session,
    summary="🔍 세션 정보 조회",
    description="지정된 세션의 상세 정보를 조회합니다.",
    response_description="세션 상세 정보",
    tags=["Sessions"]
)
def get_session_info(session_id: str):
    """
    ## 🔍 세션 정보 조회
    
    지정된 세션의 상세 정보를 조회합니다.
    
    ### 🔗 경로 매개변수
    - **session_id**: 조회할 세션 ID
    
    ### 📋 응답 데이터
    - **id**: 세션 고유 ID
    - **title**: 세션 제목
    - **created_at**: 생성 시간
    - **updated_at**: 최종 업데이트 시간
    
    ### 🚫 오류 응답
    - **404**: 세션을 찾을 수 없음
    """
    sessions = get_sessions()
    for session in sessions:
        if session.id == session_id:
            return session
    raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

# 슬랙 관련 엔드포인트들
@app.post(
    "/slack/sync",
    summary="🔄 슬랙 이슈 동기화",
    description="슬랙 채널에서 이슈 메시지를 가져와서 데이터베이스에 저장합니다.",
    response_description="동기화 결과",
    tags=["Slack"]
)
async def sync_slack_issues_endpoint(request: SlackSyncRequest):
    """
    ## 🔄 슬랙 이슈 동기화
    
    지정된 슬랙 채널에서 이슈 알림 메시지를 가져와서 데이터베이스에 저장합니다.
    
    ### 📝 요청 데이터
    - **hours**: 동기화할 시간 범위 (기본값: 24시간)
    - **force**: 강제 동기화 여부 (기본값: false)
    
    ### 📋 응답 데이터
    - **success**: 동기화 성공 여부
    - **message**: 결과 메시지
    - **new_issues**: 새로 추가된 이슈 수
    - **skipped_issues**: 건너뛴 이슈 수 (중복)
    - **errors**: 오류 발생 수
    - **total_messages**: 처리된 총 메시지 수
    
    ### 💡 활용 방법
    - 정기적으로 호출하여 새로운 이슈 수집
    - 중복 데이터는 자동으로 건너뜀
    - 파싱 가능한 이슈 메시지만 저장
    """
    if not SLACK_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="슬랙 봇 토큰이 설정되지 않았습니다. SLACK_BOT_TOKEN 환경변수를 설정해주세요.")
    
    result = await sync_slack_issues(request.hours, request.force)
    return result

@app.get(
    "/slack/issues",
    response_model=List[SlackIssue],
    summary="📋 슬랙 이슈 목록 조회",
    description="저장된 슬랙 이슈들을 조회합니다.",
    response_description="슬랙 이슈 목록",
    tags=["Slack"]
)
def list_slack_issues_endpoint(
    limit: Optional[int] = 50,
    project: Optional[str] = None
):
    """
    ## 📋 슬랙 이슈 목록 조회
    
    데이터베이스에 저장된 슬랙 이슈들을 조회합니다.
    
    ### 🔍 쿼리 매개변수
    - **limit**: 조회할 최대 이슈 수 (기본값: 50)
    - **project**: 프로젝트명으로 필터링 (선택)
    
    ### 📋 응답 데이터
    각 이슈는 다음 정보를 포함합니다:
    - **id**: 이슈 고유 ID
    - **project**: 프로젝트/과정명
    - **issue_type**: 이슈 유형 (프론트엔드, 백엔드, 훈련장려금 등)
    - **author**: 작성자
    - **content**: 이슈 내용
    - **raw_message**: 원본 슬랙 메시지
    - **created_at**: 저장 시간
    
    ### 💡 활용 방법
    - 최근 이슈 현황 파악
    - 프로젝트별 이슈 필터링
    - 이슈 통계 및 분석
    """
    return get_slack_issues(limit=limit, project=project)

@app.get(
    "/slack/issues/stats",
    summary="📊 슬랙 이슈 통계",
    description="저장된 슬랙 이슈들의 통계 정보를 제공합니다.",
    response_description="이슈 통계 정보",
    tags=["Slack"]
)
def get_slack_issue_stats():
    """
    ## 📊 슬랙 이슈 통계
    
    저장된 슬랙 이슈들의 다양한 통계 정보를 제공합니다.
    
    ### 📋 응답 데이터
    - **total_issues**: 총 이슈 수
    - **by_project**: 프로젝트별 이슈 수
    - **by_type**: 이슈 유형별 수
    - **by_author**: 작성자별 이슈 수
    - **recent_issues**: 최근 이슈들 (최대 10개)
    
    ### 💡 활용 방법
    - 이슈 현황 대시보드
    - 프로젝트별 이슈 분포 파악
    - 작성자별 활동 분석
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 총 이슈 수
        cursor.execute("SELECT COUNT(*) FROM slack_issues")
        total_issues = cursor.fetchone()[0]
        
        # 프로젝트별 통계
        cursor.execute("""
            SELECT project, COUNT(*) as count 
            FROM slack_issues 
            GROUP BY project 
            ORDER BY count DESC
        """)
        by_project = dict(cursor.fetchall())
        
        # 이슈 유형별 통계
        cursor.execute("""
            SELECT issue_type, COUNT(*) as count 
            FROM slack_issues 
            GROUP BY issue_type 
            ORDER BY count DESC
        """)
        by_type = dict(cursor.fetchall())
        
        # 작성자별 통계
        cursor.execute("""
            SELECT author, COUNT(*) as count 
            FROM slack_issues 
            GROUP BY author 
            ORDER BY count DESC 
            LIMIT 10
        """)
        by_author = dict(cursor.fetchall())
        
        # 최근 이슈들
        cursor.execute("""
            SELECT project, issue_type, author, content, created_at
            FROM slack_issues 
            ORDER BY created_at DESC 
            LIMIT 10
        """)
        recent_rows = cursor.fetchall()
        recent_issues = [
            {
                "project": row[0],
                "issue_type": row[1],
                "author": row[2],
                "content": row[3][:100] + "..." if len(row[3]) > 100 else row[3],
                "created_at": row[4]
            }
            for row in recent_rows
        ]
        
        return {
            "total_issues": total_issues,
            "by_project": by_project,
            "by_type": by_type,
            "by_author": by_author,
            "recent_issues": recent_issues
        }
        
    finally:
        conn.close()

# 피드백 및 개선 관련 엔드포인트들
@app.post(
    "/feedback",
    summary="📝 답변 피드백 제출",
    description="AI 답변에 대한 사용자 피드백을 수집합니다.",
    response_description="피드백 저장 결과",
    tags=["Feedback"]
)
async def submit_feedback(request: FeedbackRequest):
    """
    ## 📝 답변 피드백 제출
    
    AI 답변에 대한 사용자 피드백을 수집하여 답변 품질 개선에 활용합니다.
    
    ### 📝 요청 데이터
    - **session_id**: 세션 ID
    - **message_id**: 메시지 ID
    - **feedback_type**: 피드백 유형 (positive, negative, correction)
    - **feedback_content**: 피드백 내용 (선택사항)
    - **user_correction**: 사용자 수정 내용 (correction 타입일 때)
    
    ### 📋 응답 데이터
    - **success**: 저장 성공 여부
    - **message**: 결과 메시지
    """
    try:
        # 해당 메시지 정보 가져오기
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT content FROM messages 
            WHERE id = %s AND session_id = ?
        ''', (request.message_id, request.session_id))
        
        message_result = cursor.fetchone()
        if not message_result:
            conn.close()
            raise HTTPException(status_code=404, detail="메시지를 찾을 수 없습니다.")
        
        # 사용자 질문과 AI 답변 구분 (간단한 방식)
        ai_answer = message_result[0]
        
        # 이전 사용자 메시지 찾기
        cursor.execute('''
            SELECT content FROM messages 
            WHERE session_id = %s AND role = 'user'
            ORDER BY created_at DESC
            LIMIT 1
        ''', (request.session_id,))
        
        user_question_result = cursor.fetchone()
        user_question = user_question_result[0] if user_question_result else "질문을 찾을 수 없음"
        
        conn.close()
        
        # 피드백 저장
        success = save_answer_feedback(
            session_id=request.session_id,
            message_id=request.message_id,
            user_question=user_question,
            ai_answer=ai_answer,
            feedback_type=request.feedback_type,
            feedback_content=request.feedback_content,
            user_correction=request.user_correction
        )
        
        if success:
            return {
                "success": True,
                "message": "피드백이 성공적으로 저장되었습니다."
            }
        else:
            raise HTTPException(status_code=500, detail="피드백 저장에 실패했습니다.")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"피드백 처리 오류: {str(e)}")

@app.get(
    "/feedback/analysis",
    summary="📊 피드백 분석 결과",
    description="수집된 피드백을 분석하여 개선점을 제시합니다.",
    response_description="피드백 분석 결과",
    tags=["Feedback"]
)
def get_feedback_analysis():
    """
    ## 📊 피드백 분석 결과
    
    수집된 사용자 피드백을 분석하여 답변 품질 개선점을 제시합니다.
    
    ### 📋 응답 데이터
    - **problematic_questions**: 부정적 피드백이 많은 질문들
    - **common_corrections**: 자주 수정되는 답변 패턴들
    - **feedback_stats**: 전체 피드백 통계
    """
    try:
        analysis_result = analyze_feedback_patterns()
        return {
            "success": True,
            "data": analysis_result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"피드백 분석 오류: {str(e)}")

@app.get(
    "/improvement/suggestions",
    summary="💡 답변 개선 제안",
    description="슬랙 이슈와 피드백을 기반으로 답변 개선 제안을 생성합니다.",
    response_description="개선 제안 목록",
    tags=["Feedback"]
)
def get_improvement_suggestions():
    """
    ## 💡 답변 개선 제안
    
    슬랙 이슈 데이터와 사용자 피드백을 분석하여 답변 품질 개선 제안을 생성합니다.
    
    ### 📋 응답 데이터
    - **suggestions**: 개선 제안 목록
    - **priority_issues**: 우선순위가 높은 이슈들
    - **improvement_areas**: 개선이 필요한 영역들
    """
    try:
        # 슬랙 이슈 기반 제안
        issue_suggestions = get_improvement_suggestions_from_issues()
        
        # 피드백 기반 분석
        feedback_analysis = analyze_feedback_patterns()
        
        # 우선순위 이슈 식별
        priority_issues = [s for s in issue_suggestions if s.get("priority") == "high"]
        
        # 개선 영역 분류
        improvement_areas = {}
        for suggestion in issue_suggestions:
            area = suggestion.get("issue_type", "기타")
            if area not in improvement_areas:
                improvement_areas[area] = []
            improvement_areas[area].append(suggestion)
        
        return {
            "success": True,
            "data": {
                "suggestions": issue_suggestions,
                "priority_issues": priority_issues,
                "improvement_areas": improvement_areas,
                "feedback_analysis": feedback_analysis
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"개선 제안 생성 오류: {str(e)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))
    
    print("🚀 멋쟁이사자처럼 AI 챗봇 서버 시작!")
    print(f"📍 포트: {port}")
    print(f"🤖 Claude: {'✅ 연결됨' if claude_client else '❌ 연결 안됨'}")
# GPT 관련 코드 제거됨
    print(f"📚 QA 데이터베이스: {len(QA_DATABASE)}개 항목 로드됨")
    print("🌐 http://localhost:8001 에서 접속 가능합니다")
    
    uvicorn.run(app, host="0.0.0.0", port=port)