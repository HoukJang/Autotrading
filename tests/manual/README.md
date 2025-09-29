# Manual Tests

수동 실행이 필요한 테스트들입니다.

## 📁 Files

### `manual_auth_test.py`
실제 Schwab 계정을 통한 OAuth 인증 테스트

**실행 조건:**
- 실제 Schwab API 키 필요 (`.env` 파일)
- 브라우저 환경 필요
- 인터넷 연결 필요

**실행 방법:**
```bash
cd tests/manual
python manual_auth_test.py
```

**실행 과정:**
1. 기존 토큰 파일 확인
2. 브라우저 자동 열림
3. Schwab 계정 로그인
4. 애플리케이션 권한 승인
5. 토큰 자동 저장
6. API 연결 테스트

**결과:**
- `tokens.json` 파일 생성 (프로젝트 루트)
- 이후 자동 인증 가능

## ⚠️ 주의사항

1. **보안**: 실제 API 키 사용하므로 주의
2. **브라우저**: SSL 경고 무시 (self-signed certificate)
3. **콜백 URL**: Schwab 앱 설정과 일치해야 함
4. **토큰**: `tokens.json`을 Git에 커밋하지 말 것

## 🔧 Troubleshooting

**인증 실패 시:**
1. API 키/시크릿 확인
2. 콜백 URL 확인
3. Schwab 계정 상태 확인
4. 인터넷 연결 확인

**브라우저 문제 시:**
- SSL 경고는 정상 (self-signed certificate)
- 콜백 URL 확인 후 진행
- 수동으로 URL 복사해서 브라우저에 입력 가능