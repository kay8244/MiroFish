/**
 * MiroFish 프론트엔드 공통 상수
 */

// 폴링 간격 (ms)
export const POLLING_INTERVALS = {
  AGENT_LOG: 2000,        // Agent 로그 폴링
  CONSOLE_LOG: 1500,      // 콘솔 로그 폴링
  STATUS_CHECK: 3000,     // 상태 확인 폴링
  PROFILES: 2000,         // 프로필 생성 폴링
  CONFIG: 2000,           // 설정 생성 폴링
  SIMULATION_STATUS: 5000, // 시뮬레이션 상태 폴링
  SIMULATION_DETAIL: 2000, // 시뮬레이션 상세 폴링
}

// API 타임아웃 (ms)
export const API_TIMEOUTS = {
  DEFAULT: 300000,   // 5분 (기본)
  LONG: 600000,      // 10분 (긴 작업)
}

// 페이지네이션
export const PAGINATION = {
  DEFAULT_LIMIT: 20,
  MAX_LIMIT: 100,
}
