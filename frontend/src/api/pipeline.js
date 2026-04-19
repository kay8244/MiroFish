import service, { requestWithRetry } from './index'

/**
 * Start a new pipeline run (uploads seed files and triggers 5-step execution).
 *
 * Returns 202 with `{ run_id, status_url }` once the orchestrator has persisted
 * the run row. The actual pipeline work continues asynchronously — poll
 * `getPipelineStatus(run_id)` to observe progress.
 *
 * @param {Object} opts
 * @param {File[]} opts.seedFiles - One or more PDF/MD/TXT files (<=50MB each)
 * @param {string} [opts.assumptionsVersion] - Assumptions YAML tag (default: 'ai_server_si_wafer_v1')
 * @param {Object} [opts.extraConfig] - Adapter tuning knobs passed through to ctx.config.
 *   Recognized keys:
 *     - simulation_max_rounds (number | null): cap OASIS rounds (null = unlimited)
 *     - enable_twitter (boolean, default true)
 *     - enable_reddit (boolean, default true)
 *     - parallel_profile_count (number, default 3)
 *     - simulation_requirement (string): overrides default requirement text
 *     - assumptions_text (string): YAML-as-text embedded into simulation_requirement
 *     - chunk_size / chunk_overlap / zep_batch_size (graph step)
 */
export const startPipelineRun = ({ seedFiles, assumptionsVersion, extraConfig }) => {
  const form = new FormData()
  for (const f of seedFiles) {
    form.append('seed_files', f, f.name)
  }
  if (assumptionsVersion) {
    form.append('assumptions_version', assumptionsVersion)
  }
  if (extraConfig && Object.keys(extraConfig).length > 0) {
    form.append('extra_config', JSON.stringify(extraConfig))
  }
  return service.post('/api/pipeline/run', form, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

/**
 * Fetch A3-shape run status. Intended for 2-second polling.
 *
 * Response shape (see backend services/pipeline_orchestrator.py::get_status):
 *   {
 *     run_id, status, current_step, resumable_from,
 *     error: null | {
 *       step, retry_count, retry_exhausted, wall_clock_exceeded,
 *       summary, manifest_url
 *     },
 *     steps: [{ name, status, duration_s, llm_calls, retry_count }]
 *   }
 */
export const getPipelineStatus = (runId) => {
  return service.get(`/api/pipeline/status/${runId}`)
}

/** Fetch the full run manifest JSON (per-step meta, version info, inputs). */
export const getPipelineManifest = (runId) => {
  return service.get(`/api/pipeline/manifest/${runId}`)
}

/**
 * Resume a failed run. The orchestrator purges any partial Zep graph and
 * restarts from the failed step (after seed_upload, which is preserved).
 *
 * 409 Conflict if already completed or Zep purge exhausted 3 retries.
 */
export const resumePipelineRun = (runId) => {
  return requestWithRetry(
    () => service.post(`/api/pipeline/resume/${runId}`),
    2,
    1000
  )
}

export const PIPELINE_STEP_NAMES = [
  'seed_upload',
  'graph',
  'agents',
  'simulation',
  'report'
]

export const PIPELINE_STEP_LABELS = {
  seed_upload: 'Seed 업로드',
  graph: 'Graph 구축 (Ontology + Zep)',
  agents: 'Agents (pass-through)',
  simulation: 'Simulation (OASIS 병렬)',
  report: 'Report 생성'
}
