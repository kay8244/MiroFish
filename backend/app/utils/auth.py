"""
Flask-Login 초기화 + 경로/메서드 기반 전역 게이트.

설계:
  개별 라우트에 @login_required 를 붙이는 대신 app.before_request 훅으로
  일괄 게이트를 적용. 라우트 누락 위험 없음.

규칙:
  - PUBLIC_PREFIXES (인증 불필요): /api/auth/*, /health
  - 그 외 /api/* → 로그인 필요
  - 쓰기 메서드 (POST/PUT/DELETE/PATCH) 는 admin/builder 만 허용
  - GET/HEAD/OPTIONS 는 모든 인증된 역할 (admin/builder/viewer)
"""

import os

from functools import wraps

from flask import jsonify, request
from flask_login import LoginManager, current_user, login_user

from ..models.user import User

login_manager = LoginManager()

# Dev-only: bypass auth gate by auto-logging in as a fixed admin user.
# 절대 production 에서 켜지 마세요. .env 에 DEV_BYPASS_AUTH=true 로만 활성.
DEV_BYPASS_AUTH = os.environ.get('DEV_BYPASS_AUTH', '').lower() in ('1', 'true', 'yes')
DEV_BYPASS_EMAIL = os.environ.get('DEV_BYPASS_EMAIL', 'admin@mirofish.local')

# 인증 없이 허용 (CORS preflight 는 OPTIONS 메서드로 별도 처리)
PUBLIC_PREFIXES = (
    '/api/auth/login',
    '/health',
)

# 쓰기 메서드 — admin/builder 만
WRITE_METHODS = {'POST', 'PUT', 'DELETE', 'PATCH'}
WRITE_ROLES = {'admin', 'builder'}


@login_manager.user_loader
def load_user(user_id: str):
    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return None
    return User.get_by_id(uid)


@login_manager.unauthorized_handler
def on_unauthorized():
    return jsonify({'success': False, 'error': 'unauthorized'}), 401


def _is_public(path: str) -> bool:
    return any(path == p or path.startswith(p + '/') for p in PUBLIC_PREFIXES)


def enforce_auth():
    """app.before_request 로 등록되는 전역 게이트."""
    # CORS preflight: 항상 통과
    if request.method == 'OPTIONS':
        return None

    path = request.path

    # 공개 경로
    if _is_public(path):
        return None

    # /api/* 만 게이트 대상. 정적 리소스 / 루트 / health 는 위에서 통과.
    if not path.startswith('/api/'):
        return None

    # Dev bypass: 미인증이면 고정 dev 유저로 자동 로그인.
    # 한 번 로그인되면 이후 요청은 세션 쿠키로 통과 (성능 영향 미미).
    if DEV_BYPASS_AUTH and not current_user.is_authenticated:
        dev_user = User.get_by_email(DEV_BYPASS_EMAIL)
        if dev_user is not None:
            login_user(dev_user, remember=True)

    # 인증 체크
    if not current_user.is_authenticated:
        return jsonify({'success': False, 'error': 'unauthorized'}), 401

    # 역할 체크 (auth blueprint 는 공개 경로 외에는 write 가 없으므로 write 규칙 적용 OK)
    if request.method in WRITE_METHODS and current_user.role not in WRITE_ROLES:
        return jsonify({
            'success': False,
            'error': 'forbidden',
            'required_roles': sorted(WRITE_ROLES),
        }), 403

    return None


def role_required(*roles: str):
    """특정 엔드포인트 전용 role 제한 (예: user 관리 admin-only). before_request 외 보조."""
    allowed = set(roles)

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return jsonify({'success': False, 'error': 'unauthorized'}), 401
            if current_user.role not in allowed:
                return jsonify({
                    'success': False,
                    'error': 'forbidden',
                    'required_roles': sorted(allowed),
                }), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator
