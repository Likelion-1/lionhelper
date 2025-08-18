
import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn
import logging
from difflib import SequenceMatcher

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    version="2.0.0",
    description="한국어에 특화된 AI 챗봇 서비스 (키워드 기반 빠른 응답)"
)

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙 설정
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    pass

print("키워드 기반 빠른 응답 시스템이 로드되었습니다.")

# Pydantic 모델
class ChatRequest(BaseModel):
    prompt: str
    max_new_tokens: Optional[int] = 512
    temperature: Optional[float] = 0.6
    top_p: Optional[float] = 0.9

class ChatResponse(BaseModel):
    response: str
    model: str
    status: str
    matched_keywords: Optional[list] = None

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

@app.get("/")
async def root():
    try:
        return FileResponse("static/index.html")
    except:
        return {
            "message": "한국어 AI 챗봇 API (키워드 기반)", 
            "status": "running",
            "model": "Keyword-based Fast Response System",
            "language": "Korean"
        }

@app.post("/chat", response_model=ChatResponse)
async def chat_with_keywords(request: ChatRequest):
    """키워드 기반 빠른 응답 시스템을 사용하여 대화를 수행합니다."""
    
    try:
        # 입력 검증
        if not request.prompt.strip():
            raise HTTPException(status_code=400, detail="메시지를 입력해주세요.")
        
        # 가장 잘 매칭되는 QA 찾기
        best_match, score, matched_keywords = find_best_match(request.prompt)
        
        if best_match and score > 1.0:  # 임계값 설정
            response = best_match["answer"]
            status = "success"
        else:
            response = "죄송합니다. 해당 질문에 대한 답변을 찾을 수 없습니다. 다른 키워드로 질문해주시거나, 담당자에게 직접 문의해주세요."
            status = "no_match"
            matched_keywords = []
        
        return ChatResponse(
            response=response,
            model="Keyword-based Fast Response System",
            status=status,
            matched_keywords=matched_keywords
        )
        
    except Exception as e:
        logger.error(f"채팅 오류: {str(e)}")
        raise HTTPException(status_code=500, detail=f"오류가 발생했습니다: {str(e)}")

@app.get("/health")
def health_check():
    """서버 상태를 확인합니다."""
    return {
        "status": "healthy",
        "model": "Keyword-based Fast Response System",
        "device": "CPU",
        "language": "Korean",
        "qa_count": len(QA_DATABASE)
    }

@app.get("/info")
def get_info():
    """모델 정보를 반환합니다."""
    return {
        "model_name": "Keyword-based Fast Response System",
        "model_type": "Korean QA Database",
        "description": "키워드 기반 빠른 응답 시스템",
        "capabilities": [
            "한국어 대화",
            "빠른 질문 답변",
            "키워드 매칭",
            "훈련 관련 정보 제공"
        ],
        "qa_topics": list(QA_DATABASE.keys())
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

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8001))  # 다른 포트 사용
    uvicorn.run(app, host="0.0.0.0", port=port)