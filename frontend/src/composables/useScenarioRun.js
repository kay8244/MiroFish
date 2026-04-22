/**
 * B 시나리오 — 같은 graph 위에 새 simulation_requirement 로 시뮬+리포트.
 *
 * 체인:
 *   1. createSimulation({ project_id, graph_id, simulation_requirement })
 *   2. prepareSimulation({ simulation_id })  + 폴링
 *   3. startSimulation({ simulation_id })    + run-status 폴링
 *   4. generateReport({ simulation_id, force_regenerate: true }) + 폴링
 *
 * 각 단계 완료/실패는 phase + status 로 노출. UI 가 진행률 표시.
 */
import { ref } from 'vue'
import {
  createSimulation,
  prepareSimulation,
  getPrepareStatus,
  startSimulation,
  getRunStatus,
  getSimulation,
} from '../api/simulation'
import { generateReport, getReportStatus } from '../api/report'

const PHASE = {
  IDLE: 'idle',
  CREATING: 'creating',
  PREPARING: 'preparing',
  SIMULATING: 'simulating',
  REPORTING: 'reporting',
  DONE: 'done',
  ERROR: 'error',
}

const POLL_INTERVAL_MS = 3000
const PREPARE_MAX_S = 600
const SIM_MAX_S = 1800
const REPORT_MAX_S = 600

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

export function useScenarioRun() {
  const phase = ref(PHASE.IDLE)
  const phaseLabel = ref('')
  const errorMessage = ref('')
  const newSimulationId = ref(null)
  const newReportId = ref(null)
  const isRunning = ref(false)

  const _poll = async (fn, doneCheck, maxSeconds, label) => {
    const deadline = Date.now() + maxSeconds * 1000
    while (Date.now() < deadline) {
      const res = await fn()
      const done = doneCheck(res)
      if (done === 'done') return res
      if (done === 'fail') {
        const reason = res?.error || res?.data?.error || '알 수 없는 실패'
        throw new Error(`${label}: ${reason}`)
      }
      await sleep(POLL_INTERVAL_MS)
    }
    throw new Error(`${label}: 타임아웃 (${maxSeconds}s)`)
  }

  /**
   * 새 시나리오 실행.
   * @param {object} opts
   * @param {string} opts.simulationId — 기존 simulation_id (project_id/graph_id 추출용)
   * @param {string} opts.simulationRequirement — 새 시나리오 질문
   */
  const runScenario = async ({ simulationId, simulationRequirement }) => {
    if (isRunning.value) {
      throw new Error('이미 시나리오 실행 중입니다')
    }
    if (!simulationId) throw new Error('simulationId 가 필요합니다')
    if (!simulationRequirement || !simulationRequirement.trim()) {
      throw new Error('새 시나리오 질문을 입력하세요')
    }

    isRunning.value = true
    errorMessage.value = ''
    newSimulationId.value = null
    newReportId.value = null

    try {
      // 0. 기존 sim 에서 project_id + graph_id 추출
      phase.value = PHASE.CREATING
      phaseLabel.value = '기존 그래프 정보 조회 중...'
      const baseRes = await getSimulation(simulationId)
      const baseSim = baseRes?.data
      if (!baseSim) throw new Error('기존 시뮬레이션 조회 실패')
      const projectId = baseSim.project_id
      const graphId = baseSim.graph_id
      if (!projectId || !graphId) {
        throw new Error('기존 시뮬레이션에 project_id/graph_id 가 없습니다')
      }

      // 1. createSimulation (그래프 재사용)
      phaseLabel.value = '새 시뮬레이션 생성 중...'
      const createRes = await createSimulation({
        project_id: projectId,
        graph_id: graphId,
        simulation_requirement: simulationRequirement.trim(),
        enable_twitter: baseSim.enable_twitter ?? true,
        enable_reddit: baseSim.enable_reddit ?? true,
      })
      const newSimId = createRes?.data?.simulation_id
      if (!newSimId) throw new Error('새 시뮬레이션 생성 실패')
      newSimulationId.value = newSimId

      // 2. prepareSimulation + 폴링
      phase.value = PHASE.PREPARING
      phaseLabel.value = '에이전트 페르소나 + 시뮬 설정 생성 중...'
      const prepareRes = await prepareSimulation({ simulation_id: newSimId })
      // 이미 ready 인 경우 스킵
      if (prepareRes?.data?.already_prepared) {
        // 새 sim 이라 거의 발생 안 함
      } else {
        // task_id 가 있어야 backend 가 task 의 진짜 상태 (failed 등)를 리턴함.
        // 누락하면 backend 는 "not_started" placeholder 리턴 → 폴링 무한 루프.
        const prepareTaskId = prepareRes?.data?.task_id
        await _poll(
          async () => {
            // 두 소스 동시 확인: (1) task 상태, (2) sim 자체 상태
            // task 가 사라졌거나 sim 이 직접 failed 로 마킹된 경우도 잡아야 함.
            const [statusRes, simRes] = await Promise.all([
              getPrepareStatus({
                ...(prepareTaskId ? { task_id: prepareTaskId } : {}),
                simulation_id: newSimId,
              }),
              getSimulation(newSimId),
            ])
            return { status: statusRes?.data, sim: simRes?.data }
          },
          (res) => {
            const st = res?.status?.status
            const simStatus = res?.sim?.status
            const simError = res?.sim?.error
            // sim 이 failed 면 즉시 종료 (backend 가 task fail 표시 못한 경우 대비)
            if (simStatus === 'failed') {
              // 에러 메시지를 폴링 함수가 잡을 수 있도록 res 에 주입
              res.error = simError || 'simulation failed'
              return 'fail'
            }
            if (st === 'ready' || st === 'completed' || simStatus === 'ready') return 'done'
            if (st === 'failed') return 'fail'
            return null
          },
          PREPARE_MAX_S,
          'prepare'
        )
      }

      // 3. startSimulation + run-status 폴링
      phase.value = PHASE.SIMULATING
      phaseLabel.value = 'OASIS 시뮬레이션 실행 중 (Twitter + Reddit)...'
      await startSimulation({ simulation_id: newSimId })
      await _poll(
        () => getRunStatus(newSimId),
        (res) => {
          const data = res?.data || {}
          const tw = data.twitter_status
          const rd = data.reddit_status
          const fail = data.status === 'failed' || tw === 'failed' || rd === 'failed'
          if (fail) return 'fail'
          // 두 플랫폼 모두 종료 상태
          const twDone = !data.enable_twitter || ['completed', 'stopped'].includes(tw)
          const rdDone = !data.enable_reddit || ['completed', 'stopped'].includes(rd)
          if (twDone && rdDone) return 'done'
          return null
        },
        SIM_MAX_S,
        'simulation'
      )

      // 4. generateReport + 폴링
      phase.value = PHASE.REPORTING
      phaseLabel.value = '보고서 생성 중...'
      const repRes = await generateReport({
        simulation_id: newSimId,
        force_regenerate: true,
      })
      const reportId = repRes?.data?.report_id
      if (!reportId) throw new Error('보고서 ID 없음')
      newReportId.value = reportId

      await _poll(
        () => getReportStatus(reportId),
        (res) => {
          const st = res?.data?.status
          if (st === 'completed') return 'done'
          if (st === 'failed') return 'fail'
          return null
        },
        REPORT_MAX_S,
        'report'
      )

      phase.value = PHASE.DONE
      phaseLabel.value = '완료! 새 보고서 준비됨'
    } catch (err) {
      phase.value = PHASE.ERROR
      errorMessage.value = err?.message || String(err)
      phaseLabel.value = `실패: ${errorMessage.value}`
    } finally {
      isRunning.value = false
    }
  }

  const reset = () => {
    if (isRunning.value) return
    phase.value = PHASE.IDLE
    phaseLabel.value = ''
    errorMessage.value = ''
    newSimulationId.value = null
    newReportId.value = null
  }

  return {
    PHASE,
    phase,
    phaseLabel,
    errorMessage,
    newSimulationId,
    newReportId,
    isRunning,
    runScenario,
    reset,
  }
}
