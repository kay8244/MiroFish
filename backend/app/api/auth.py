"""
인증 API 블루프린트.

엔드포인트:
  POST /api/auth/login   {email, password} → 세션 쿠키 설정 + 사용자 정보
  POST /api/auth/logout  → 세션 파기
  GET  /api/auth/me      → 현재 로그인된 사용자 (미인증 시 401)

세션 쿠키는 Flask-Login 이 자동 관리. CORS 는 supports_credentials=True.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user

from ..models import User
from ..utils.logger import get_logger

auth_bp = Blueprint('auth', __name__)
logger = get_logger('mirofish.auth')


@auth_bp.route('/login', methods=['POST'])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    if not email or not password:
        return jsonify({'success': False, 'error': 'email and password required'}), 400

    user = User.get_by_email(email)
    if user is None or not user.check_password(password):
        # 동일 응답: email 존재 여부 누설 방지
        logger.info(f'login failed for {email}')
        return jsonify({'success': False, 'error': 'invalid credentials'}), 401

    login_user(user, remember=True)
    logger.info(f'login success id={user.id} email={user.email} role={user.role}')
    return jsonify({'success': True, 'user': user.to_dict()})


@auth_bp.route('/logout', methods=['POST'])
@login_required
def logout():
    uid = getattr(current_user, 'id', None)
    logout_user()
    logger.info(f'logout id={uid}')
    return jsonify({'success': True})


@auth_bp.route('/me', methods=['GET'])
@login_required
def me():
    return jsonify({'success': True, 'user': current_user.to_dict()})
