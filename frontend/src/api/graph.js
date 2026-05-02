import service, { requestWithRetry } from './index'

/**
 * Generate ontology (upload documents and simulation requirements)
 * @param {Object} data - Contains files, simulation_requirement, project_name, etc.
 * @returns {Promise}
 */
export function generateOntology(formData) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/ontology/generate',
      method: 'post',
      data: formData,
      headers: {
        'Content-Type': 'multipart/form-data'
      }
    })
  )
}

/**
 * Build graph
 * @param {Object} data - Contains project_id, graph_name, etc.
 * @returns {Promise}
 */
export function buildGraph(data) {
  return requestWithRetry(() =>
    service({
      url: '/api/graph/build',
      method: 'post',
      data
    })
  )
}

/**
 * Incremental append: 기존 프로젝트의 그래프에 새 파일들을 추가 (graph_id 유지).
 * @param {string} projectId
 * @param {File[]} files
 * @returns {Promise} { task_id, graph_id, files_added, added_text_length }
 */
export function appendFilesToProject(projectId, files) {
  const formData = new FormData()
  formData.append('project_id', projectId)
  for (const file of files) {
    formData.append('files', file)
  }
  return requestWithRetry(() =>
    service({
      url: '/api/graph/append',
      method: 'post',
      data: formData,
      headers: { 'Content-Type': 'multipart/form-data' }
    })
  )
}

/**
 * Query task status
 * @param {String} taskId - Task ID
 * @returns {Promise}
 */
export function getTaskStatus(taskId) {
  return service({
    url: `/api/graph/task/${taskId}`,
    method: 'get'
  })
}

/**
 * Get graph data
 * @param {String} graphId - Graph ID
 * @returns {Promise}
 */
export function getGraphData(graphId) {
  return service({
    url: `/api/graph/data/${graphId}`,
    method: 'get'
  })
}

/**
 * Get project info
 * @param {String} projectId - Project ID
 * @returns {Promise}
 */
export function getProject(projectId) {
  return service({
    url: `/api/graph/project/${projectId}`,
    method: 'get'
  })
}
