"""
Pipeline Step Adapters

기존 서비스를 PipelineOrchestrator에 등록하는 4개 adapter.
**서비스 내부는 수정하지 않는다.** adapter 경계에서만:
  - StepContext → 서비스 호출 인자 매핑
  - 산출물은 ctx.tmp_dir에 기록 (manifest meta dict 반환)
  - 외부 자원(Zep graph, simulation_id, report_id) 식별자는 meta JSON에 기록

5단계: seed_upload(orchestrator), graph, agents, simulation, report.
seed_upload은 start_run에서 처리되므로 adapter 등록 없음 (MC-5).

agents/simulation 책임 경계 결정 (옵션 ii Pass-through, 2026-04-19 채택):
  - agents: prev_step의 graph_meta.json read + manifest 메타 기록 only.
    profile 생성은 simulation 단계의 prepare_simulation 안에서 일괄 처리됨.
  - simulation: create_simulation → prepare_simulation → SimulationRunner.start_simulation
    → run_state polling (poll-until-completed). 30분 wall-clock 예상.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from .pipeline_orchestrator import StepContext, register_step
from .text_processor import TextProcessor
from .ontology_generator import OntologyGenerator
from .graph_builder import GraphBuilderService
from .simulation_manager import SimulationManager
from .simulation_runner import SimulationRunner, RunnerStatus
from .report_agent import ReportAgent
from ..models.task import TaskManager, TaskStatus

logger = logging.getLogger('mirofish.pipeline_adapters')


# ─────────────────────────────────────────────────────────────────────
# graph adapter
# ─────────────────────────────────────────────────────────────────────

# graph_builder.build_graph_async 비동기 폴링 설정
_GRAPH_POLL_INTERVAL_S = 5
_GRAPH_POLL_MAX_S = 9 * 60  # 10분 wall-clock에서 1분 버퍼


def graph_adapter(ctx: StepContext) -> dict:
    """seed → ontology → Zep graph 구축.

    1. seed_dir의 모든 파일을 text로 합침 (TextProcessor)
    2. OntologyGenerator로 entity/edge 정의 생성
    3. GraphBuilderService.build_graph_async로 Zep graph 구축 (비동기)
    4. TaskManager 폴링으로 graph_id 캡처
    5. tmp_dir/graph_meta.json + ontology.json 기록

    NOTE: graph_id는 graph_builder가 자체 생성 (`mirofish_<uuid16>`).
    ctx.zep_group_id는 manifest의 논리 식별자일 뿐, 실제 Zep graph_id와 다르다.
    """
    ctx.tmp_dir.mkdir(parents=True, exist_ok=True)
    seed_files = sorted(p for p in ctx.seed_dir.iterdir() if p.is_file())
    if not seed_files:
        raise RuntimeError(f'graph: seed_dir에 파일 없음: {ctx.seed_dir}')

    logger.info(f'graph: seed 추출 시작 ({len(seed_files)}개 파일)')
    document_text = TextProcessor.extract_from_files([str(p) for p in seed_files])
    document_text = TextProcessor.preprocess_text(document_text)
    text_stats = TextProcessor.get_text_stats(document_text)

    simulation_requirement = ctx.config.get(
        'simulation_requirement',
        'AI 서버 → SI 웨이퍼 수요 예측 (한국어 시뮬레이션)',
    )

    # 1) 온톨로지 생성 (Fix F: tmp_dir 캐시 — step retry 시 재생성 방지)
    ontology_cache = ctx.tmp_dir / 'ontology.json'
    if ontology_cache.exists():
        logger.info(f'graph: ontology 재사용 (이전 retry 결과: {ontology_cache})')
        ontology = json.loads(ontology_cache.read_text(encoding='utf-8'))
    else:
        logger.info('graph: ontology 생성 중...')
        ontology_gen = OntologyGenerator()
        ontology = ontology_gen.generate(
            document_texts=[document_text],
            simulation_requirement=simulation_requirement,
        )
        # tmp_dir에 ontology 보관 (디버깅/audit + 다음 retry 재사용)
        ontology_cache.write_text(
            json.dumps(ontology, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

    # 2) Zep graph 비동기 구축
    chunk_size = ctx.config.get('chunk_size', 500)
    chunk_overlap = ctx.config.get('chunk_overlap', 50)
    batch_size = ctx.config.get('zep_batch_size', 3)
    graph_name = f'MiroFish run {ctx.run_id[:8]}'

    builder = GraphBuilderService()
    task_id = builder.build_graph_async(
        text=document_text,
        ontology=ontology,
        graph_name=graph_name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        batch_size=batch_size,
    )
    logger.info(f'graph: build_graph_async task_id={task_id}, 폴링 시작')

    # 3) TaskManager 폴링
    task_manager = TaskManager()
    deadline = time.time() + _GRAPH_POLL_MAX_S
    last_progress = -1
    while True:
        if time.time() > deadline:
            raise TimeoutError(
                f'graph: build_graph_async 폴링 타임아웃 ({_GRAPH_POLL_MAX_S}s)'
            )
        task = task_manager.get_task(task_id)
        if task is None:
            raise RuntimeError(f'graph: task {task_id} 사라짐')
        if task.progress != last_progress:
            logger.info(f'graph: progress={task.progress}% msg={task.message}')
            last_progress = task.progress
        if task.status == TaskStatus.COMPLETED:
            break
        if task.status == TaskStatus.FAILED:
            raise RuntimeError(f'graph: build_graph 실패: {task.error}')
        time.sleep(_GRAPH_POLL_INTERVAL_S)

    result = task.result or {}
    graph_id = result.get('graph_id')
    if not graph_id:
        raise RuntimeError(f'graph: 완료되었으나 graph_id 누락: {result}')

    meta = {
        'graph_id': graph_id,
        'graph_info': result.get('graph_info', {}),
        'chunks_processed': result.get('chunks_processed', 0),
        'text_stats': text_stats,
        'task_id': task_id,
        'entity_types_defined': len(ontology.get('entity_types', [])),
        'edge_types_defined': len(ontology.get('edge_types', [])),
    }
    (ctx.tmp_dir / 'graph_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    logger.info(f'graph: 완료 graph_id={graph_id}')
    return meta


# ─────────────────────────────────────────────────────────────────────
# agents adapter (Pass-through: meta no-op)
# ─────────────────────────────────────────────────────────────────────

def agents_adapter(ctx: StepContext) -> dict:
    """Pass-through 모델: prev_step(graph)의 graph_meta.json read +
    manifest에 graph_id 전파.

    실제 OASIS profile 생성은 simulation 단계의 prepare_simulation 내부에서
    일괄 처리되므로 여기서는 별도 LLM 호출 없음.
    """
    ctx.tmp_dir.mkdir(parents=True, exist_ok=True)
    if ctx.prev_step_dir is None:
        raise RuntimeError('agents: prev_step_dir 없음 (graph 단계 산출 필요)')

    graph_meta_path = ctx.prev_step_dir / 'graph_meta.json'
    if not graph_meta_path.exists():
        raise RuntimeError(f'agents: graph_meta.json 없음: {graph_meta_path}')

    graph_meta = json.loads(graph_meta_path.read_text(encoding='utf-8'))
    graph_id = graph_meta.get('graph_id')
    if not graph_id:
        raise RuntimeError(f'agents: graph_id 누락: {graph_meta}')

    meta = {
        'graph_id': graph_id,
        'pass_through': True,
        'note': 'profile 생성은 simulation.prepare_simulation에 위임됨',
    }
    (ctx.tmp_dir / 'agents_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    logger.info(f'agents: pass-through 완료 graph_id={graph_id}')
    return meta


# ─────────────────────────────────────────────────────────────────────
# simulation adapter
# ─────────────────────────────────────────────────────────────────────

# SimulationRunner subprocess 폴링 설정
_SIM_POLL_INTERVAL_S = 30
_SIM_POLL_MAX_S = 28 * 60  # 30분 wall-clock에서 2분 버퍼


def simulation_adapter(ctx: StepContext) -> dict:
    """create_simulation → prepare_simulation → start_simulation → poll.

    prepare_simulation 안에서 OASIS profile 생성 + LLM config 생성까지 일괄
    처리된 후 status가 READY가 되면 SimulationRunner subprocess를 시작한다.

    assumptions YAML은 simulation_requirement 문자열에 텍스트로 임베드된다
    (계약 차이 #3 — config_generator에 별도 슬롯 없음).
    """
    ctx.tmp_dir.mkdir(parents=True, exist_ok=True)
    if ctx.prev_step_dir is None:
        raise RuntimeError('simulation: prev_step_dir 없음 (agents 단계 산출 필요)')

    agents_meta = json.loads(
        (ctx.prev_step_dir / 'agents_meta.json').read_text(encoding='utf-8')
    )
    graph_id = agents_meta.get('graph_id')
    if not graph_id:
        raise RuntimeError(f'simulation: graph_id 누락: {agents_meta}')

    # seed에서 document_text 재구성 (prepare_simulation 입력)
    seed_files = sorted(p for p in ctx.seed_dir.iterdir() if p.is_file())
    document_text = TextProcessor.preprocess_text(
        TextProcessor.extract_from_files([str(p) for p in seed_files])
    )

    base_requirement = ctx.config.get(
        'simulation_requirement',
        'AI 서버 → SI 웨이퍼 수요 예측 (한국어 시뮬레이션)',
    )
    assumptions_text = ctx.config.get('assumptions_text', '')
    if assumptions_text:
        simulation_requirement = (
            f'{base_requirement}\n\n## Assumptions (v{ctx.assumptions_version})\n'
            f'{assumptions_text}'
        )
    else:
        simulation_requirement = base_requirement

    enable_twitter = ctx.config.get('enable_twitter', True)
    enable_reddit = ctx.config.get('enable_reddit', True)
    parallel_profile_count = ctx.config.get('parallel_profile_count', 3)
    max_rounds = ctx.config.get('simulation_max_rounds')  # None이면 무제한

    # 1) create_simulation
    sim_manager = SimulationManager()
    state = sim_manager.create_simulation(
        project_id=ctx.run_id,
        graph_id=graph_id,
        enable_twitter=enable_twitter,
        enable_reddit=enable_reddit,
    )
    simulation_id = state.simulation_id
    logger.info(f'simulation: created sim_id={simulation_id}')

    # 2) prepare_simulation (entities + profiles + config)
    logger.info('simulation: prepare 시작 (profiles + config 생성)')
    sim_manager.prepare_simulation(
        simulation_id=simulation_id,
        simulation_requirement=simulation_requirement,
        document_text=document_text,
        use_llm_for_profiles=True,
        parallel_profile_count=parallel_profile_count,
    )

    # 3) SimulationRunner subprocess 실행
    platform = 'parallel' if (enable_twitter and enable_reddit) else (
        'twitter' if enable_twitter else 'reddit'
    )
    logger.info(f'simulation: start_simulation platform={platform}, max_rounds={max_rounds}')
    SimulationRunner.start_simulation(
        simulation_id=simulation_id,
        platform=platform,
        max_rounds=max_rounds,
        enable_graph_memory_update=False,
    )

    # 4) 폴링 (subprocess 비동기 → 완료/실패까지 대기)
    deadline = time.time() + _SIM_POLL_MAX_S
    last_round = -1
    while True:
        if time.time() > deadline:
            SimulationRunner.stop_simulation(simulation_id)
            raise TimeoutError(
                f'simulation: 폴링 타임아웃 ({_SIM_POLL_MAX_S}s) — 강제 중지'
            )
        run_state = SimulationRunner.get_run_state(simulation_id)
        if run_state is None:
            raise RuntimeError(f'simulation: run_state 사라짐 sim_id={simulation_id}')

        if run_state.current_round != last_round:
            logger.info(
                f'simulation: round={run_state.current_round}/{run_state.total_rounds} '
                f'tw={run_state.twitter_actions_count} rd={run_state.reddit_actions_count}'
            )
            last_round = run_state.current_round

        if run_state.runner_status == RunnerStatus.COMPLETED:
            break
        if run_state.runner_status == RunnerStatus.FAILED:
            raise RuntimeError(f'simulation: 실패: {run_state.error}')
        time.sleep(_SIM_POLL_INTERVAL_S)

    final_state = SimulationRunner.get_run_state(simulation_id)
    meta = {
        'graph_id': graph_id,
        'simulation_id': simulation_id,
        'simulation_requirement': simulation_requirement,
        'platform': platform,
        'total_rounds': final_state.total_rounds,
        'twitter_actions_count': final_state.twitter_actions_count,
        'reddit_actions_count': final_state.reddit_actions_count,
        'completed_at': final_state.completed_at,
    }
    (ctx.tmp_dir / 'simulation_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    logger.info(f'simulation: 완료 sim_id={simulation_id}')
    return meta


# ─────────────────────────────────────────────────────────────────────
# report adapter
# ─────────────────────────────────────────────────────────────────────

def report_adapter(ctx: StepContext) -> dict:
    """ReportAgent.generate_report → reports/{report_id}/ 산출.

    ReportAgent는 자체 reports/ 디렉토리에 chapter별 .md를 쓴다.
    pipeline tmp_dir에는 메타와 report_id만 기록. 실제 산출물 경로는
    SimulationRunner와 동일하게 서비스 관리 디렉토리에 유지된다.
    """
    ctx.tmp_dir.mkdir(parents=True, exist_ok=True)
    if ctx.prev_step_dir is None:
        raise RuntimeError('report: prev_step_dir 없음 (simulation 단계 산출 필요)')

    sim_meta = json.loads(
        (ctx.prev_step_dir / 'simulation_meta.json').read_text(encoding='utf-8')
    )
    graph_id = sim_meta['graph_id']
    simulation_id = sim_meta['simulation_id']
    simulation_requirement = sim_meta['simulation_requirement']

    report_id = f'run_{ctx.run_id[:8]}'
    logger.info(f'report: generate_report 시작 report_id={report_id}')

    agent = ReportAgent(
        graph_id=graph_id,
        simulation_id=simulation_id,
        simulation_requirement=simulation_requirement,
    )
    report = agent.generate_report(report_id=report_id)

    sections_count = len(report.outline.sections) if report.outline else 0
    meta = {
        'report_id': report_id,
        'graph_id': graph_id,
        'simulation_id': simulation_id,
        'sections_count': sections_count,
        'status': str(report.status),
    }
    (ctx.tmp_dir / 'report_meta.json').write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    logger.info(f'report: 완료 report_id={report_id} sections={sections_count}')
    return meta


# ─────────────────────────────────────────────────────────────────────
# Side-effect 등록 (모듈 로드 시점)
# ─────────────────────────────────────────────────────────────────────

register_step('graph', graph_adapter)
register_step('agents', agents_adapter)
register_step('simulation', simulation_adapter)
register_step('report', report_adapter)
logger.info('pipeline_adapters: 4개 step 등록 완료 (graph/agents/simulation/report)')
