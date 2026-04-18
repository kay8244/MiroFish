# MiroFish 종합 분석 리포트

**분석일:** 2026-03-28
**대상:** MiroFish — 멀티에이전트 AI 예측 엔진
**분석자:** Architect (Phase 1) + Security/Code/Performance/AI Quality Reviewers (Phase 2)

---

## Executive Summary

MiroFish는 지식그래프 + LLM + 멀티에이전트 시뮬레이션을 결합한 혁신적인 예측 플랫폼입니다. Python/Flask 백엔드(~20K LOC)와 Vue 3 프론트엔드(~24K LOC)로 구성되며, OASIS 프레임워크와 Zep Cloud를 활용합니다.

**연구 프로토타입으로서는 인상적인 기능 완성도**를 보이지만, **프로덕션 배포에는 심각한 구조적 문제**가 있습니다:

| 영역 | 등급 | 핵심 이슈 |
|------|------|----------|
| 아키텍처 | **C+** | DB 없음(JSON-on-disk), 파일 IPC 경쟁조건, 2,711줄 API 라우트에 비즈니스 로직 |
| 코드 품질 | **C** | 테스트 0%, bare except 4건, 3,248줄 스크립트 중복, 5,150줄 Vue 컴포넌트 |
| 보안 | **D** | P0 4건 (traceback 51건 노출, CORS *, XSS 6건, 하드코딩 시크릿) |
| 성능 | **C** | 보고서 1회당 LLM 50~80회 직렬 호출, TaskManager 메모리 누수 |
| LLM/AI 품질 | **B-** | ReACT 루프 견고, graceful degradation 양호. 단 환각 검증 부재, JSON 복구 중복 |
| 배포/운영 | **D+** | 단일 스테이지 Docker, dev 서버로 프로덕션, 인증 전무, rate limiting 없음 |
| 문서화 | **B** | README (CN/EN) 충실, 데모 영상 제공. API 문서(OpenAPI) 없음 |

---

## 1. 아키텍처 분석

### 1.1 백엔드 구조 — 관심사 분리 위반

3-Blueprint 구조 자체는 적절하나, `api/simulation.py` (2,711줄)에 비즈니스 로직이 78% 내장:

| 문제 | 위치 | 영향 |
|------|------|------|
| 117줄 헬퍼가 파일시스템 직접 조작 | `api/simulation.py:239-355` | API ↔ 서비스 경계 붕괴 |
| 인라인 진행콜백 클로저 100줄 | `api/simulation.py:504-603` | 테스트 불가능 |
| Raw SQL이 라우트에 직접 | `api/simulation.py:2018-2039` | Repository 패턴 부재 |
| Config.validate() 미호출 | `__init__.py` (app factory) | 런타임까지 설정 오류 미감지 |

### 1.2 데이터 영속화 — DB 없는 JSON-on-disk

| Manager | 저장 | 재시작 생존 | 동시성 안전 |
|---------|------|-----------|-----------|
| TaskManager | 인메모리 dict | **NO** | YES (thread lock) |
| ProjectManager | JSON 파일 | YES | **NO** (파일 락 없음) |
| SimulationManager | 인메모리 + 파일 | 부분적 | **NO** |
| SimulationRunner | 클래스 변수 dict | **NO** | 약함 (GIL만) |

### 1.3 파일 기반 IPC — 3가지 경쟁 조건

`services/simulation_ipc.py:157-176`:
1. **부분 쓰기 읽기** — 응답 파일 생성 중 클라이언트가 읽으면 `JSONDecodeError`
2. **이중 삭제** — 클라이언트/서버 모두 명령 파일 삭제 시도
3. **비원자적 응답+삭제** — 크래시 시 명령 잔존, 응답 없음

파일 락 사용: **0건** (전체 백엔드 검색 결과)

### 1.4 프론트엔드 아키텍처

- **Step4Report.vue (5,150줄)** — 프로젝트 최대 파일. 리포트 렌더링, 에이전트 로그, 콘솔, 워크플로 타임라인이 단일 파일
- **views/Process.vue (2,067줄)** — **데드 코드** (라우터에서 미참조, `router/index.js:3`이 MainView.vue를 import)
- **상태관리 없음** — Vuex/Pinia 미사용, `pendingUpload.js` (33줄)만 존재
- **TypeScript 미사용** — 14,000+ 줄 프론트엔드에 타입 검사 없음
- **CSS 중복** — Step4Report.vue ↔ Step5Interaction.vue 간 300줄+ 완전 동일 CSS

---

## 2. 코드 품질

### 2.1 대형 파일 (추출 필요)

| 파일 | 줄 수 | 추출 가능 모듈 수 |
|------|-------|-----------------|
| `frontend/src/components/Step4Report.vue` | 5,150 | 4개 (ReportViewer, AgentLog, Header, 공유CSS) |
| `backend/app/api/simulation.py` | 2,711 | 5개 (entities, run, interview, data, prepare_service) |
| `backend/app/services/report_agent.py` | 2,571 | 3개 (logger, models, tools) |
| `backend/app/services/simulation_runner.py` | 1,763 | 3개 (models, process, monitor) |
| `frontend/src/views/Process.vue` | 2,067 | **삭제** (데드 코드) |

### 2.2 스크립트 중복 — 81% 동일

`run_twitter_simulation.py` (780줄) vs `run_reddit_simulation.py` (769줄): diff 148줄만 차이.
`run_parallel_simulation.py` (1,699줄)에도 동일 로직 중복. **총 ~3,248줄 중복.**

`BaseSimulationRunner` 추상 클래스 추출 시 각 스크립트 50~60줄로 축소 가능.

### 2.3 에러 처리

| 패턴 | 건수 | 심각도 |
|------|------|--------|
| `traceback.format_exc()` API 응답 노출 | **51건** | CRITICAL |
| Bare `except:` (모든 예외 삼킴) | **4건** | CRITICAL |
| `except Exception:` (과도한 범위) | **160건** | HIGH |
| SQLite 연결 `with` 미사용 | 다수 | MEDIUM |

### 2.4 테스트 — **커버리지 0%**

유일한 테스트: `scripts/test_profile_format.py` (독립 스크립트, pytest 미연동).
pytest 설정, conftest.py, tests/ 디렉토리 없음.

**우선 테스트 대상:** simulation_config_generator (bare except → 사일런트 오류), oasis_profile_generator (타입 미검증), simulation_runner (프로세스 관리)

---

## 3. 보안 분석

### P0 — Critical (즉시 수정)

| # | 이슈 | 건수 | 위치 |
|---|------|------|------|
| 1 | Traceback API 응답 노출 | 51건 | report.py:17, simulation.py:29, graph.py:5 |
| 2 | CORS `origins: '*'` + 인증 전무 | 1건 | `__init__.py:43` |
| 3 | v-html XSS (renderMarkdown 미살균) | 6건 | Step4Report.vue:51,1557,1569 / Step5Interaction.vue:51,273,403 |
| 4 | 하드코딩 SECRET_KEY 폴백 | 1건 | `config.py:24` (`'mirofish-secret-key'`) |

### P1 — High

| # | 이슈 | 위치 |
|---|------|------|
| 5 | 인증/인가 메커니즘 전무 | 모든 API 라우트 |
| 6 | Path Traversal — ID 검증 없이 경로 결합 | `project.py:115`, `simulation_manager.py:140`, `report_agent.py:1912` |
| 7 | LLM Prompt Injection 방어 없음 | `ontology_generator.py:184-193`, `report.py:537-546` |
| 8 | DEBUG 기본값 True | `config.py:25` |
| 9 | IPC 파일 락 없음 | `simulation_ipc.py:157-176` |

### P2 — Medium

| # | 이슈 | 위치 |
|---|------|------|
| 10 | Rate limiting 전무 | 전체 API |
| 11 | 요청 본문 전체 로그 기록 (민감정보 포함 가능) | `__init__.py:56-57` |
| 12 | Zep API key 간접 노출 (traceback 경유) | `graph_builder.py:50` |
| 13 | Docker dev 서버로 프로덕션 실행 | `Dockerfile:28-29` |

**양호 항목:** 파일 업로드 UUID 안전 파일명(`project.py:257-259`), 스크립트 다운로드 allowlist(`simulation.py:1334-1341`), API 키 환경변수 관리(.env), .gitignore 포함

---

## 4. 성능 분석

### Critical — 보고서 생성 LLM 호출 폭발

보고서 1회 생성 시 **50~80회 순차 LLM 호출** (추정 소요: 150초~640초):
- `plan_outline`: 1회
- 섹션 ReACT 루프: 5회 × 6섹션 = 30회
- `insight_forge` 서브쿼리: 최대 30회
- `interview_agents` 내부: 최대 18회

### 최적화 기회

| 개선 | 예상 효과 | 위치 |
|------|----------|------|
| 섹션별 ReACT 루프 병렬화 | ~80% 시간 단축 | `report_agent.py:1636` |
| insight_forge 서브쿼리를 메인 LLM 통합 | 섹션당 5회 절감 | `zep_tools.py:981-988` |
| IPC 적응형 폴링 + 원자적 쓰기 | 평균 250ms→50ms | `simulation_ipc.py:157-176` |
| TaskManager cleanup 주기 실행 | 메모리 누수 방지 | `task.py:172` (미호출) |
| `get_report_by_simulation` O(N)→O(1) | 인덱스 파일 도입 | `report_agent.py:2503` |

### 허용 가능

- `retry.py` 지수 백오프 + jitter — 교과서적 구현
- PyMuPDF 페이지 단위 스트리밍 — 일반 PDF에 적합
- SQLite 페이지네이션 쿼리 — 현재 규모에서 적절

---

## 5. LLM/AI 품질

### 프롬프트 엔지니어링

- **112개 프롬프트**가 8개 파일에 인라인 문자열로 분산 — 버전 관리 불가
- **품질 자체는 양호**: `report_agent.py`의 ReACT 프롬프트는 도구 사용 워크플로, 올바른/잘못된 예시, 최소 호출 횟수 등 상세 지시
- `oasis_profile_generator.py`의 시스템 프롬프트는 상대적으로 단순

### 토큰 비용 추정 (30 엔티티 기준)

| 단계 | 추정 토큰 |
|------|----------|
| 온톨로지 생성 | ~20K |
| 프로필 생성 (30개) | ~75K |
| 시뮬레이션 설정 | ~20K |
| 보고서 생성 | ~360K |
| **합계** | **~475K / 시뮬레이션** |

gpt-4o-mini: **~$0.15-0.30**, gpt-4o: **~$2.50-5.00**
토큰 사용량 모니터링: **없음** (`response.usage` 미추적)

### 환각 처리 — 구조 검증만, 의미 검증 없음

| 서비스 | 구조 검증 | 의미 검증 |
|--------|----------|----------|
| ontology_generator | 필드 존재, 개수 제한 | **없음** — 추상 개념 엔티티 감지 불가 |
| oasis_profile_generator | bio/persona 존재 | **없음** — `age` 타입 미검증 (문자열 통과) |
| report_agent | Final Answer 프리픽스 확인 | **없음** — 도구 결과와 무관한 내용 감지 불가 |

### JSON 파싱 — 3곳 중복 구현, 위험한 괄호 카운팅

`_fix_truncated_json`이 `oasis_profile_generator.py:590`과 `simulation_config_generator.py:487`에 중복. 문자열 내부 괄호를 구분하지 못하는 단순 카운팅으로 잘못된 JSON 생성 위험.

### 모델 이식성

- OpenAI SDK + 환경변수 base_url — **잘 설계됨**
- `<think>` 태그 제거 (MiniMax 대응) — `llm_client.py:67`
- **갭**: OpenAI 클라이언트가 3곳에서 독립 인스턴스화 (DRY 위반). `response_format: json_object`가 일부 모델 미지원.

### 긍정적 측면

- ReACT 루프 충돌 처리 3단계 에스컬레이션 — 실전적
- LLM 실패 시 일관된 graceful degradation (디폴트 설정, 규칙 기반 생성)
- 도구 호출 파싱 3단계 fallback (XML → 전체 JSON → 마지막 JSON)
- 텍스트 길이 제한 가드레일 체계적 배치

---

## 6. 배포/운영

| 항목 | 현재 상태 | 권장 |
|------|----------|------|
| Dockerfile | 단일 스테이지, `python:3.11` full image | 멀티스테이지 + slim 이미지 |
| 프로덕션 CMD | `npm run dev` (Vite dev + Flask debug) | gunicorn + nginx |
| 로깅 | `utils/logger.py` 기본 설정 | 구조화 로깅 (JSON format) |
| 모니터링 | 없음 | 최소 health check + 메트릭 |
| 환경변수 | `.env.example` 제공 | 비밀 관리자 (Vault 등) 도입 |

---

## 7. SWOT 분석

### Strengths (강점)
- **독창적 컨셉**: 지식그래프 → 에이전트 시뮬레이션 → 예측 리포트의 end-to-end 파이프라인
- **OASIS 프레임워크 통합**: CAMEL-AI의 검증된 시뮬레이션 엔진 활용
- **LLM Graceful Degradation**: 실패 시 일관된 fallback 패턴
- **ReACT 보고서 생성**: 도구 사용 기반 분석 — 단순 요약이 아닌 증거 기반 보고서
- **모델 이식성**: OpenAI 호환 API면 어디든 연결 가능

### Weaknesses (약점)
- **보안 기초 부재**: 인증 없음, CORS *, traceback 노출, XSS, rate limiting 없음
- **DB 없는 아키텍처**: JSON-on-disk → 동시성 불안, 재시작 시 상태 소실
- **테스트 커버리지 0%**: 프로토타입 수준에서도 위험한 수준
- **기술 부채 집중**: simulation.py 2,711줄, Step4Report.vue 5,150줄
- **프론트엔드 TypeScript/상태관리 부재**: 14K LOC에 타입 검사 없음

### Opportunities (기회)
- **Shanda Group 지원**: 자원과 네트워크
- **CAMEL-AI 생태계**: 오픈소스 커뮤니티 확장 가능
- **다양한 시뮬레이션 플랫폼**: Twitter/Reddit 외 확장 용이 (BaseRunner 추출 시)
- **SaaS화 가능성**: 인증/과금 추가 시 서비스화 가능
- **토큰 비용 최적화**: 병렬화만으로 보고서 생성 80% 시간 단축 가능

### Threats (위협)
- **Zep Cloud 단일 의존**: 추상화 레이어 없이 직접 SDK 호출. Zep 서비스 장애 = 전체 시스템 불능
- **보안 취약점 노출 시**: AGPL 라이선스로 소스 공개 상태 — 공격 표면 가시적
- **LLM 비용 확대**: gpt-4o 사용 시 시뮬레이션당 $5 — 대규모 사용에 비용 부담
- **경쟁 플랫폼**: LangChain/CrewAI 기반 유사 프로젝트 등장 가능

---

## 8. 개선 권고 (우선순위별)

### P0 — 즉시 (1주 이내) | 예상 작업: 1~2일

| # | 작업 | 예상 시간 | 효과 |
|---|------|----------|------|
| 1 | Traceback API 응답 제거 (51건) → 로거만 기록 | 2시간 | 보안 P0-1 + P2-3 동시 해결 |
| 2 | SECRET_KEY 폴백 제거 + DEBUG 기본 False | 30분 | 보안 P0-4 + P1-4 |
| 3 | DOMPurify 적용 (v-html 6건) | 1시간 | XSS 완전 차단 |
| 4 | CORS 오리진 환경변수화 | 30분 | 보안 P0-2 |
| 5 | Bare `except:` → `except Exception:` + logging | 30분 | 사일런트 오류 방지 |

### P1 — 단기 (1개월) | 예상 작업: 1~2주

| # | 작업 | 예상 시간 | 효과 |
|---|------|----------|------|
| 6 | API 키 인증 미들웨어 추가 | 4시간 | 비인증 접근 차단 |
| 7 | ID 검증 유틸리티 (Path Traversal 방어) | 2시간 | 파일시스템 조작 방지 |
| 8 | Rate limiting (flask-limiter) | 2시간 | LLM 비용 폭탄 방지 |
| 9 | `api/simulation.py` 서비스 분리 | 8시간 | 2,711줄 → 5개 모듈 |
| 10 | 스크립트 BaseRunner 추출 | 4시간 | 3,248줄 중복 제거 |
| 11 | `Process.vue` 삭제 + import alias 수정 | 30분 | 2,067줄 데드코드 제거 |
| 12 | TaskManager cleanup 주기 실행 | 1시간 | 메모리 누수 방지 |

### P2 — 중기 (1분기) | 예상 작업: 2~4주

| # | 작업 | 예상 시간 | 효과 |
|---|------|----------|------|
| 13 | IPC 원자적 쓰기 (`os.replace`) + 적응형 폴링 | 4시간 | 경쟁조건 해소, IPC 지연 80% 단축 |
| 14 | 보고서 섹션 ReACT 병렬화 | 8시간 | 보고서 생성 80% 시간 단축 |
| 15 | JSON-on-disk → SQLite 마이그레이션 | 16시간 | 동시성/신뢰성/쿼리 개선 |
| 16 | JSON 복구 로직 통합 (`utils/json_repair.py`) | 4시간 | 3곳 중복 제거, 안전성 향상 |
| 17 | LLMClient 통합 (3곳 → 1곳) | 4시간 | 모델 호환성 일원화 |
| 18 | 프롬프트 파일 분리 + 버전 관리 | 8시간 | A/B 테스트, 롤백 가능 |
| 19 | LLM 출력 타입 검증 (Pydantic) | 8시간 | 환각/타입 오류 사전 차단 |
| 20 | 핵심 테스트 작성 (커버리지 30% 목표) | 16시간 | 파싱 오류, 프로세스 관리 버그 방지 |
| 21 | Step4Report.vue 분할 (4개 서브 컴포넌트) | 8시간 | 5,150줄 → 관리 가능 단위 |
| 22 | 공유 CSS 추출 | 2시간 | 300줄+ 중복 제거 |

### P3 — 장기 (6개월+)

| # | 작업 | 효과 |
|---|------|------|
| 23 | Pinia 상태관리 도입 | 컴포넌트 간 데이터 동기화 |
| 24 | TypeScript 점진적 마이그레이션 | 타입 안전성 확보 |
| 25 | Dockerfile 멀티스테이지 + gunicorn | 프로덕션 배포 준비 |
| 26 | 토큰 사용량 모니터링 + 비용 대시보드 | 운영 가시성 |
| 27 | Zep 추상화 레이어 | 벤더 종속 탈피 |
| 28 | Celery/RQ 태스크 큐 | 백그라운드 작업 안정성 |

---

## 분석 통계

| 항목 | 수치 |
|------|------|
| 분석 대상 파일 | 58개 (Python 28, Vue 12, JS 7, 설정 11) |
| 총 코드 라인 | ~41,500줄 |
| 발견 이슈 | **P0: 5건, P1: 7건, P2: 10건, P3 최적화: 6건** |
| 파일:라인 참조 | 85+ 구체적 참조 포함 |
| 분석 Phase | 3단계 (아키텍처 → 4개 전문 병렬 → 종합) |
