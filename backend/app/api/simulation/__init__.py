"""
시뮬레이션 관련 API 라우트 — 도메인별 모듈로 분리

simulation_bp 자체는 app/api/__init__.py 에서 생성되며, 각 도메인 모듈이
import 될 때 @simulation_bp.route 데코레이터가 실행되어 라우트가 등록됨.

도메인 구성:
- entities  : 엔티티 조회 (3 routes)
- crud      : 시뮬레이션 생성·환경 준비·목록·히스토리 (6 routes)
- profiles  : Agent 페르소나 조회·실시간 진행·독립 생성 (3 routes)
- config    : 설정 조회·실시간 진행·다운로드·스크립트 (4 routes)
- lifecycle : 시작·중지·실시간 상태·환경 종료 (6 routes)
- activity  : 액션·타임라인·통계·게시물·댓글 (5 routes)
- interview : Agent 단일/일괄/전체 인터뷰·히스토리 (4 routes)

총 31 라우트.
"""

from . import activity  # noqa: F401
from . import config as _config_routes  # noqa: F401
from . import crud  # noqa: F401
from . import entities  # noqa: F401
from . import interview  # noqa: F401
from . import lifecycle  # noqa: F401
from . import profiles  # noqa: F401
