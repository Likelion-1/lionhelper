#!/usr/bin/env python3
"""
Ollama GPT-OSS-20B 모델 테스트 스크립트
"""

import requests
import json

def test_ollama_connection():
    """Ollama 연결을 테스트합니다."""
    try:
        # Ollama 서버 상태 확인
        response = requests.get("http://localhost:11434/api/tags")
        if response.status_code == 200:
            print("✅ Ollama 서버 연결 성공")
            models = response.json()
            print(f"사용 가능한 모델: {[model['name'] for model in models.get('models', [])]}")
            return True
        else:
            print("❌ Ollama 서버 연결 실패")
            return False
    except Exception as e:
        print(f"❌ Ollama 서버 연결 오류: {e}")
        return False

def test_ollama_generation():
    """Ollama 모델 생성을 테스트합니다."""
    try:
        url = "http://localhost:11434/api/generate"
        
        payload = {
            "model": "gpt-oss:20b",
            "prompt": "안녕하세요! 간단한 인사말을 해주세요.",
            "stream": False,
            "options": {
                "num_predict": 100,
                "temperature": 0.7
            }
        }
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        print("✅ Ollama 모델 생성 성공")
        print(f"응답: {result.get('response', '응답 없음')}")
        return True
        
    except Exception as e:
        print(f"❌ Ollama 모델 생성 오류: {e}")
        return False

def test_fastapi_integration():
    """FastAPI와의 통합을 테스트합니다."""
    try:
        url = "http://localhost:8000/chat"
        
        payload = {
            "prompt": "사랑니 발치 관련해서 질문이 있어요",
            "use_ollama": True
        }
        
        response = requests.post(url, json=payload, timeout=30)
        response.raise_for_status()
        
        result = response.json()
        print("✅ FastAPI 통합 테스트 성공")
        print(f"응답: {result.get('response', '응답 없음')}")
        print(f"모델: {result.get('model', '모델 정보 없음')}")
        print(f"응답 타입: {result.get('response_type', '타입 정보 없음')}")
        return True
        
    except Exception as e:
        print(f"❌ FastAPI 통합 테스트 오류: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Ollama GPT-OSS-20B 통합 테스트 시작")
    print("=" * 50)
    
    # 1. Ollama 연결 테스트
    print("\n1. Ollama 서버 연결 테스트")
    if not test_ollama_connection():
        print("Ollama 서버가 실행되지 않았습니다. 다음 명령어로 실행해주세요:")
        print("ollama serve")
        exit(1)
    
    # 2. Ollama 모델 생성 테스트
    print("\n2. Ollama 모델 생성 테스트")
    if not test_ollama_generation():
        print("모델이 다운로드되지 않았습니다. 다음 명령어로 다운로드해주세요:")
        print("ollama pull openai/gpt-oss-20b")
        exit(1)
    
    # 3. FastAPI 통합 테스트
    print("\n3. FastAPI 통합 테스트")
    test_fastapi_integration()
    
    print("\n" + "=" * 50)
    print("✅ 모든 테스트 완료!")
