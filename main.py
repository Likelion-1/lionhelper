
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel
from typing import Optional, List
import uvicorn
import logging
from difflib import SequenceMatcher
import requests
import json
import uuid
from datetime import datetime
import sqlite3
import os

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ollama 설정
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gpt-oss:20b")  # 환경변수로 설정 가능

# 외부 Ollama 서비스 URL (필요시 사용)
EXTERNAL_OLLAMA_URL = os.getenv("EXTERNAL_OLLAMA_URL", "")

# 데이터베이스 초기화
def init_database():
    """SQLite 데이터베이스 초기화"""
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    # 세션 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 메시지 테이블
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            response_type TEXT,
            model_used TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES sessions (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# 데이터베이스 초기화 실행
init_database()

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
    }
}

# FastAPI 앱 초기화
app = FastAPI(
    title="한국어 AI 챗봇", 
    version="3.0.0",
    description="한국어에 특화된 AI 챗봇 서비스 (키워드 기반 + Ollama GPT-OSS-20B)"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 전역 예외 핸들러 추가
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """모든 예외에 대해 JSON 응답을 보장합니다."""
    logger.error(f"예상치 못한 오류: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"내부 서버 오류: {str(exc)}"}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """요청 검증 오류에 대한 JSON 응답을 보장합니다."""
    logger.error(f"요청 검증 오류: {str(exc)}")
    return JSONResponse(
        status_code=422,
        content={"detail": "요청 데이터가 유효하지 않습니다.", "errors": exc.errors()}
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP 예외에 대한 JSON 응답을 보장합니다."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# 정적 파일 서빙 설정
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    pass

print("하이브리드 AI 챗봇 시스템이 로드되었습니다.")
print(f"Ollama 모델: {OLLAMA_MODEL}")

# Pydantic 모델
class ChatRequest(BaseModel):
    prompt: str
    session_id: Optional[str] = None
    max_new_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.6
    top_p: Optional[float] = 0.9
    use_ollama: Optional[bool] = True  # Ollama 사용 여부

class ChatResponse(BaseModel):
    response: str
    model: str
    status: str
    session_id: str
    message_id: str
    matched_keywords: Optional[list] = None
    response_type: str  # "keyword" 또는 "ollama"

class SessionCreate(BaseModel):
    title: Optional[str] = "새로운 대화"

class Session(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    
class Message(BaseModel):
    id: str
    session_id: str
    role: str  # "user" 또는 "assistant"
    content: str
    response_type: Optional[str] = None
    model_used: Optional[str] = None
    created_at: str

def find_best_match(user_input: str) -> tuple:
    """사용자 입력과 가장 잘 매칭되는 QA를 찾습니다."""
    user_input_lower = user_input.lower()
    best_match = None
    best_score = 0
    matched_keywords = []
    
    for qa_id, qa_data in QA_DATABASE.items():
        score = 0
        keywords_found = []
        
        # 키워드 매칭
        for keyword in qa_data["keywords"]:
            if keyword.lower() in user_input_lower:
                score += 2
                keywords_found.append(keyword)
        
        # 질문과의 유사도 계산
        question_similarity = SequenceMatcher(None, user_input_lower, qa_data["question"].lower()).ratio()
        score += question_similarity * 3
        
        if score > best_score:
            best_score = score
            best_match = qa_data
            matched_keywords = keywords_found
    
    return best_match, best_score, matched_keywords

def create_session(title: str = "새로운 대화") -> str:
    """새로운 채팅 세션 생성"""
    session_id = str(uuid.uuid4())
    conn = sqlite3.connect('chat_history.db')
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
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO messages (id, session_id, role, content, response_type, model_used)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (message_id, session_id, role, content, response_type, model_used))
    
    # 세션 업데이트 시간 갱신
    cursor.execute('''
        UPDATE sessions SET updated_at = CURRENT_TIMESTAMP WHERE id = ?
    ''', (session_id,))
    
    conn.commit()
    conn.close()
    return message_id

def get_sessions() -> List[Session]:
    """모든 세션 목록 조회"""
    conn = sqlite3.connect('chat_history.db')
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
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, session_id, role, content, response_type, model_used, created_at
        FROM messages 
        WHERE session_id = ?
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
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    cursor.execute('DELETE FROM messages WHERE session_id = ?', (session_id,))
    cursor.execute('DELETE FROM sessions WHERE id = ?', (session_id,))
    
    conn.commit()
    conn.close()

def update_session_title(session_id: str, title: str):
    """세션 제목 업데이트"""
    conn = sqlite3.connect('chat_history.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE sessions SET title = ?, updated_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    ''', (title, session_id))
    
    conn.commit()
    conn.close()

async def call_ollama(prompt: str, max_tokens: int = 512, temperature: float = 0.6) -> str:
    """Ollama API를 호출하여 응답을 받습니다."""
    
    # 입력 검증
    if not prompt or not prompt.strip():
        return "입력이 비어있습니다."
    
    # 여러 URL을 시도 (Render.com 서비스 간 통신)
    urls_to_try = [
        OLLAMA_BASE_URL,
        "http://korean-chatbot-ollama:11434",
        "http://ollama:11434",
        "http://lionhelper-ollama:11434",  # 실제 서비스 이름일 수 있음
        "http://lionhelper-ollama.onrender.com:11434",  # 외부 URL 시도
        "http://localhost:11434"
    ]
    
    # 외부 Ollama 서비스가 설정되어 있으면 추가
    if EXTERNAL_OLLAMA_URL:
        urls_to_try.insert(0, EXTERNAL_OLLAMA_URL)
    
    for url in urls_to_try:
        try:
            full_url = f"{url}/api/generate"
            logger.info(f"Ollama 연결 시도: {full_url}")
            
            payload = {
                "model": OLLAMA_MODEL,
                "prompt": f"다음 질문에 대해 한국어로 친절하고 정확하게 답변해주세요: {prompt}",
                "stream": False,
                "options": {
                    "num_predict": max_tokens,
                    "temperature": temperature
                }
            }
            
            response = requests.post(full_url, json=payload, timeout=30)
            response.raise_for_status()
            
            # JSON 응답 처리
            try:
                result = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"Ollama JSON 파싱 오류 ({url}): {str(e)}")
                continue
            
            # 응답 검증
            if not isinstance(result, dict):
                logger.error(f"Ollama 응답이 딕셔너리가 아님 ({url}): {type(result)}")
                continue
                
            ollama_response = result.get("response", "").strip()
            if not ollama_response:
                logger.warning(f"Ollama 빈 응답 받음 ({url})")
                continue
            
            logger.info(f"Ollama 연결 성공: {url}")
            return ollama_response
            
        except requests.exceptions.Timeout:
            logger.warning(f"Ollama 타임아웃 ({url})")
            continue
        except requests.exceptions.ConnectionError:
            logger.warning(f"Ollama 연결 오류 ({url})")
            continue
        except requests.exceptions.RequestException as e:
            logger.warning(f"Ollama 요청 실패 ({url}): {str(e)}")
            continue
        except Exception as e:
            logger.error(f"Ollama 처리 오류 ({url}): {str(e)}")
            continue
    
    # 모든 연결 시도 실패
    logger.error("모든 Ollama 연결 시도 실패")
    logger.error(f"시도한 URL들: {urls_to_try}")
    return "죄송합니다. AI 모델에 연결할 수 없습니다. 키워드 기반 응답만 사용 가능합니다."

@app.get("/")
async def root():
    try:
        return FileResponse("static/index.html")
    except:
        return {
            "message": "한국어 AI 챗봇 API (하이브리드 시스템)", 
            "status": "running",
            "model": f"Keyword-based + {OLLAMA_MODEL}",
            "language": "Korean"
        }

@app.post("/chat", response_model=ChatResponse)
async def chat_with_hybrid(request: ChatRequest):
    """하이브리드 시스템을 사용하여 대화를 수행합니다."""
    
    try:
        # 입력 검증
        if not request.prompt or not request.prompt.strip():
            raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")
        
        # 세션 처리
        session_id = request.session_id
        if not session_id:
            # 새 세션 생성 (첫 메시지의 일부를 제목으로 사용)
            title = request.prompt[:30] + "..." if len(request.prompt) > 30 else request.prompt
            session_id = create_session(title)
        
        # 사용자 메시지 저장
        user_message_id = save_message(session_id, "user", request.prompt)
        
        # 1단계: 키워드 기반 빠른 응답 시도
        best_match, score, matched_keywords = find_best_match(request.prompt)
        
        if best_match and score > 1.0:  # 임계값 설정
            response = best_match["answer"]
            status = "success"
            response_type = "keyword"
            model_name = "Keyword-based Fast Response System"
        else:
            # 2단계: 키워드 매칭 실패 시 Ollama 사용
            if request.use_ollama:
                ollama_response = await call_ollama(
                    request.prompt, 
                    request.max_new_tokens, 
                    request.temperature
                )
                
                # Ollama 응답이 실패 메시지인지 확인
                if "연결할 수 없습니다" in ollama_response or "죄송합니다" in ollama_response:
                    # 키워드 기반 응답으로 fallback
                    response = "죄송합니다. 해당 질문에 대한 답변을 찾을 수 없습니다. 다음 키워드로 질문해보세요:\n\n"
                    response += "• 줌/배경화면 설정\n• 훈련장려금/계좌정보\n• 출결/외출/공결\n• 화장실/자리비움\n• 기초클래스/출결등록\n• 내일배움카드/등록\n• 사랑니/치과진료\n• 입원/진단서\n\n또는 담당자에게 직접 문의해주세요."
                    status = "no_match"
                    response_type = "keyword"
                    model_name = "Keyword-based Fast Response System"
                    matched_keywords = []
                else:
                    response = ollama_response
                    status = "success"
                    response_type = "ollama"
                    model_name = OLLAMA_MODEL
                    matched_keywords = []
            else:
                response = "죄송합니다. 해당 질문에 대한 답변을 찾을 수 없습니다. 다른 키워드로 질문해주시거나, 담당자에게 직접 문의해주세요."
                status = "no_match"
                response_type = "keyword"
                model_name = "Keyword-based Fast Response System"
                matched_keywords = []
        
        # 응답 데이터 유효성 검사
        if not response:
            response = "죄송합니다. 응답을 생성할 수 없습니다."
            status = "error"
        
        # AI 응답 저장
        assistant_message_id = save_message(session_id, "assistant", response, response_type, model_name)
        
        # 응답 객체 생성
        chat_response = ChatResponse(
            response=response,
            model=model_name,
            status=status,
            session_id=session_id,
            message_id=assistant_message_id,
            matched_keywords=matched_keywords if matched_keywords else [],
            response_type=response_type
        )
        
        # 로그 추가
        logger.info(f"챗봇 응답 성공: session_id={session_id}, response_type={response_type}")
        
        return chat_response
        
    except HTTPException:
        # HTTPException은 그대로 전달
        raise
    except Exception as e:
        logger.error(f"채팅 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"내부 서버 오류가 발생했습니다: {str(e)}")

@app.get("/health")
def health_check():
    """서버 상태를 확인합니다."""
    # Ollama 연결 상태 확인
    ollama_status = "unknown"
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            ollama_status = "connected"
        else:
            ollama_status = "error"
    except:
        ollama_status = "disconnected"
    
    return {
        "status": "healthy",
        "model": f"Keyword-based + {OLLAMA_MODEL}",
        "device": "CPU",
        "language": "Korean",
        "qa_count": len(QA_DATABASE),
        "ollama_url": OLLAMA_BASE_URL,
        "ollama_status": ollama_status,
        "available_urls": [
            OLLAMA_BASE_URL,
            "http://korean-chatbot-ollama:11434",
            "http://ollama:11434",
            "http://localhost:11434"
        ]
    }

@app.get("/info")
def get_info():
    """모델 정보를 반환합니다."""
    return {
        "model_name": f"Hybrid System: Keyword-based + {OLLAMA_MODEL}",
        "model_type": "Hybrid AI System",
        "description": "키워드 기반 빠른 응답 + Ollama GPT-OSS-20B 하이브리드 시스템",
        "capabilities": [
            "한국어 대화",
            "빠른 질문 답변 (키워드 기반)",
            "AI 생성 응답 (Ollama)",
            "키워드 매칭",
            "훈련 관련 정보 제공"
        ],
        "qa_topics": list(QA_DATABASE.keys()),
        "ollama_model": OLLAMA_MODEL
    }

@app.get("/qa-list")
def get_qa_list():
    """등록된 QA 목록을 반환합니다."""
    return {
        "qa_list": [
            {
                "id": qa_id,
                "question": qa_data["question"],
                "keywords": qa_data["keywords"]
            }
            for qa_id, qa_data in QA_DATABASE.items()
        ]
    }

# === 대화 기록 관리 API ===

@app.post("/sessions", response_model=Session)
def create_new_session(session_data: SessionCreate):
    """새로운 채팅 세션 생성"""
    session_id = create_session(session_data.title)
    sessions = get_sessions()
    for session in sessions:
        if session.id == session_id:
            return session
    raise HTTPException(status_code=500, detail="세션 생성에 실패했습니다.")

@app.get("/sessions", response_model=List[Session])
def list_sessions():
    """모든 채팅 세션 목록 조회"""
    return get_sessions()

@app.get("/sessions/{session_id}/messages", response_model=List[Message])
def get_messages(session_id: str):
    """특정 세션의 메시지 목록 조회"""
    messages = get_session_messages(session_id)
    if not messages:
        # 빈 세션이거나 존재하지 않는 세션인지 확인
        sessions = get_sessions()
        session_exists = any(s.id == session_id for s in sessions)
        if not session_exists:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
    return messages

@app.delete("/sessions/{session_id}")
def remove_session(session_id: str):
    """세션 삭제"""
    try:
        delete_session(session_id)
        return {"message": "세션이 삭제되었습니다.", "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"세션 삭제 중 오류가 발생했습니다: {str(e)}")

@app.put("/sessions/{session_id}/title")
def rename_session(session_id: str, title_data: dict):
    """세션 제목 변경"""
    title = title_data.get("title")
    if not title:
        raise HTTPException(status_code=400, detail="제목을 입력해주세요.")
    
    try:
        update_session_title(session_id, title)
        return {"message": "세션 제목이 변경되었습니다.", "session_id": session_id, "title": title}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제목 변경 중 오류가 발생했습니다: {str(e)}")

@app.get("/sessions/{session_id}", response_model=Session)
def get_session_info(session_id: str):
    """특정 세션 정보 조회"""
    sessions = get_sessions()
    for session in sessions:
        if session.id == session_id:
            return session
    raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))  # 다른 포트 사용
    uvicorn.run(app, host="0.0.0.0", port=port)