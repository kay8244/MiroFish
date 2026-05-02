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

export function parseInterview(text) {
  const result = {
    topic: '',
    agentCount: '',
    successCount: 0,
    totalCount: 0,
    selectionReason: '',
    interviews: [],
    summary: ''
  }

  try {
    const topicMatch = text.match(/\*\*Interview Topic:\*\*\s*(.+?)(?:\n|$)/)
    if (topicMatch) result.topic = topicMatch[1].trim()

    const countMatch = text.match(/\*\*Interviewed:\*\*\s*(\d+)\s*\/\s*(\d+)/)
    if (countMatch) {
      result.successCount = parseInt(countMatch[1])
      result.totalCount = parseInt(countMatch[2])
      result.agentCount = `${countMatch[1]} / ${countMatch[2]}`
    }

    const reasonMatch = text.match(/### Selection Reason for Interviewees\n([\s\S]*?)(?=\n---\n|\n### Interview Records)/)
    if (reasonMatch) {
      result.selectionReason = reasonMatch[1].trim()
    }

    const parseIndividualReasons = (reasonText) => {
      const reasons = {}
      if (!reasonText) return reasons

      const lines = reasonText.split(/\n+/)
      let currentName = null
      let currentReason = []

      for (const line of lines) {
        let headerMatch = null
        let name = null
        let reasonStart = null

        headerMatch = line.match(/^\d+\.\s*\*\*([^*（(]+)(?:[（(]index\s*=?\s*\d+[)）])?\*\*[：:]\s*(.*)/)
        if (headerMatch) {
          name = headerMatch[1].trim()
          reasonStart = headerMatch[2]
        }

        if (!headerMatch) {
          headerMatch = line.match(/^-\s*(?:选择|Select)([^（(]+)(?:[（(]index\s*=?\s*\d+[)）])?[：:]\s*(.*)/)
          if (headerMatch) {
            name = headerMatch[1].trim()
            reasonStart = headerMatch[2]
          }
        }

        if (!headerMatch) {
          headerMatch = line.match(/^-\s*\*\*([^*（(]+)(?:[（(]index\s*=?\s*\d+[)）])?\*\*[：:]\s*(.*)/)
          if (headerMatch) {
            name = headerMatch[1].trim()
            reasonStart = headerMatch[2]
          }
        }

        if (name) {
          if (currentName && currentReason.length > 0) {
            reasons[currentName] = currentReason.join(' ').trim()
          }
          currentName = name
          currentReason = reasonStart ? [reasonStart.trim()] : []
        } else if (currentName && line.trim() && !line.match(/^未选|^综上|^最终选择|^Not selected|^In summary|^Final selection/)) {
          currentReason.push(line.trim())
        }
      }

      if (currentName && currentReason.length > 0) {
        reasons[currentName] = currentReason.join(' ').trim()
      }

      return reasons
    }

    const individualReasons = parseIndividualReasons(result.selectionReason)

    const interviewBlocks = text.split(/#### Interview #\d+:/).slice(1)

    interviewBlocks.forEach((block, index) => {
      const interview = {
        num: index + 1,
        title: '',
        name: '',
        role: '',
        bio: '',
        selectionReason: '',
        questions: [],
        twitterAnswer: '',
        redditAnswer: '',
        quotes: []
      }

      const titleMatch = block.match(/^(.+?)\n/)
      if (titleMatch) interview.title = titleMatch[1].trim()

      const nameRoleMatch = block.match(/\*\*(.+?)\*\*\s*\((.+?)\)/)
      if (nameRoleMatch) {
        interview.name = nameRoleMatch[1].trim()
        interview.role = nameRoleMatch[2].trim()
        interview.selectionReason = individualReasons[interview.name] || ''
      }

      const bioMatch = block.match(/_(?:简介|Bio):\s*([\s\S]*?)_\n/)
      if (bioMatch) {
        interview.bio = bioMatch[1].trim().replace(/\.\.\.$/, '...')
      }

      const qMatch = block.match(/\*\*Q:\*\*\s*([\s\S]*?)(?=\n\n\*\*A:\*\*|\*\*A:\*\*)/)
      if (qMatch) {
        const qText = qMatch[1].trim()
        const questions = qText.split(/\n\d+\.\s+/).filter(q => q.trim())
        if (questions.length > 0) {
          const firstQ = qText.match(/^1\.\s+(.+)/)
          if (firstQ) {
            interview.questions = [firstQ[1].trim(), ...questions.slice(1).map(q => q.trim())]
          } else {
            interview.questions = questions.map(q => q.trim())
          }
        }
      }

      const answerMatch = block.match(/\*\*A:\*\*\s*([\s\S]*?)(?=\*\*(?:关键引言|Key Quotes)|$)/)
      if (answerMatch) {
        const answerText = answerMatch[1].trim()

        const twitterMatch = answerText.match(/[Twitter Platform Answer]\n?([\s\S]*?)(?=[Reddit Platform Answer]|$)/)
        const redditMatch = answerText.match(/[Reddit Platform Answer]\n?([\s\S]*?)$/)

        if (twitterMatch) {
          interview.twitterAnswer = twitterMatch[1].trim()
        }
        if (redditMatch) {
          interview.redditAnswer = redditMatch[1].trim()
        }

        if (!twitterMatch && redditMatch) {
          if (interview.redditAnswer && interview.redditAnswer !== '(No reply from this platform)') {
            interview.twitterAnswer = interview.redditAnswer
          }
        } else if (twitterMatch && !redditMatch) {
          if (interview.twitterAnswer && interview.twitterAnswer !== '(No reply from this platform)') {
            interview.redditAnswer = interview.twitterAnswer
          }
        } else if (!twitterMatch && !redditMatch) {
          interview.twitterAnswer = answerText
        }
      }

      const quotesMatch = block.match(/\*\*Key Quotes:\*\*\n([\s\S]*?)(?=\n---|\n####|$)/)
      if (quotesMatch) {
        const quotesText = quotesMatch[1]
        let quoteMatches = quotesText.match(/> "([^"]+)"/g)
        if (!quoteMatches) {
          quoteMatches = quotesText.match(/> [“""]([^”""]+)[”""]/g)
        }
        if (quoteMatches) {
          interview.quotes = quoteMatches
            .map(q => q.replace(/^> [“""]|[”""]$/g, '').trim())
            .filter(q => q)
        }
      }

      if (interview.name || interview.title) {
        result.interviews.push(interview)
      }
    })

    const summaryMatch = text.match(/### Interview Summary and Core Viewpoints\n([\s\S]*?)$/)
    if (summaryMatch) {
      result.summary = summaryMatch[1].trim()
    }
  } catch (e) {
    console.warn('Parse interview failed:', e)
  }

  return result
}
