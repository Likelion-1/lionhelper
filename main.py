
import os
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

# 모델 ID
# 더 가벼운 한국어 모델들 (선택 가능)
MODEL_ID = 'beomi/KoAlpaca-Polyglot-5.8B'  # 5.8B 파라미터
# MODEL_ID = 'beomi/KoAlpaca-Polyglot-12.8B'  # 12.8B 파라미터 (더 큰 모델)
# MODEL_ID = 'microsoft/DialoGPT-medium'  # 영어 모델 (가장 가벼움)

# FastAPI 앱 초기화
app = FastAPI(title="Llama-3 Korean Chat API (Local)", version="1.0.0")

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

# 모델과 토크나이저 로드
print("토크나이저를 로딩 중...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)

print("모델을 로딩 중...")
model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    torch_dtype=torch.float16,  # M4 Pro에 최적화
    device_map="auto",
    trust_remote_code=True,
    low_cpu_mem_usage=True,  # 메모리 사용량 최적화
    load_in_8bit=False,  # 8비트 양자화 비활성화 (안정성)
    max_memory={0: "12GB"}  # 메모리 제한 설정
)

model.eval()

# Pydantic 모델
class ChatRequest(BaseModel):
    prompt: str
    max_new_tokens: Optional[int] = 2048
    temperature: Optional[float] = 0.6
    top_p: Optional[float] = 0.9

class ChatResponse(BaseModel):
    response: str
    model: str
    status: str

# 시스템 프롬프트
PROMPT = '''You are a helpful AI assistant. Please answer the user's questions kindly. 당신은 유능한 AI 어시스턴트 입니다. 사용자의 질문에 대해 친절하게 답변해주세요.'''

@app.get("/")
async def root():
    try:
        return FileResponse("static/index.html")
    except:
        return {"message": f"API for {MODEL_ID}", "status": "running"}

@app.post("/chat", response_model=ChatResponse)
async def chat_with_llama(request: ChatRequest):
    """로컬 모델을 사용하여 대화를 수행합니다."""
    
    try:
        # 메시지 구성
        messages = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": request.prompt}
        ]
        
        # 입력 토큰화
        input_ids = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt"
        ).to(model.device)
        
        # 종료 토큰 설정
        terminators = [
            tokenizer.eos_token_id,
            tokenizer.convert_tokens_to_ids("<|eot_id|>")
        ]
        
        # 텍스트 생성
        outputs = model.generate(
            input_ids,
            max_new_tokens=request.max_new_tokens,
            eos_token_id=terminators,
            do_sample=True,
            temperature=request.temperature,
            top_p=request.top_p
        )
        
        # 결과 디코딩
        generated_text = tokenizer.decode(
            outputs[0][input_ids.shape[-1]:], 
            skip_special_tokens=True
        )
        
        return ChatResponse(
            response=generated_text.strip(),
            model=MODEL_ID,
            status="success"
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"오류가 발생했습니다: {str(e)}")

@app.get("/health")
def health_check():
    """서버 상태를 확인합니다."""
    return {
        "status": "healthy",
        "model": MODEL_ID,
        "device": str(model.device)
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)