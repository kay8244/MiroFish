# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MiroFish is a multi-agent AI prediction engine. Users upload seed materials (reports, stories), and MiroFish builds a parallel digital world where thousands of AI agents with independent personalities simulate social interactions. The system produces prediction reports and an interactive environment.

The simulation engine is powered by **OASIS** (camel-oasis) for social media simulation (Twitter/Reddit platforms).

## Development Commands

All commands run from the `MiroFish/` root directory:

```bash
# Install all dependencies (Node + Python)
npm run setup:all

# Start both frontend and backend concurrently
npm run dev

# Start individually
npm run frontend    # Vite dev server on :3000
npm run backend     # Flask on :5001

# Build frontend
npm run build

# Backend Python tests
cd backend && uv run pytest
```

**Prerequisites:** Node.js 18+, Python >=3.11 <=3.12, uv (Python package manager)

## Environment Variables

Copy `.env.example` to `.env`. Required keys:
- `LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL_NAME` — any OpenAI SDK-compatible LLM API
- `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` — Graphiti(Neo4j) 지식 그래프. 로컬 컨테이너는 `docker compose -f graphiti-db/docker-compose.yml up -d`
- Optional: `LLM_BOOST_*` variants for acceleration
- Optional (legacy): `ZEP_API_KEY` / `ZEP_BASE_URL` — `uv sync --extra zep`로 Zep Cloud 경로 활성화 시에만 필요. 기본 Graphiti 경로에서는 불필요.

## Architecture

### Backend (Flask + Python)

Entry point: `backend/run.py` → `app.create_app()` (Flask factory pattern)

**API Blueprints** (`app/api/`):
- `/api/graph` — Knowledge graph construction from uploaded documents
- `/api/simulation` — OASIS simulation management (create, run, monitor)
- `/api/report` — Report generation via ReportAgent

**Services** (`app/services/`): Core business logic layer
- `graph_builder.py` — Graphiti(Neo4j) 기반 지식 그래프 빌더 (Phase 6 canonical)
- `graph_builder_zep_legacy.py` — 기존 Zep Cloud 빌더 (optional `--extra zep`, 비활성)
- `ontology_generator.py` — Extracts entity relationships using LLM
- `oasis_profile_generator.py` — Generates agent personas (legacy Zep enrichment은 soft-import)
- `simulation_config_generator.py` — Configures simulation parameters
- `simulation_runner.py` — Runs OASIS simulations in separate processes
- `simulation_manager.py` — Manages simulation lifecycle
- `simulation_ipc.py` — Inter-process communication for simulation
- `report_agent.py` — LLM-powered report generation with tool-use
- `text_processor.py` — Document chunking and processing
- `graphiti_*` — Graphiti memory integration (entity reader, tools, graph memory updater)

**Utils** (`app/utils/`):
- `llm_client.py` — Unified LLM client (supports OpenAI/Anthropic SDK format)
- `graphiti_client.py` / `graphiti_paging.py` — Graphiti/Neo4j 클라이언트 팩토리 + Cypher 페이징
- `zep_client_legacy.py` / `zep_paging_legacy.py` — Zep Cloud 경로 (optional extra)
- `file_parser.py` — PDF/MD/TXT file parsing

**Config** (`app/config.py`): Loads from `MiroFish/.env` via python-dotenv. Contains OASIS platform action definitions (Twitter/Reddit) and report agent parameters.

### Frontend (Vue 3 + Vite)

SPA with Vue Router. Vite proxies `/api` requests to Flask backend at `:5001`.

**5-step workflow mapped to views/components:**
1. `Step1GraphBuild.vue` — Upload seed documents, build knowledge graph
2. `Step2EnvSetup.vue` — Entity extraction, persona generation, environment config
3. `Step3Simulation.vue` — Run dual-platform (Twitter+Reddit) parallel simulation
4. `Step4Report.vue` — ReportAgent generates prediction report
5. `Step5Interaction.vue` — Chat with simulated agents or ReportAgent

**Key views:** `Home.vue` (landing), `MainView.vue` (process container), `SimulationRunView.vue` (live simulation), `ReportView.vue`, `InteractionView.vue`

**API layer** (`src/api/`): axios-based with 5min timeout, auto-retry, proxy to backend. Separate modules for `graph.js`, `simulation.js`, `report.js`.

**Visualization:** D3.js for knowledge graph rendering (`GraphPanel.vue`).

### Data Flow

1. User uploads documents → backend parses and chunks text
2. LLM extracts entities/relationships → Graphiti(Neo4j) stores temporal knowledge graph
3. LLM generates agent profiles from ontology
4. OASIS runs multi-agent simulation (Twitter/Reddit platforms in parallel)
5. Simulation results stored in `backend/uploads/simulations/`
6. ReportAgent analyzes simulation data with Graphiti tool-use to produce report
7. Users can chat with any simulated agent post-simulation

### Docker

Single container runs both frontend and backend. Image published to `ghcr.io/666ghj/mirofish`. CI builds on tag push via GitHub Actions.

## Key Conventions

- Backend comments/logs are in Korean; README and some frontend code in Chinese/English
- Backend uses `uv` for Python dependency management (not pip directly)
- File uploads limited to PDF, MD, TXT (50MB max), stored in `backend/uploads/`
- Simulation processes run as separate Python subprocesses managed by `SimulationRunner`
- License: AGPL-3.0
