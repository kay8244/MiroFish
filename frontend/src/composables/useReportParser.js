/**
 * Composable for parsing report agent tool results.
 * Extracts structured data from text-based tool outputs.
 */

// Tool configurations with display names and colors
export const toolConfig = {
  'insight_forge': {
    name: 'Deep Insight',
    color: 'purple',
    icon: 'lightbulb'
  },
  'panorama_search': {
    name: 'Panorama Search',
    color: 'blue',
    icon: 'globe'
  },
  'interview_agents': {
    name: 'Agent Interview',
    color: 'green',
    icon: 'users'
  },
  'quick_search': {
    name: 'Quick Search',
    color: 'orange',
    icon: 'zap'
  },
  'get_graph_statistics': {
    name: 'Graph Stats',
    color: 'cyan',
    icon: 'chart'
  },
  'get_entities_by_type': {
    name: 'Entity Query',
    color: 'pink',
    icon: 'database'
  }
}

export function getToolDisplayName(toolName) {
  return toolConfig[toolName]?.name || toolName
}

export function getToolColor(toolName) {
  return toolConfig[toolName]?.color || 'gray'
}

export function getToolIcon(toolName) {
  return toolConfig[toolName]?.icon || 'tool'
}

export function parseInsightForge(text) {
  const result = {
    query: '',
    simulationRequirement: '',
    stats: { facts: 0, entities: 0, relationships: 0 },
    subQueries: [],
    facts: [],
    entities: [],
    relations: []
  }

  try {
    const queryMatch = text.match(/Analysis Question:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()

    const reqMatch = text.match(/Prediction Scenario:\s*(.+?)(?:\n|$)/)
    if (reqMatch) result.simulationRequirement = reqMatch[1].trim()

    const factMatch = text.match(/Related Prediction Facts:\s*(\d+)/)
    const entityMatch = text.match(/Entities Involved:\s*(\d+)/)
    const relMatch = text.match(/Relationship Chains:\s*(\d+)/)
    if (factMatch) result.stats.facts = parseInt(factMatch[1])
    if (entityMatch) result.stats.entities = parseInt(entityMatch[1])
    if (relMatch) result.stats.relationships = parseInt(relMatch[1])

    const subQSection = text.match(/### Sub-Questions Analyzed\n([\s\S]*?)(?=\n###|$)/)
    if (subQSection) {
      const lines = subQSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.subQueries = lines.map(l => l.replace(/^\d+\.\s*/, '').trim()).filter(Boolean)
    }

    const factsSection = text.match(/### [Key Facts][\s\S]*?\n([\s\S]*?)(?=\n###|$)/)
    if (factsSection) {
      const lines = factsSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.facts = lines.map(l => {
        const match = l.match(/^\d+\.\s*"?(.+?)"?\s*$/)
        return match ? match[1].replace(/^"|"$/g, '').trim() : l.replace(/^\d+\.\s*/, '').trim()
      }).filter(Boolean)
    }

    const entitySection = text.match(/### [Core Entities]\n([\s\S]*?)(?=\n###|$)/)
    if (entitySection) {
      const entityText = entitySection[1]
      const entityBlocks = entityText.split(/\n(?=- \*\*)/).filter(b => b.trim().startsWith('- **'))
      result.entities = entityBlocks.map(block => {
        const nameMatch = block.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
        const summaryMatch = block.match(/Summary:\s*"?(.+?)"?(?:\n|$)/)
        const relatedMatch = block.match(/Related Facts:\s*(\d+)/)
        return {
          name: nameMatch ? nameMatch[1].trim() : '',
          type: nameMatch ? nameMatch[2].trim() : '',
          summary: summaryMatch ? summaryMatch[1].trim() : '',
          relatedFactsCount: relatedMatch ? parseInt(relatedMatch[1]) : 0
        }
      }).filter(e => e.name)
    }

    const relSection = text.match(/### [Relationship Chains]\n([\s\S]*?)(?=\n###|$)/)
    if (relSection) {
      const lines = relSection[1].split('\n').filter(l => l.trim().startsWith('-'))
      result.relations = lines.map(l => {
        const match = l.match(/^-\s*(.+?)\s*--\[(.+?)\]-->\s*(.+)$/)
        if (match) {
          return { source: match[1].trim(), relation: match[2].trim(), target: match[3].trim() }
        }
        return null
      }).filter(Boolean)
    }
  } catch (e) {
    console.warn('Parse insight_forge failed:', e)
  }

  return result
}

export function parsePanorama(text) {
  const result = {
    query: '',
    stats: { nodes: 0, edges: 0, activeFacts: 0, historicalFacts: 0 },
    activeFacts: [],
    historicalFacts: [],
    entities: []
  }

  try {
    const queryMatch = text.match(/Query:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()

    const nodesMatch = text.match(/Total Nodes:\s*(\d+)/)
    const edgesMatch = text.match(/Total Edges:\s*(\d+)/)
    const activeMatch = text.match(/Active Facts:\s*(\d+)/)
    const histMatch = text.match(/Historical\/Expired Facts:\s*(\d+)/)
    if (nodesMatch) result.stats.nodes = parseInt(nodesMatch[1])
    if (edgesMatch) result.stats.edges = parseInt(edgesMatch[1])
    if (activeMatch) result.stats.activeFacts = parseInt(activeMatch[1])
    if (histMatch) result.stats.historicalFacts = parseInt(histMatch[1])

    const activeSection = text.match(/### [Active Facts][\s\S]*?\n([\s\S]*?)(?=\n###|$)/)
    if (activeSection) {
      const lines = activeSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.activeFacts = lines.map(l => {
        return l.replace(/^\d+\.\s*/, '').replace(/^"|"$/g, '').trim()
      }).filter(Boolean)
    }

    const histSection = text.match(/### [Historical\/Expired Facts][\s\S]*?\n([\s\S]*?)(?=\n###|$)/)
    if (histSection) {
      const lines = histSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.historicalFacts = lines.map(l => {
        return l.replace(/^\d+\.\s*/, '').replace(/^"|"$/g, '').trim()
      }).filter(Boolean)
    }

    const entitySection = text.match(/### [Involved Entities]\n([\s\S]*?)(?=\n###|$)/)
    if (entitySection) {
      const lines = entitySection[1].split('\n').filter(l => l.trim().startsWith('-'))
      result.entities = lines.map(l => {
        const match = l.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
        if (match) return { name: match[1].trim(), type: match[2].trim() }
        return null
      }).filter(Boolean)
    }
  } catch (e) {
    console.warn('Parse panorama failed:', e)
  }

  return result
}

export function parseQuickSearch(text) {
  const result = {
    query: '',
    count: 0,
    facts: [],
    edges: [],
    nodes: []
  }

  try {
    const queryMatch = text.match(/Search Query:\s*(.+?)(?:\n|$)/)
    if (queryMatch) result.query = queryMatch[1].trim()

    const countMatch = text.match(/Found\s*(\d+)\s*results/)
    if (countMatch) result.count = parseInt(countMatch[1])

    const factsSection = text.match(/### Related Facts:\n([\s\S]*)\$/)
    if (factsSection) {
      const lines = factsSection[1].split('\n').filter(l => l.match(/^\d+\./))
      result.facts = lines.map(l => l.replace(/^\d+\.\s*/, '').trim()).filter(Boolean)
    }

    const edgesSection = text.match(/### Related Edges:\n([\s\S]*?)(?=\n###|$)/)
    if (edgesSection) {
      const lines = edgesSection[1].split('\n').filter(l => l.trim().startsWith('-'))
      result.edges = lines.map(l => {
        const match = l.match(/^-\s*(.+?)\s*--\[(.+?)\]-->\s*(.+)$/)
        if (match) {
          return { source: match[1].trim(), relation: match[2].trim(), target: match[3].trim() }
        }
        return null
      }).filter(Boolean)
    }

    const nodesSection = text.match(/### Related Nodes:\n([\s\S]*?)(?=\n###|$)/)
    if (nodesSection) {
      const lines = nodesSection[1].split('\n').filter(l => l.trim().startsWith('-'))
      result.nodes = lines.map(l => {
        const match = l.match(/^-\s*\*\*(.+?)\*\*\s*\((.+?)\)/)
        if (match) return { name: match[1].trim(), type: match[2].trim() }
        const simpleMatch = l.match(/^-\s*(.+)$/)
        if (simpleMatch) return { name: simpleMatch[1].trim(), type: '' }
        return null
      }).filter(Boolean)
    }
  } catch (e) {
    console.warn('Parse quick_search failed:', e)
  }

  return result
}
