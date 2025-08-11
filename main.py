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

app = FastAPI(title="Llama-3 Korean Chat API", version="1.0.0")

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

# 모델 로딩 (전역 변수로 한 번만 로드)
MODEL_ID = 'MLP-KTLim/llama-3-Korean-Bllossom-8B'
tokenizer = None
model = None

def load_model():
    """모델을 로드하는 함수"""
    global tokenizer, model
    if tokenizer is None or model is None:
        print("모델 로딩 중...")
        tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.bfloat16,
            device_map="auto",
            low_cpu_mem_usage=True,  # 메모리 사용량 최적화
        )
        model.eval()
        print("모델 로딩 완료!")

class ChatRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 256
    temperature: Optional[float] = 0.6
    top_p: Optional[float] = 0.9

class ChatResponse(BaseModel):
    response: str
    model: str

@app.on_event("startup")
async def startup_event():
    """서버 시작 시 모델 로드"""
    load_model()

@app.get("/")
async def root():
    """웹 인터페이스 제공"""
    try:
        return FileResponse("static/index.html")
    except:
        return {
            "message": "Llama-3 Korean Chat API",
            "version": "1.0.0",
            "status": "running",
            "model": MODEL_ID,
            "docs": "/docs"
        }

@app.post("/chat", response_model=ChatResponse)
async def chat_with_llama(request: ChatRequest):
    """Llama-3 모델과 대화를 수행합니다."""
    try:
        if model is None or tokenizer is None:
            raise HTTPException(status_code=503, detail="모델이 로드되지 않았습니다.")
        
        PROMPT = '''You are a helpful AI assistant. Please answer the user's questions kindly. 당신은 유능한 AI 어시스턴트 입니다. 사용자의 질문에 대해 친절하게 답변해주세요.'''
        
        messages = [
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": request.prompt}
        ]

        input_ids = tokenizer.apply_chat_template(
            messages,
            add_generation_prompt=True,
            return_tensors="pt"
        ).to(model.device)

        terminators = [
            tokenizer.eos_token_id,
            tokenizer.convert_tokens_to_ids("<|eot_id|>")
        ]

        with torch.no_grad():  # 메모리 사용량 최적화
            outputs = model.generate(
                input_ids,
                max_new_tokens=request.max_tokens,
                eos_token_id=terminators,
                do_sample=True,
                temperature=request.temperature,
                top_p=request.top_p,
                repetition_penalty=1.1,
                pad_token_id=tokenizer.eos_token_id
            )

        generated_text = tokenizer.decode(
            outputs[0][input_ids.shape[-1]:], 
            skip_special_tokens=True
        )
        
        return ChatResponse(
            response=generated_text.strip(),
            model=MODEL_ID
        )

    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"생성 중 오류가 발생했습니다: {str(e)}"
        )

@app.get("/health")
async def health_check():
    """서버 상태 확인"""
    return {
        "status": "healthy",
        "model_loaded": model is not None,
        "model": MODEL_ID
    }

@app.get("/models")
async def list_models():
    """사용 중인 모델 정보"""
    return {
        "current_model": MODEL_ID,
        "available_models": [MODEL_ID]
    }

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)