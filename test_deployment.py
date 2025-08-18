#!/usr/bin/env python3
"""
한국어 챗봇 배포 전 테스트 스크립트
"""

import requests
import json
import time

def test_health_endpoint():
    """헬스 체크 엔드포인트 테스트"""
    try:
        response = requests.get("http://localhost:8000/health")
        if response.status_code == 200:
            print("✅ 헬스 체크 성공")
            print(f"   응답: {response.json()}")
            return True
        else:
            print(f"❌ 헬스 체크 실패: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 헬스 체크 오류: {e}")
        return False

def test_info_endpoint():
    """정보 엔드포인트 테스트"""
    try:
        response = requests.get("http://localhost:8000/info")
        if response.status_code == 200:
            print("✅ 정보 엔드포인트 성공")
            print(f"   응답: {response.json()}")
            return True
        else:
            print(f"❌ 정보 엔드포인트 실패: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 정보 엔드포인트 오류: {e}")
        return False

def test_chat_endpoint():
    """채팅 엔드포인트 테스트"""
    try:
        test_message = "안녕하세요! 테스트입니다."
        payload = {
            "prompt": test_message,
            "max_new_tokens": 100,
            "temperature": 0.7,
            "top_p": 0.9
        }
        
        response = requests.post(
            "http://localhost:8000/chat",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload)
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ 채팅 엔드포인트 성공")
            print(f"   질문: {test_message}")
            print(f"   응답: {result['response'][:100]}...")
            return True
        else:
            print(f"❌ 채팅 엔드포인트 실패: {response.status_code}")
            print(f"   오류: {response.text}")
            return False
    except Exception as e:
        print(f"❌ 채팅 엔드포인트 오류: {e}")
        return False

def test_web_interface():
    """웹 인터페이스 테스트"""
    try:
        response = requests.get("http://localhost:8000/")
        if response.status_code == 200:
            print("✅ 웹 인터페이스 접근 성공")
            return True
        else:
            print(f"❌ 웹 인터페이스 접근 실패: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 웹 인터페이스 오류: {e}")
        return False

def main():
    """메인 테스트 함수"""
    print("🚀 한국어 챗봇 배포 전 테스트 시작")
    print("=" * 50)
    
    # 서버가 시작될 때까지 잠시 대기
    print("⏳ 서버 시작 대기 중...")
    time.sleep(5)
    
    tests = [
        ("헬스 체크", test_health_endpoint),
        ("정보 엔드포인트", test_info_endpoint),
        ("채팅 엔드포인트", test_chat_endpoint),
        ("웹 인터페이스", test_web_interface),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        print(f"\n🔍 {test_name} 테스트 중...")
        if test_func():
            passed += 1
        time.sleep(1)
    
    print("\n" + "=" * 50)
    print(f"📊 테스트 결과: {passed}/{total} 통과")
    
    if passed == total:
        print("🎉 모든 테스트가 성공했습니다! 배포 준비 완료!")
        return True
    else:
        print("⚠️  일부 테스트가 실패했습니다. 문제를 해결한 후 다시 시도하세요.")
        return False

if __name__ == "__main__":
    main() 