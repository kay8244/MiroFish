"""
API 라우트 모듈
"""

from flask import Blueprint

graph_bp = Blueprint('graph', __name__)
simulation_bp = Blueprint('simulation', __name__)
report_bp = Blueprint('report', __name__)

from . import graph  # noqa: E402, F401
from . import simulation  # noqa: E402, F401
from . import report  # noqa: E402, F401

# Pipeline orchestrator blueprint (신규, SK실트론 Si 웨이퍼 MVP)
# 기존 blueprint와 독립. api/simulation.py에는 영향 없음.
from .pipeline import pipeline_bp  # noqa: E402, F401
