"""
설정 도우미 모듈

설정 파일 관리와 검증을 위한 유틸리티 함수들을 제공합니다.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, List

from .settings import settings


def check_auth_file_exists() -> bool:
    """auth.py 파일 존재 여부 확인"""
    auth_file = Path(__file__).parent / "auth.py"
    return auth_file.exists()


def create_auth_file_from_template() -> bool:
    """auth.example.py에서 auth.py 파일 생성"""
    config_dir = Path(__file__).parent
    template_file = config_dir / "auth.example.py"
    auth_file = config_dir / "auth.py"

    if not template_file.exists():
        print(f"❌ 템플릿 파일을 찾을 수 없습니다: {template_file}")
        return False

    if auth_file.exists():
        print(f"⚠️  auth.py 파일이 이미 존재합니다: {auth_file}")
        return False

    try:
        shutil.copy2(template_file, auth_file)
        print(f"✅ auth.py 파일이 생성되었습니다: {auth_file}")
        print("📝 실제 API 키와 데이터베이스 정보로 수정하세요.")
        return True
    except Exception as e:
        print(f"❌ auth.py 파일 생성 실패: {e}")
        return False


def validate_configuration(verbose: bool = True) -> Dict[str, Any]:
    """설정 검증 및 상태 반환"""
    status = settings.get_auth_config_status()

    validation_result = {
        "valid": True,
        "errors": [],
        "warnings": [],
        "status": status
    }

    # 필수 설정 검증
    try:
        settings.validate_required_config()
    except ValueError as e:
        validation_result["valid"] = False
        validation_result["errors"].append(str(e))

    # 경고 사항 확인
    if settings.schwab_app_key == "YOUR_ACTUAL_APP_KEY":
        validation_result["warnings"].append("Schwab API key is using template value. Please update with actual key.")

    if "your_real_password" in settings.database_url:
        validation_result["warnings"].append("Database password is using template value. Please update with actual password.")

    # Environment specific checks
    if settings.is_production() and settings.debug:
        validation_result["warnings"].append("Debug mode is enabled in production environment.")

    if verbose:
        print_validation_result(validation_result)

    return validation_result


def print_validation_result(result: Dict[str, Any]) -> None:
    """검증 결과 출력"""
    print("=== Configuration Validation Result ===")

    if result["valid"]:
        print("[OK] Configuration is valid.")
    else:
        print("[ERROR] Configuration has errors.")

    if result["errors"]:
        print("\n[ERRORS]:")
        for error in result["errors"]:
            print(f"  - {error}")

    if result["warnings"]:
        print("\n[WARNINGS]:")
        for warning in result["warnings"]:
            print(f"  - {warning}")

    print("\n[STATUS]:")
    status = result["status"]
    for key, value in status.items():
        icon = "[OK]" if value else "[FAIL]"
        print(f"  {icon} {key}: {value}")


def get_setup_instructions() -> List[str]:
    """설정 안내 메시지 생성"""
    instructions = []

    if not check_auth_file_exists():
        instructions.append("1. Create auth.py file:")
        instructions.append("   python -c \"from autotrading.config.config_helper import create_auth_file_from_template; create_auth_file_from_template()\"")

    instructions.append("2. Update the following values in auth.py with your actual information:")
    instructions.append("   - SCHWAB_CONFIG['app_key']: Your Schwab API app key")
    instructions.append("   - SCHWAB_CONFIG['app_secret']: Your Schwab API app secret")
    instructions.append("   - DATABASE_CONFIG['url']: Your PostgreSQL connection info")

    instructions.append("3. Validate configuration:")
    instructions.append("   python -c \"from autotrading.config.config_helper import validate_configuration; validate_configuration()\"")

    return instructions


def print_setup_instructions() -> None:
    """설정 안내 출력"""
    print("=== Autotrading Configuration Setup ===")
    instructions = get_setup_instructions()
    for instruction in instructions:
        print(instruction)


if __name__ == "__main__":
    # 스크립트로 실행 시 설정 검증
    print_setup_instructions()
    print("\n")
    validate_configuration()