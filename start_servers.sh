#!/bin/bash

echo "🚀 AI 챗봇 서버 자동 시작 스크립트"
echo "=================================="

# 작업 디렉토리로 이동
cd /Users/choigapju/Desktop/helper

# 1. 기존 FastAPI 서버 안전하게 종료
echo "📱 기존 FastAPI 서버 확인 중..."
FASTAPI_PID=$(lsof -ti:8001 2>/dev/null)
if [ ! -z "$FASTAPI_PID" ]; then
    echo "✋ 기존 FastAPI 서버 (PID: $FASTAPI_PID) 종료 중..."
    kill -TERM $FASTAPI_PID 2>/dev/null
    sleep 2
    # 만약 여전히 살아있으면 강제 종료
    if kill -0 $FASTAPI_PID 2>/dev/null; then
        echo "🔫 강제 종료 중..."
        kill -9 $FASTAPI_PID 2>/dev/null
    fi
    echo "✅ 기존 FastAPI 서버 종료 완료"
else
    echo "✅ 실행 중인 FastAPI 서버 없음"
fi

# 2. Ollama 서버 상태 확인 및 시작
echo ""
echo "🤖 Ollama 서버 상태 확인 중..."
OLLAMA_PID=$(pgrep ollama 2>/dev/null)
if [ ! -z "$OLLAMA_PID" ]; then
    echo "✅ Ollama 서버 이미 실행 중 (PID: $OLLAMA_PID)"
else
    echo "🚀 Ollama 서버 시작 중..."
    nohup ollama serve > ollama.log 2>&1 &
    OLLAMA_PID=$!
    echo "✅ Ollama 서버 시작됨 (PID: $OLLAMA_PID)"
    
    # Ollama 서버가 준비될 때까지 대기
    echo "⏳ Ollama 서버 준비 대기 중..."
    for i in {1..30}; do
        if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
            echo "✅ Ollama 서버 준비 완료!"
            break
        fi
        echo "   $i/30 초 대기 중..."
        sleep 1
    done
fi

# 3. 가상환경 활성화 및 FastAPI 서버 시작
echo ""
echo "🐍 Python 가상환경 활성화 중..."
source lionhelper/bin/activate

echo "🌟 FastAPI 서버 시작 중..."
echo "📝 로그는 server.log 파일에서 확인하세요"
echo "🌐 서버 주소: http://localhost:8001"
echo "📚 API 문서: http://localhost:8001/docs"
echo ""
echo "💡 서버를 중지하려면 Ctrl+C를 누르세요"
echo "=================================="

# 서버 실행 (포그라운드)
python main.py

