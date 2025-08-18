#!/usr/bin/env python3
"""
MVP 모델 테스트 스크립트
키워드 기반 빠른 응답 시스템을 테스트합니다.
"""

import requests
import json
import time

# 서버 URL
BASE_URL = "http://localhost:8001"

def test_chat(prompt: str):
    """채팅 API를 테스트합니다."""
    url = f"{BASE_URL}/chat"
    data = {
        "prompt": prompt,
        "max_new_tokens": 512,
        "temperature": 0.6,
        "top_p": 0.9
    }
    
    try:
        start_time = time.time()
        response = requests.post(url, json=data)
        end_time = time.time()
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 질문: {prompt}")
            print(f"⏱️  응답 시간: {(end_time - start_time)*1000:.2f}ms")
            print(f"🎯 매칭된 키워드: {result.get('matched_keywords', [])}")
            print(f"📝 답변: {result['response']}")
            print(f"📊 상태: {result['status']}")
        else:
            print(f"❌ 오류: {response.status_code} - {response.text}")
        
        print("-" * 80)
        
    except Exception as e:
        print(f"❌ 연결 오류: {e}")

def test_health():
    """서버 상태를 확인합니다."""
    try:
        response = requests.get(f"{BASE_URL}/health")
        if response.status_code == 200:
            result = response.json()
            print(f"🏥 서버 상태: {result['status']}")
            print(f"🤖 모델: {result['model']}")
            print(f"📚 QA 개수: {result['qa_count']}")
        else:
            print(f"❌ 서버 오류: {response.status_code}")
    except Exception as e:
        print(f"❌ 서버 연결 실패: {e}")

def main():
    """메인 테스트 함수"""
    print("🚀 MVP 모델 테스트 시작")
    print("=" * 80)
    
    # 서버 상태 확인
    test_health()
    print()
    
    # 테스트 케이스들
    test_cases = [
        "줌 배경 화면 설정 어떻게 하나요?",
        "훈련장려금 계좌 정보가 안보여요",
        "출결 관련해서 질문이 있어요",
        "화장실 다녀와도 되나요?",
        "기초클래스 출결 등록이 안돼요",
        "내일배움카드 때문에 등록이 늦었어요",
        "사랑니 발치 공결 인정되나요?",
        "입원해서 진단서 매일 제출해야 하나요?",
        "이건 테스트 질문입니다"  # 매칭되지 않는 케이스
    ]
    
    for test_case in test_cases:
        test_chat(test_case)
        time.sleep(0.5)  # 서버 부하 방지

if __name__ == "__main__":
    main()
