"""
Assumptions YAML 로더.

simulation_adapter는 `ctx.config['assumptions_text']` 값을
`simulation_requirement`에 임베드한다. 이 헬퍼는 version 문자열
(예: `ai_server_si_wafer_v1`)을 받아 해당 YAML의 `narrative` 블록을 반환한다.

호출 예:
    from app.utils.assumptions_loader import load_assumptions_text
    text = load_assumptions_text('ai_server_si_wafer_v1')
    extra_config = {'assumptions_text': text, ...}

실제 adapter 통합은 Day 3 옵션. 현재는 명시적 로딩 + UI/CLI에서 사용.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import yaml


def _default_config_dir() -> Path:
    """backend/app/config/assumptions/"""
    return Path(__file__).resolve().parents[1] / 'config' / 'assumptions'


def load_assumptions_yaml(
    version: str,
    config_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Full YAML 딕셔너리 로드 (narrative, agent_hints, runtime_defaults 포함).

    Args:
        version: 파일 stem (예: 'ai_server_si_wafer_v1')
        config_dir: 디렉토리 override (테스트용)

    Returns:
        파싱된 YAML dict.

    Raises:
        FileNotFoundError: version에 대응하는 YAML 파일 부재.
        ValueError: YAML 파싱은 되지만 필수 키(version/narrative) 누락.
    """
    base = config_dir or _default_config_dir()
    path = base / f'{version}.yaml'
    if not path.exists():
        raise FileNotFoundError(
            f'assumptions YAML 없음: {path}. '
            f'backend/app/config/assumptions/ 아래에 {version}.yaml을 추가하세요.'
        )
    with open(path, encoding='utf-8') as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f'{path}: top-level은 dict이어야 합니다 (실제: {type(data).__name__})')
    if 'version' not in data:
        raise ValueError(f'{path}: `version` 키 필수')
    if 'narrative' not in data:
        raise ValueError(f'{path}: `narrative` 키 필수 (adapter가 읽어 임베드)')
    # 파일명 version과 내부 version 일치 확인 (휴먼 에러 방지)
    if data['version'] != version:
        raise ValueError(
            f'{path}: 파일명 버전({version})과 내부 version({data["version"]}) 불일치'
        )
    return data


def load_assumptions_text(
    version: str,
    config_dir: Optional[Path] = None,
) -> str:
    """simulation_requirement에 임베드할 narrative 텍스트만 반환.

    Args:
        version: 파일 stem (예: 'ai_server_si_wafer_v1')
        config_dir: 디렉토리 override (테스트용)

    Returns:
        narrative 문자열. 앞뒤 공백 trim.
    """
    data = load_assumptions_yaml(version, config_dir=config_dir)
    narrative = data.get('narrative', '')
    if not isinstance(narrative, str):
        raise ValueError(f'narrative는 문자열이어야 합니다: {type(narrative).__name__}')
    return narrative.strip()


def list_available_versions(config_dir: Optional[Path] = None) -> list[str]:
    """디렉토리의 모든 YAML 파일 stem 목록."""
    base = config_dir or _default_config_dir()
    if not base.exists():
        return []
    return sorted(p.stem for p in base.glob('*.yaml'))
