#!/usr/bin/env python3
"""
JSON 응답 오류를 테스트하고 디버깅하는 스크립트
"""

import requests
import json
import sys

def test_endpoint(url, method="GET", data=None):
    """엔드포인트를 테스트하고 상세한 정보를 출력합니다."""
    print(f"\n=== {method} {url} ===")
    
    try:
        if method == "GET":
            response = requests.get(url, timeout=10)
        elif method == "POST":
            response = requests.post(url, json=data, timeout=10)
        
        print(f"상태 코드: {response.status_code}")
        print(f"Content-Type: {response.headers.get('content-type', 'None')}")
        print(f"응답 크기: {len(response.content)} bytes")
        
        # 원시 응답 내용 출력 (처음 500자)
        raw_content = response.text
        print(f"원시 응답 (처음 500자):")
        print(repr(raw_content[:500]))
        
        # JSON 파싱 시도
        try:
            json_data = response.json()
            print("✅ JSON 파싱 성공")
            print(f"JSON 데이터: {json.dumps(json_data, ensure_ascii=False, indent=2)}")
            return True, json_data
        except json.JSONDecodeError as e:
            print(f"❌ JSON 파싱 실패: {e}")
            return False, raw_content
            
    except requests.exceptions.RequestException as e:
        print(f"❌ 요청 실패: {e}")
        return False, None
    except Exception as e:
        print(f"❌ 예상치 못한 오류: {e}")
        return False, None

def main():
    # 기본 URL
    base_url = "https://lionhelper.onrender.com"
    
    # 테스트할 엔드포인트들
    endpoints = [
        ("GET", "/health"),
        ("GET", "/info"),
        ("GET", "/sessions"),
        ("POST", "/chat", {
            "prompt": "안녕하세요",
            "max_new_tokens": 100,
            "temperature": 0.6
        })
    ]
    
    print("🔍 JSON 응답 테스트 시작")
    print(f"기본 URL: {base_url}")
    
    results = []
    
    for method, endpoint, *data in endpoints:
        url = base_url + endpoint
        test_data = data[0] if data else None
        
        success, response = test_endpoint(url, method, test_data)
        results.append((endpoint, success, response))
    
    # 결과 요약
    print("\n" + "="*50)
    print("📊 테스트 결과 요약")
    print("="*50)
    
    success_count = 0
    for endpoint, success, response in results:
        status = "✅ 성공" if success else "❌ 실패"
        print(f"{endpoint}: {status}")
        if success:
            success_count += 1
    
    print(f"\n전체 성공률: {success_count}/{len(results)} ({success_count/len(results)*100:.1f}%)")
    
    # 실패한 경우 추가 정보
    failed_endpoints = [endpoint for endpoint, success, _ in results if not success]
    if failed_endpoints:
        print(f"\n⚠️  실패한 엔드포인트: {', '.join(failed_endpoints)}")
        print("로컬 서버에서도 테스트해보세요:")
        print("python main.py")

if __name__ == "__main__":
    main()
