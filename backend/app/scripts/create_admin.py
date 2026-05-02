"""
관리자/사용자 계정 생성 CLI.

사용법 (backend/ 에서):
    uv run python -m app.scripts.create_admin
    uv run python -m app.scripts.create_admin --email alice@x.com --role builder

옵션 없이 실행하면 이메일/비번/롤을 인터랙티브로 프롬프트.
비번은 getpass 로 입력받아 터미널에 표시되지 않음.
"""

import argparse
import getpass
import sys

from ..models import init_users_db
from ..models.user import User, VALID_ROLES


def _prompt_email(default: str | None = None) -> str:
    while True:
        raw = input(f"이메일{' [' + default + ']' if default else ''}: ").strip()
        if not raw and default:
            raw = default
        if '@' in raw and len(raw) >= 3:
            return raw.lower()
        print("유효한 이메일을 입력하세요.", file=sys.stderr)


def _prompt_password() -> str:
    while True:
        pw1 = getpass.getpass("비밀번호 (8자 이상): ")
        if len(pw1) < 8:
            print("8자 이상이어야 합니다.", file=sys.stderr)
            continue
        pw2 = getpass.getpass("비밀번호 확인: ")
        if pw1 != pw2:
            print("일치하지 않습니다.", file=sys.stderr)
            continue
        return pw1


def _prompt_role(default: str = 'admin') -> str:
    options = '/'.join(VALID_ROLES)
    while True:
        raw = input(f"롤 ({options}) [{default}]: ").strip().lower()
        if not raw:
            raw = default
        if raw in VALID_ROLES:
            return raw
        print(f"{options} 중에서 선택.", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description='MiroFish 사용자 계정 생성')
    parser.add_argument('--email', help='이메일')
    parser.add_argument('--role', choices=VALID_ROLES, help='롤 (admin/builder/viewer)')
    parser.add_argument('--password', help='비번 (미지정 시 인터랙티브 프롬프트 — CI/테스트 전용)')
    args = parser.parse_args()

    init_users_db()

    email = args.email.lower().strip() if args.email else _prompt_email()

    existing = User.get_by_email(email)
    if existing is not None:
        print(f"이미 존재하는 이메일: {email} (id={existing.id}, role={existing.role})", file=sys.stderr)
        return 2

    password = args.password if args.password else _prompt_password()
    role = args.role if args.role else _prompt_role()

    try:
        user = User.create(email=email, password=password, role=role)
    except ValueError as e:
        print(f"생성 실패: {e}", file=sys.stderr)
        return 1

    print(f"✓ 계정 생성 완료: id={user.id} email={user.email} role={user.role}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
