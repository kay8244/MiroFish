"""
인증 API 블루프린트.

엔드포인트:
  POST   /api/auth/login                  {email, password} → 세션 쿠키 + 사용자 정보
  POST   /api/auth/logout                 → 세션 파기
  GET    /api/auth/me                     → 현재 로그인된 사용자 (미인증 시 401)
  POST   /api/auth/password               → 본인 비밀번호 변경 {old_password, new_password}
  GET    /api/auth/users                  (admin) → 전체 사용자 목록
  POST   /api/auth/users                  (admin) → 사용자 생성 {email, password, role}
  DELETE /api/auth/users/<id>             (admin) → 사용자 삭제
  PATCH  /api/auth/users/<id>/role        (admin) → 역할 변경 {role}
  POST   /api/auth/users/<id>/password    (admin) → 타인 비밀번호 재설정 {password}

세션 쿠키는 Flask-Login 이 자동 관리. CORS 는 supports_credentials=True.
admin-only 라우트는 utils.auth.role_required('admin') 데코레이터로 보호.
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required, login_user, logout_user

from ..models import User
from ..models.user import VALID_ROLES
from ..utils.auth import role_required
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


# ============== 비밀번호 변경 (본인) ==============

@auth_bp.route('/password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json(silent=True) or {}
    old_password = data.get('old_password') or ''
    new_password = data.get('new_password') or ''

    if not old_password or not new_password:
        return jsonify({'success': False, 'error': 'old_password and new_password required'}), 400

    if not current_user.check_password(old_password):
        return jsonify({'success': False, 'error': 'invalid old password'}), 401

    try:
        User.set_password(current_user.id, new_password)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    logger.info(f'password changed id={current_user.id}')
    return jsonify({'success': True})


# ============== 사용자 관리 (admin only) ==============

@auth_bp.route('/users', methods=['GET'])
@role_required('admin')
def list_users():
    return jsonify({'success': True, 'users': User.list_all()})


@auth_bp.route('/users', methods=['POST'])
@role_required('admin')
def create_user():
    data = request.get_json(silent=True) or {}
    email = (data.get('email') or '').strip()
    password = data.get('password') or ''
    role = data.get('role') or ''

    if not email or not password or not role:
        return jsonify({'success': False, 'error': 'email, password, role required'}), 400
    if role not in VALID_ROLES:
        return jsonify({
            'success': False,
            'error': f'role must be one of {list(VALID_ROLES)}',
        }), 400
    if User.get_by_email(email) is not None:
        return jsonify({'success': False, 'error': 'email already exists'}), 409

    try:
        user = User.create(email=email, password=password, role=role)
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400

    logger.info(f'user created by admin={current_user.id} new_id={user.id} role={role}')
    return jsonify({'success': True, 'user': user.to_dict()}), 201


@auth_bp.route('/users/<int:user_id>', methods=['DELETE'])
@role_required('admin')
def delete_user(user_id: int):
    if user_id == current_user.id:
        return jsonify({'success': False, 'error': 'cannot delete yourself'}), 400
    if not User.delete(user_id):
        return jsonify({'success': False, 'error': 'user not found'}), 404
    logger.info(f'user deleted by admin={current_user.id} target_id={user_id}')
    return jsonify({'success': True})


@auth_bp.route('/users/<int:user_id>/role', methods=['PATCH'])
@role_required('admin')
def update_user_role(user_id: int):
    data = request.get_json(silent=True) or {}
    role = data.get('role') or ''
    if role not in VALID_ROLES:
        return jsonify({
            'success': False,
            'error': f'role must be one of {list(VALID_ROLES)}',
        }), 400
    # 자기 자신을 admin → 다른 역할로 강등하려는 경우, 마지막 admin 보호
    if user_id == current_user.id and role != 'admin':
        admin_count = sum(1 for u in User.list_all() if u['role'] == 'admin')
        if admin_count <= 1:
            return jsonify({
                'success': False,
                'error': 'cannot demote the last admin',
            }), 400
    try:
        if not User.update_role(user_id, role):
            return jsonify({'success': False, 'error': 'user not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    logger.info(
        f'role updated by admin={current_user.id} target_id={user_id} new_role={role}'
    )
    return jsonify({'success': True})


@auth_bp.route('/users/<int:user_id>/password', methods=['POST'])
@role_required('admin')
def admin_reset_password(user_id: int):
    data = request.get_json(silent=True) or {}
    new_password = data.get('password') or ''
    if not new_password:
        return jsonify({'success': False, 'error': 'password required'}), 400
    try:
        if not User.set_password(user_id, new_password):
            return jsonify({'success': False, 'error': 'user not found'}), 404
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    logger.info(
        f'password reset by admin={current_user.id} target_id={user_id}'
    )
    return jsonify({'success': True})
