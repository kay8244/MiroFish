"""
assumptions_loader 테스트.

- 실제 출하 파일(ai_server_si_wafer_v1.yaml) 스모크
- 임시 디렉토리 기반 에러 경로
"""

import os
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.utils.assumptions_loader import (  # noqa: E402
    load_assumptions_text,
    load_assumptions_yaml,
    list_available_versions,
    _default_config_dir,
)


class TestShippedFile:
    """출하된 ai_server_si_wafer_v1.yaml 정합성."""

    def test_default_dir_exists(self):
        assert _default_config_dir().exists(), \
            'backend/app/config/assumptions/ 디렉토리 없음'

    def test_v1_yaml_loads(self):
        data = load_assumptions_yaml('ai_server_si_wafer_v1')
        assert data['version'] == 'ai_server_si_wafer_v1'
        assert 'narrative' in data
        assert len(data['narrative']) > 500, 'narrative가 너무 짧음'

    def test_v1_text_contains_key_entities(self):
        text = load_assumptions_text('ai_server_si_wafer_v1')
        for keyword in ('NVIDIA', 'TSMC', 'HBM', 'CoWoS', 'Microsoft',
                        'SK Hynix', '이수페타시스', 'Rubin'):
            assert keyword in text, f'narrative에 {keyword} 누락'

    def test_v1_has_agent_hints(self):
        data = load_assumptions_yaml('ai_server_si_wafer_v1')
        hints = data.get('agent_hints', {})
        dist = hints.get('distribution', {})
        # 분포 합이 1.0 근처여야 함
        total = sum(dist.values())
        assert 0.95 < total < 1.05, f'distribution 합이 1이 아님: {total}'

    def test_list_available_includes_v1(self):
        versions = list_available_versions()
        assert 'ai_server_si_wafer_v1' in versions


class TestErrorPaths:
    def test_missing_version_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load_assumptions_text('nonexistent_version', config_dir=tmp_path)

    def test_missing_narrative_raises(self, tmp_path):
        yaml_path = tmp_path / 'broken_v1.yaml'
        yaml_path.write_text(textwrap.dedent("""\
            version: broken_v1
            scenario: test
        """), encoding='utf-8')
        with pytest.raises(ValueError, match='narrative'):
            load_assumptions_yaml('broken_v1', config_dir=tmp_path)

    def test_version_mismatch_raises(self, tmp_path):
        yaml_path = tmp_path / 'file_v1.yaml'
        yaml_path.write_text(textwrap.dedent("""\
            version: internal_v2
            narrative: |
              some text
        """), encoding='utf-8')
        with pytest.raises(ValueError, match='불일치'):
            load_assumptions_yaml('file_v1', config_dir=tmp_path)

    def test_non_dict_yaml_raises(self, tmp_path):
        yaml_path = tmp_path / 'list_v1.yaml'
        yaml_path.write_text('- a\n- b\n', encoding='utf-8')
        with pytest.raises(ValueError, match='dict'):
            load_assumptions_yaml('list_v1', config_dir=tmp_path)

    def test_narrative_trimmed(self, tmp_path):
        yaml_path = tmp_path / 'padded_v1.yaml'
        yaml_path.write_text(textwrap.dedent("""\
            version: padded_v1
            narrative: |


              body line 1

              body line 2


        """), encoding='utf-8')
        text = load_assumptions_text('padded_v1', config_dir=tmp_path)
        assert text.startswith('body line 1')
        assert text.endswith('body line 2')


class TestAdapterContract:
    """simulation_adapter와의 계약 확인: text가 그대로 임베드될 때 문제없어야 함."""

    def test_text_injected_into_requirement_shape(self):
        text = load_assumptions_text('ai_server_si_wafer_v1')
        base = 'AI 서버 → SI 웨이퍼 수요 예측'
        requirement = (
            f'{base}\n\n## Assumptions (vai_server_si_wafer_v1)\n{text}'
        )
        # 구조적 체크만: 조립된 requirement가 적절한 분량인지
        assert '## Assumptions' in requirement
        assert len(requirement) > 2000
        assert 'NVIDIA' in requirement
