import os
import httpx  # 동기/비동기 HTTP 요청을 위한 라이브러리
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
import uvicorn

# --- 환경 변수에서 API 토큰 불러오기 ---
# 이 부분은 Render의 Environment Variables에 설정해야 합니다.
HF_API_TOKEN = os.getenv("HF_API_TOKEN") 
MODEL_ID = 'MLP-KTLim/llama-3-Korean-Bllossom-8B'
API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"

app = FastAPI(title="Llama-3 Korean Chat API (via HF Inference)", version="1.1.0")

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 정적 파일 서빙 설정 (기존과 동일)
try:
    app.mount("/static", StaticFiles(directory="static"), name="static")
except:
    pass

# --- 모델 직접 로딩 관련 코드 모두 삭제 ---
# load_model(), startup_event() 등은 더 이상 필요 없습니다.

class ChatRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 256
    temperature: Optional[float] = 0.6
    top_p: Optional[float] = 0.9

class ChatResponse(BaseModel):
    response: str
    model: str

@app.get("/")
async def root():
    try:
        return FileResponse("static/index.html")
    except:
        return {"message": f"API for {MODEL_ID}", "status": "running"}

@app.post("/chat", response_model=ChatResponse)
async def chat_with_llama_api(request: ChatRequest):
    """Hugging Face Inference API를 호출하여 대화를 수행합니다."""
    
    if not HF_API_TOKEN:
        raise HTTPException(status_code=500, detail="Hugging Face API 토큰이 설정되지 않았습니다.")

    headers = {"Authorization": f"Bearer {HF_API_TOKEN}"}
    
    # Hugging Face Chat Completion API 형식에 맞게 payload 구성
    payload = {
        "inputs": request.prompt,
        "parameters": {
            "max_new_tokens": request.max_tokens,
            "temperature": request.temperature,
            "top_p": request.top_p,
            "return_full_text": False, # 프롬프트를 제외하고 답변만 받기
        }
    }
    
    try:
        # httpx를 사용하여 비동기 API 요청
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(API_URL, headers=headers, json=payload)

        # 오류 처리
        if response.status_code != 200:
            # 모델이 로딩 중일 때 503 에러가 발생할 수 있습니다.
            if response.status_code == 503:
                error_detail = response.json().get('error', '모델이 로딩 중입니다. 잠시 후 다시 시도해주세요.')
                raise HTTPException(status_code=503, detail=error_detail)
            
            raise HTTPException(status_code=response.status_code, detail=response.text)

        result = response.json()
        generated_text = result[0]['generated_text'] if result and 'generated_text' in result[0] else ""
        
        return ChatResponse(
            response=generated_text.strip(),
            model=MODEL_ID
        )

    except httpx.ReadTimeout:
        raise HTTPException(status_code=504, detail="Hugging Face API에서 응답이 지연되었습니다.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"오류가 발생했습니다: {str(e)}")

if __name__ == "__main__":
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)