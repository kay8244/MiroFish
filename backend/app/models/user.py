"""
User 모델 — Flask-Login UserMixin 호환, raw sqlite3 backed.

Role:
  - admin: 모든 권한 + 사용자 관리
  - builder: graph/simulation/report/pipeline write 가능
  - viewer: GET 만 가능

패스워드는 bcrypt 해시만 저장. 평문은 DB/로그에 남지 않는다.
"""

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import bcrypt
from flask_login import UserMixin

VALID_ROLES = ('admin', 'builder', 'viewer')
_db_lock = threading.Lock()


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _db_path() -> Path:
    return _backend_root() / 'pipeline.sqlite3'


@contextmanager
def _db_conn():
    conn = sqlite3.connect(str(_db_path()), isolation_level=None, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('PRAGMA journal_mode = WAL')
    try:
        yield conn
    finally:
        conn.close()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def init_users_db() -> None:
    """users 테이블 생성 (멱등). 앱 부팅 시 1회 호출."""
    with _db_lock, _db_conn() as conn:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        ''')


class User(UserMixin):
    def __init__(self, id: int, email: str, role: str, password_hash: Optional[str] = None):
        self.id = id
        self.email = email
        self.role = role
        self.password_hash = password_hash

    def get_id(self) -> str:
        return str(self.id)

    def check_password(self, password: str) -> bool:
        if not self.password_hash:
            return False
        return bcrypt.checkpw(password.encode('utf-8'), self.password_hash.encode('utf-8'))

    def to_dict(self) -> dict:
        return {'id': self.id, 'email': self.email, 'role': self.role}

    @staticmethod
    def _from_row(row: sqlite3.Row) -> 'User':
        return User(
            id=row['id'],
            email=row['email'],
            role=row['role'],
            password_hash=row['password_hash'],
        )

    @classmethod
    def get_by_id(cls, user_id: int) -> Optional['User']:
        with _db_conn() as conn:
            row = conn.execute(
                'SELECT id, email, password_hash, role FROM users WHERE id = ?',
                (user_id,),
            ).fetchone()
            return cls._from_row(row) if row else None

    @classmethod
    def get_by_email(cls, email: str) -> Optional['User']:
        with _db_conn() as conn:
            row = conn.execute(
                'SELECT id, email, password_hash, role FROM users WHERE email = ?',
                (email.strip().lower(),),
            ).fetchone()
            return cls._from_row(row) if row else None

    @classmethod
    def create(cls, email: str, password: str, role: str) -> 'User':
        if role not in VALID_ROLES:
            raise ValueError(f"role must be one of {VALID_ROLES}, got {role!r}")
        email_norm = email.strip().lower()
        if not email_norm or '@' not in email_norm:
            raise ValueError('email invalid')
        if len(password) < 8:
            raise ValueError('password must be >= 8 characters')
        pw_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        now = _now_iso()
        with _db_lock, _db_conn() as conn:
            cur = conn.execute(
                'INSERT INTO users (email, password_hash, role, created_at, updated_at) '
                'VALUES (?, ?, ?, ?, ?)',
                (email_norm, pw_hash, role, now, now),
            )
            user_id = cur.lastrowid
        return cls(id=user_id, email=email_norm, role=role, password_hash=pw_hash)

    @classmethod
    def count(cls) -> int:
        with _db_conn() as conn:
            row = conn.execute('SELECT COUNT(*) AS n FROM users').fetchone()
            return int(row['n'])
