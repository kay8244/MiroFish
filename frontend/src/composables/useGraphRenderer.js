import * as d3 from 'd3'

const NODE_COLORS = ['#FF6B35', '#004E89', '#7B2D8E', '#1A936F', '#C5283D', '#E9724C', '#2D3436', '#6C5CE7']

export function useGraphRenderer({
  graphSvg,
  graphData,
  graphContainer,
  onSelectNode,
  onSelectEdge,
  onCloseDetail,
}) {
  const renderGraph = () => {
    if (!graphSvg.value || !graphData.value) {
      console.log('Cannot render: svg or data missing')
      return
    }

    const container = graphContainer.value
    if (!container) {
      console.log('Cannot render: container missing')
      return
    }

    const rect = container.getBoundingClientRect()
    const width = rect.width || 800
    const height = (rect.height || 600) - 60

    if (width <= 0 || height <= 0) {
      console.log('Cannot render: invalid dimensions', width, height)
      return
    }

    console.log('Rendering graph:', width, 'x', height)

    const svg = d3.select(graphSvg.value)
      .attr('width', width)
      .attr('height', height)
      .attr('viewBox', `0 0 ${width} ${height}`)

    svg.selectAll('*').remove()

    const nodesData = graphData.value.nodes || []
    const edgesData = graphData.value.edges || []

    if (nodesData.length === 0) {
      console.log('No nodes to render')
      svg.append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#999')
        .text('Waiting for graph data...')
      return
    }

    const nodeMap = {}
    nodesData.forEach(n => {
      nodeMap[n.uuid] = n
    })

    const nodes = nodesData.map(n => ({
      id: n.uuid,
      name: n.name || 'Unnamed',
      type: n.labels?.find(l => l !== 'Entity' && l !== 'Node') || 'Entity',
      rawData: n
    }))

    const nodeIds = new Set(nodes.map(n => n.id))

    const edges = edgesData
      .filter(e => nodeIds.has(e.source_node_uuid) && nodeIds.has(e.target_node_uuid))
      .map(e => ({
        source: e.source_node_uuid,
        target: e.target_node_uuid,
        type: e.fact_type || e.name || 'RELATED_TO',
        rawData: {
          ...e,
          source_name: nodeMap[e.source_node_uuid]?.name || 'Unknown',
          target_name: nodeMap[e.target_node_uuid]?.name || 'Unknown'
        }
      }))

    console.log('Nodes:', nodes.length, 'Edges:', edges.length)

    const types = [...new Set(nodes.map(n => n.type))]
    const colorScale = d3.scaleOrdinal()
      .domain(types)
      .range(NODE_COLORS)

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id).distance(100).strength(0.5))
      .force('charge', d3.forceManyBody().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(40))
      .force('x', d3.forceX(width / 2).strength(0.05))
      .force('y', d3.forceY(height / 2).strength(0.05))

    const g = svg.append('g')

    svg.call(d3.zoom()
      .extent([[0, 0], [width, height]])
      .scaleExtent([0.2, 4])
      .on('zoom', (event) => {
        g.attr('transform', event.transform)
      }))

    const linkGroup = g.append('g')
      .attr('class', 'links')
      .selectAll('g')
      .data(edges)
      .enter()
      .append('g')
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation()
        onSelectEdge?.(d.rawData)
      })

    linkGroup.append('line')
      .attr('stroke', '#ccc')
      .attr('stroke-width', 1.5)
      .attr('stroke-opacity', 0.6)

    linkGroup.append('line')
      .attr('stroke', 'transparent')
      .attr('stroke-width', 10)

    const linkLabel = g.append('g')
      .attr('class', 'link-labels')
      .selectAll('text')
      .data(edges)
      .enter()
      .append('text')
      .attr('font-size', '9px')
      .attr('fill', '#999')
      .attr('text-anchor', 'middle')
      .text(d => d.type.length > 15 ? d.type.substring(0, 12) + '...' : d.type)

    const node = g.append('g')
      .attr('class', 'nodes')
      .selectAll('g')
      .data(nodes)
      .enter()
      .append('g')
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation()
        onSelectNode?.(d.rawData, colorScale(d.type))
      })
      .call(d3.drag()
        .on('start', dragstarted)
        .on('drag', dragged)
        .on('end', dragended))

    node.append('circle')
      .attr('r', 10)
      .attr('fill', d => colorScale(d.type))
      .attr('stroke', '#fff')
      .attr('stroke-width', 2)
      .attr('class', 'node-circle')

    node.append('text')
      .attr('dx', 14)
      .attr('dy', 4)
      .text(d => d.name?.substring(0, 12) || '')
      .attr('font-size', '11px')
      .attr('fill', '#333')
      .attr('font-family', 'JetBrains Mono, monospace')

    svg.on('click', () => {
      onCloseDetail?.()
    })

    simulation.on('tick', () => {
      linkGroup.selectAll('line')
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y)

      linkLabel
        .attr('x', d => (d.source.x + d.target.x) / 2)
        .attr('y', d => (d.source.y + d.target.y) / 2 - 5)

      node.attr('transform', d => `translate(${d.x},${d.y})`)
    })

    function dragstarted(event) {
      if (!event.active) simulation.alphaTarget(0.3).restart()
      event.subject.fx = event.subject.x
      event.subject.fy = event.subject.y
    }

    function dragged(event) {
      event.subject.fx = event.x
      event.subject.fy = event.y
    }

    function dragended(event) {
      if (!event.active) simulation.alphaTarget(0)
      event.subject.fx = null
      event.subject.fy = null
    }
  }

  return { renderGraph }
}
