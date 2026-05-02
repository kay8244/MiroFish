"""
설정 관리
프로젝트 루트 디렉터리의 .env 파일에서 통합 설정 로드
"""

import os
from dotenv import load_dotenv

# 프로젝트 루트 디렉터리의 .env 파일 로드
# 경로: MiroFish/.env (backend/app/config.py 기준 상대 경로)
project_root_env = os.path.join(os.path.dirname(__file__), '../../.env')

if os.path.exists(project_root_env):
    load_dotenv(project_root_env, override=True)
else:
    # 루트 디렉터리에 .env가 없으면 환경 변수 로드 시도（프로덕션 환경용）
    load_dotenv(override=True)


class Config:
    """Flask 설정 클래스"""

    # Flask 설정
    SECRET_KEY = os.environ.get('SECRET_KEY', os.urandom(24).hex())
    DEBUG = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'

    # JSON 설정 - ASCII 이스케이프 비활성화, 유니코드 문자 직접 표시（\uXXXX 형식 대신）
    JSON_AS_ASCII = False

    # LLM 설정
    LLM_PROVIDER = os.environ.get('LLM_PROVIDER', 'openai')  # 'openai' or 'anthropic'
    LLM_API_KEY = os.environ.get('LLM_API_KEY')
    LLM_BASE_URL = os.environ.get('LLM_BASE_URL', 'https://api.openai.com/v1')
    LLM_MODEL_NAME = os.environ.get('LLM_MODEL_NAME', 'gpt-4o-mini')

    # Graphiti(Neo4j) 설정 — 기본 knowledge graph 백엔드
    NEO4J_URI = os.environ.get('NEO4J_URI', 'bolt://localhost:7687')
    NEO4J_USER = os.environ.get('NEO4J_USER', 'neo4j')
    NEO4J_PASSWORD = os.environ.get('NEO4J_PASSWORD', 'mirofish-dev')

    # Zep Cloud legacy — optional extra(`uv sync --extra zep`) 설치 + 아래 키 설정
    # 시에만 활성. 평상시 Graphiti 단독 경로에서는 두 값 모두 None이어도 무방.
    ZEP_API_KEY = os.environ.get('ZEP_API_KEY')
    ZEP_BASE_URL = os.environ.get('ZEP_BASE_URL')

    # 파일 업로드 설정
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB
    UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), '../uploads')
    ALLOWED_EXTENSIONS = {'pdf', 'md', 'txt', 'markdown'}

    # 텍스트 처리 설정
    DEFAULT_CHUNK_SIZE = 500  # 기본 청크 크기
    DEFAULT_CHUNK_OVERLAP = 50  # 기본 겹침 크기

    # OASIS 시뮬레이션 설정
    OASIS_DEFAULT_MAX_ROUNDS = int(os.environ.get('OASIS_DEFAULT_MAX_ROUNDS', '10'))
    OASIS_SIMULATION_DATA_DIR = os.path.join(os.path.dirname(__file__), '../uploads/simulations')

    # OASIS 플랫폼 사용 가능한 액션 설정
    OASIS_TWITTER_ACTIONS = [
        'CREATE_POST', 'LIKE_POST', 'REPOST', 'FOLLOW', 'DO_NOTHING', 'QUOTE_POST'
    ]
    OASIS_REDDIT_ACTIONS = [
        'LIKE_POST', 'DISLIKE_POST', 'CREATE_POST', 'CREATE_COMMENT',
        'LIKE_COMMENT', 'DISLIKE_COMMENT', 'SEARCH_POSTS', 'SEARCH_USER',
        'TREND', 'REFRESH', 'DO_NOTHING', 'FOLLOW', 'MUTE'
    ]

    # Report Agent 설정
    REPORT_AGENT_MAX_TOOL_CALLS = int(os.environ.get('REPORT_AGENT_MAX_TOOL_CALLS', '5'))
    REPORT_AGENT_MAX_REFLECTION_ROUNDS = int(os.environ.get('REPORT_AGENT_MAX_REFLECTION_ROUNDS', '2'))
    REPORT_AGENT_TEMPERATURE = float(os.environ.get('REPORT_AGENT_TEMPERATURE', '0.5'))

    @classmethod
    def validate(cls):
        """필수 설정 검증. ZEP_API_KEY는 legacy path에서만 사용되므로 필수 아님."""
        errors = []
        if not cls.LLM_API_KEY:
            errors.append("LLM_API_KEY 가 설정되지 않았습니다")
        if not os.environ.get('SECRET_KEY'):
            errors.append("SECRET_KEY 가 설정되지 않았습니다 (랜덤 키가 사용됩니다 - 프로덕션에서는 고정 키를 설정하세요)")
        return errors

