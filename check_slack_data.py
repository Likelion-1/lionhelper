#!/usr/bin/env python3
"""
슬랙 데이터 크롤링 확인 스크립트
DBeaver 없이도 슬랙 데이터가 제대로 수집되고 있는지 확인할 수 있습니다.
"""

import requests
import json
from datetime import datetime, timedelta

# API 기본 URL
BASE_URL = "http://localhost:8000"

def check_slack_stats():
    """슬랙 이슈 통계 확인"""
    print("📊 슬랙 이슈 통계 확인 중...")
    try:
        response = requests.get(f"{BASE_URL}/slack/issues/stats")
        if response.status_code == 200:
            stats = response.json()
            print("✅ 통계 조회 성공!")
            print(f"   총 이슈 수: {stats.get('total_issues', 0)}")
            print(f"   프로젝트별 통계: {stats.get('project_stats', [])}")
            print(f"   이슈 유형별 통계: {stats.get('issue_type_stats', [])}")
            return stats
        else:
            print(f"❌ 통계 조회 실패: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ 통계 조회 오류: {e}")
        return None

def check_recent_issues(limit=5):
    """최근 이슈들 확인"""
    print(f"\n📋 최근 {limit}개 이슈 확인 중...")
    try:
        response = requests.get(f"{BASE_URL}/slack/issues?limit={limit}")
        if response.status_code == 200:
            issues = response.json()
            print(f"✅ 최근 이슈 {len(issues)}개 조회 성공!")
            for i, issue in enumerate(issues, 1):
                print(f"   {i}. [{issue.get('issue_type', 'N/A')}] {issue.get('project', 'N/A')}")
                print(f"      작성자: {issue.get('author', 'N/A')}")
                print(f"      내용: {issue.get('content', 'N/A')[:50]}...")
                print(f"      생성일: {issue.get('created_at', 'N/A')}")
                print()
            return issues
        else:
            print(f"❌ 이슈 조회 실패: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ 이슈 조회 오류: {e}")
        return None

def check_mention_messages():
    """멘션 태그가 포함된 메시지 확인"""
    print("\n🔔 멘션 태그가 포함된 메시지 확인 중...")
    try:
        response = requests.get(f"{BASE_URL}/slack/issues?limit=50")
        if response.status_code == 200:
            issues = response.json()
            mention_count = 0
            mention_types = {"@here": 0, "@everyone": 0, "@channel": 0}
            
            for issue in issues:
                raw_message = issue.get('raw_message', '')
                if any(mention in raw_message for mention in ["<@here>", "<@everyone>", "<@channel>", "<!here>", "<!everyone>", "<!channel>"]):
                    mention_count += 1
                    if "<@here>" in raw_message or "<!here>" in raw_message:
                        mention_types["@here"] += 1
                    if "<@everyone>" in raw_message or "<!everyone>" in raw_message:
                        mention_types["@everyone"] += 1
                    if "<@channel>" in raw_message or "<!channel>" in raw_message:
                        mention_types["@channel"] += 1
            
            print(f"✅ 멘션 태그 분석 완료!")
            print(f"   총 멘션 메시지: {mention_count}개")
            print(f"   멘션 유형별: {mention_types}")
            return mention_count
        else:
            print(f"❌ 멘션 메시지 확인 실패: {response.status_code}")
            return 0
    except Exception as e:
        print(f"❌ 멘션 메시지 확인 오류: {e}")
        return 0

def sync_slack_data(hours=24, force=False):
    """슬랙 데이터 동기화"""
    print(f"\n🔄 슬랙 데이터 동기화 중... (최근 {hours}시간)")
    try:
        payload = {"hours": hours, "force": force}
        response = requests.post(f"{BASE_URL}/slack/sync", json=payload)
        if response.status_code == 200:
            result = response.json()
            print("✅ 동기화 성공!")
            print(f"   새로 추가된 이슈: {result.get('new_issues', 0)}개")
            print(f"   건너뛴 이슈: {result.get('skipped_issues', 0)}개")
            print(f"   처리된 메시지: {result.get('total_messages', 0)}개")
            return result
        else:
            print(f"❌ 동기화 실패: {response.status_code}")
            print(f"   응답: {response.text}")
            return None
    except Exception as e:
        print(f"❌ 동기화 오류: {e}")
        return None

def main():
    """메인 실행 함수"""
    print("🚀 슬랙 데이터 크롤링 확인 시작")
    print("=" * 50)
    
    # 1. 현재 통계 확인
    stats = check_slack_stats()
    
    # 2. 최근 이슈들 확인
    recent_issues = check_recent_issues(5)
    
    # 3. 멘션 태그 메시지 확인
    mention_count = check_mention_messages()
    
    # 4. 동기화 실행 (선택사항)
    print("\n" + "=" * 50)
    sync_choice = input("🔄 슬랙 데이터 동기화를 실행하시겠습니까? (y/n): ").lower()
    if sync_choice == 'y':
        hours = input("동기화할 시간 범위를 입력하세요 (기본값: 24): ").strip()
        hours = int(hours) if hours.isdigit() else 24
        sync_result = sync_slack_data(hours)
        
        if sync_result:
            print("\n🔄 동기화 후 재확인...")
            check_slack_stats()
            check_recent_issues(3)
    
    print("\n✅ 확인 완료!")
    print("=" * 50)

if __name__ == "__main__":
    main()
