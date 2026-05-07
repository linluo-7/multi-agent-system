// State
let activeSection = 'agents';
let selectedAgentId = 'supervisor';
let showConfigModal = false;
let configType = ''; // 'skill' | 'mcp'

const agents = [
  { id: 'supervisor', name: 'Supervisor', role: '总控', avatar: '🎯', status: 'online', tasks: 156, current: '任务协调中',
    skills: ['任务拆解', '流程编排', '结果整合', '路由分发'],
    tools: ['file_system', 'database', 'redis', 'llm_reflect'],
    config: { model: 'GPT-4o', temp: 0.7, maxTokens: 4096 }
  },
  { id: 'search', name: 'Search', role: '搜索', avatar: '🔍', status: 'online', tasks: 423, current: 'RAG检索中',
    skills: ['网络搜索', '网页抓取', '内容提取', 'RAG检索'],
    tools: ['web_search', 'web_fetch', 'milvus', 'neo4j'],
    config: { model: 'GPT-4o-mini', temp: 0.3, maxTokens: 2048 }
  },
  { id: 'code', name: 'Code', role: '编码', avatar: '💻', status: 'online', tasks: 287, current: '代码生成',
    skills: ['代码生成', '代码审查', '代码执行', '调试诊断'],
    tools: ['file_system', 'bash', 'git', 'evaluator'],
    config: { model: 'GPT-4o', temp: 0.2, maxTokens: 8192 }
  },
  { id: 'reasoning', name: 'Reasoning', role: '推理', avatar: '🧠', status: 'online', tasks: 198, current: '反思纠错',
    skills: ['逻辑推理', '反思纠错', '质量评估', '优化建议'],
    tools: ['llm_reflect', 'evaluator', 'milvus'],
    config: { model: 'GPT-4o', temp: 0.5, maxTokens: 4096 }
  },
  { id: 'doc', name: 'Doc', role: '文档', avatar: '📄', status: 'idle', tasks: 189, current: '待命',
    skills: ['文档生成', '格式转换', '摘要提取', '报告生成'],
    tools: ['file_system', 'markdown', 'pdf'],
    config: { model: 'GPT-4o-mini', temp: 0.4, maxTokens: 4096 }
  }
];

const mcpServers = [
  { id: 'filesystem', name: '文件系统', icon: '📁', desc: '读写文件、目录操作、权限管理', category: 'tools', enabled: true },
  { id: 'web_search', name: '网络搜索', icon: '🔍', desc: '搜索引擎、关键词检索', category: 'web', enabled: true },
  { id: 'web_fetch', name: '网页抓取', icon: '🌐', desc: '获取网页内容、解析HTML', category: 'web', enabled: true },
  { id: 'database', name: '数据库', icon: '🗄️', desc: 'PostgreSQL/MySQL查询操作', category: 'tools', enabled: true },
  { id: 'redis', name: 'Redis缓存', icon: '⚡', desc: '键值存储、消息队列、缓存', category: 'tools', enabled: true },
  { id: 'milvus', name: '向量检索', icon: '🔮', desc: 'Milvus向量相似度搜索', category: 'ai', enabled: true },
  { id: 'neo4j', name: '知识图谱', icon: '🕸️', desc: 'Neo4j图数据库查询', category: 'ai', enabled: true },
  { id: 'bash', name: '命令执行', icon: '⌨️', desc: 'Shell命令执行', category: 'tools', enabled: true },
  { id: 'git', name: 'Git操作', icon: '📦', desc: '版本控制操作', category: 'tools', enabled: false },
  { id: 'llm_reflect', name: 'LLM反思', icon: '🤖', desc: '大模型自我反思纠错', category: 'ai', enabled: true },
  { id: 'evaluator', name: '质量评估', icon: '✅', desc: '结果质量评估打分', category: 'ai', enabled: true },
  { id: 'markdown', name: 'Markdown', icon: '📝', desc: 'Markdown文档处理', category: 'doc', enabled: true },
  { id: 'pdf', name: 'PDF处理', icon: '📄', desc: 'PDF生成与解析', category: 'doc', enabled: false },
];

const skills = [
  { id: 'retrieval', name: '检索', icon: '🔍', skills: ['RAG检索', '向量搜索', '知识图谱', '混合检索'], enabled: true },
  { id: 'coding', name: '编码', icon: '💻', skills: ['代码生成', '代码审查', '代码执行', '调试诊断'], enabled: true },
  { id: 'reasoning', name: '推理', icon: '🧠', skills: ['逻辑推理', '反思纠错', '质量评估', '优化建议'], enabled: true },
  { id: 'tools', name: '工具', icon: '🔧', skills: ['文件操作', '网络请求', '数据库', '命令执行'], enabled: true },
  { id: 'doc', name: '文档', icon: '📄', skills: ['文档生成', '摘要提取', '格式转换', '报告生成'], enabled: true },
];

let currentChat = [
  {
    role: 'user',
    content: '帮我分析一下最近的销售数据，找出增长趋势'
  },
  {
    role: 'assistant',
    content: '好的，我来分析最近30天的销售数据。\n\n主要发现：\n1. 整体销售额较上月增长 23.5%\n2. 华东地区增速最快，达到 31.2%\n3. 周末销量环比增长 18.7%\n\n需要我进一步分析某个具体维度吗？',
    thinking: '用户想要分析销售数据。我需要：\n1. 调用RAG检索获取相关文档\n2. 分析数据中的关键指标\n3. 识别增长趋势\n4. 汇总成报告',
    tools: [
      { name: 'milvus', icon: '🔮', status: 'success', desc: '向量检索销售数据' },
      { name: 'neo4j', icon: '🕸️', status: 'success', desc: '查询知识图谱' },
      { name: 'llm_reflect', icon: '🤖', status: 'success', desc: '反思纠错' }
    ],
    sources: [
      { doc: '销售报表_2026_03.pdf', score: 96, snippet: '华东地区Q1销售额4.2亿，同比增长31.2%...' },
      { doc: '用户行为分析.xlsx', score: 89, snippet: '周末活跃用户环比增长18.7%，新客占比...' }
    ]
  }
];

// SVG Workflow
function createWorkflowSVG() {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'workflow-svg');
  svg.setAttribute('viewBox', '0 0 800 340');

  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');

  const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  marker.setAttribute('id', 'arrow');
  marker.setAttribute('markerWidth', '8');
  marker.setAttribute('markerHeight', '8');
  marker.setAttribute('refX', '6');
  marker.setAttribute('refY', '3');
  marker.setAttribute('orient', 'auto');
  const arrowPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  arrowPath.setAttribute('d', 'M0,0 L0,6 L8,3 z');
  arrowPath.setAttribute('fill', '#3f3f46');
  marker.appendChild(arrowPath);
  defs.appendChild(marker);

  const loopMarker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  loopMarker.setAttribute('id', 'arrow-loop');
  loopMarker.setAttribute('markerWidth', '8');
  loopMarker.setAttribute('markerHeight', '8');
  loopMarker.setAttribute('refX', '6');
  loopMarker.setAttribute('refY', '3');
  loopMarker.setAttribute('orient', 'auto');
  const loopPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  loopPath.setAttribute('d', 'M0,0 L0,6 L8,3 z');
  loopPath.setAttribute('fill', '#f59e0b');
  loopMarker.appendChild(loopPath);
  defs.appendChild(loopMarker);

  svg.appendChild(defs);

  const nodes = [
    { id: 'input', x: 30, y: 40, w: 70, h: 45, label: '输入', sub: 'User', type: 'entry' },
    { id: 'supervisor', x: 140, y: 25, w: 90, h: 75, label: 'Supervisor', sub: '状态机总控', type: 'supervisor' },
    { id: 'query', x: 280, y: 10, w: 75, h: 45, label: 'Query', sub: '意图理解', type: 'rag' },
    { id: 'embedding', x: 390, y: 10, w: 75, h: 45, label: 'Embedding', sub: '向量化', type: 'rag' },
    { id: 'vector', x: 500, y: 5, w: 80, h: 45, label: 'Vector', sub: 'Milvus', type: 'worker' },
    { id: 'kg', x: 500, y: 55, w: 80, h: 45, label: 'Knowledge', sub: 'Neo4j', type: 'worker' },
    { id: 'rrf', x: 620, y: 25, w: 65, h: 50, label: 'RRF', sub: '融合排序', type: 'rag' },
    { id: 'search', x: 280, y: 80, w: 70, h: 45, label: 'Search', sub: '搜索Agent', type: 'worker' },
    { id: 'code', x: 360, y: 80, w: 70, h: 45, label: 'Code', sub: '编码Agent', type: 'worker' },
    { id: 'reasoning', x: 440, y: 80, w: 70, h: 45, label: 'Reasoning', sub: '推理Agent', type: 'worker' },
    { id: 'memory', x: 520, y: 80, w: 65, h: 45, label: 'Memory', sub: '长短记忆', type: 'memory' },
    { id: 'checkpoint', x: 280, y: 160, w: 80, h: 40, label: 'Checkpointer', sub: '断点持久', type: 'memory' },
    { id: 'loop', x: 390, y: 155, w: 55, h: 50, label: 'Loop', sub: '反思迭代', type: 'loop' },
    { id: 'circuit', x: 480, y: 160, w: 80, h: 40, label: 'Circuit', sub: '熔断限流', type: 'safety' },
    { id: 'llm', x: 590, y: 160, w: 70, h: 40, label: 'LLM Core', sub: '反思纠错', type: 'supervisor' },
    { id: 'output', x: 280, y: 235, w: 65, h: 40, label: 'Output', sub: '结果聚合', type: 'entry' },
    { id: 'monitor', x: 380, y: 235, w: 65, h: 40, label: 'Monitor', sub: '监控告警', type: 'safety' },
    { id: 'response', x: 480, y: 235, w: 80, h: 40, label: 'Response', sub: '最终响应', type: 'entry' },
  ];

  const colors = {
    entry: { fill: '#1c1c1e', stroke: '#3f3f46' },
    supervisor: { fill: 'rgba(139, 92, 246, 0.15)', stroke: '#a855f7' },
    rag: { fill: 'rgba(34, 211, 238, 0.15)', stroke: '#22d3ee' },
    worker: { fill: 'rgba(59, 130, 246, 0.15)', stroke: '#3b82f6' },
    memory: { fill: 'rgba(245, 158, 11, 0.15)', stroke: '#f59e0b' },
    safety: { fill: 'rgba(239, 68, 68, 0.15)', stroke: '#ef4444' },
    loop: { fill: 'rgba(245, 158, 11, 0.2)', stroke: '#f59e0b' }
  };

  const icons = {
    entry: '📥', supervisor: '🎯', rag: '🔍', worker: '⚙️', memory: '💾', safety: '🛡️', loop: '🔄'
  };

  nodes.forEach(node => {
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    const c = colors[node.type];
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', node.x);
    rect.setAttribute('y', node.y);
    rect.setAttribute('width', node.w);
    rect.setAttribute('height', node.h);
    rect.setAttribute('fill', c.fill);
    rect.setAttribute('stroke', c.stroke);
    rect.setAttribute('rx', '4');
    g.appendChild(rect);

    const icon = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    icon.setAttribute('x', node.x + node.w/2);
    icon.setAttribute('y', node.y + 16);
    icon.setAttribute('text-anchor', 'middle');
    icon.setAttribute('font-size', '14px');
    icon.textContent = icons[node.type];
    g.appendChild(icon);

    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', node.x + node.w/2);
    label.setAttribute('y', node.y + 28);
    label.setAttribute('text-anchor', 'middle');
    label.setAttribute('font-size', '10px');
    label.setAttribute('fill', '#fafafa');
    label.textContent = node.label;
    g.appendChild(label);

    const sub = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    sub.setAttribute('x', node.x + node.w/2);
    sub.setAttribute('y', node.y + 40);
    sub.setAttribute('text-anchor', 'middle');
    sub.setAttribute('font-size', '8px');
    sub.setAttribute('fill', '#71717a');
    sub.textContent = node.sub;
    g.appendChild(sub);

    svg.appendChild(g);
  });

  const edges = [
    { from: 'input', to: 'supervisor' },
    { from: 'supervisor', to: 'query' },
    { from: 'supervisor', to: 'search' },
    { from: 'query', to: 'embedding' },
    { from: 'embedding', to: 'vector' },
    { from: 'embedding', to: 'kg' },
    { from: 'vector', to: 'rrf' },
    { from: 'kg', to: 'rrf' },
    { from: 'rrf', to: 'search' },
    { from: 'search', to: 'code' },
    { from: 'code', to: 'reasoning' },
    { from: 'reasoning', to: 'memory' },
    { from: 'memory', to: 'checkpoint' },
    { from: 'checkpoint', to: 'loop' },
    { from: 'loop', to: 'circuit' },
    { from: 'circuit', to: 'llm' },
    { from: 'llm', to: 'output' },
    { from: 'llm', to: 'loop', loop: true },
    { from: 'output', to: 'monitor' },
    { from: 'monitor', to: 'response' },
  ];

  const getCenter = (id) => {
    const n = nodes.find(x => x.id === id);
    return { x: n.x + n.w/2, y: n.y + n.h/2 };
  };

  edges.forEach(e => {
    const from = getCenter(e.from);
    const to = getCenter(e.to);
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');

    if (e.loop) {
      path.setAttribute('d', `M ${from.x},${from.y-20} Q ${from.x},${from.y-50} ${to.x+30},${from.y-50} T ${to.x},${to.y+20}`);
      path.setAttribute('stroke', '#f59e0b');
      path.setAttribute('stroke-dasharray', '4,3');
      path.setAttribute('marker-end', 'url(#arrow-loop)');
    } else {
      path.setAttribute('d', `M ${from.x},${from.y} L ${to.x},${to.y}`);
      path.setAttribute('marker-end', 'url(#arrow)');
    }

    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', '#3f3f46');
    path.setAttribute('stroke-width', '1.5');
    svg.appendChild(path);
  });

  // Legend
  const legend = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  legend.setAttribute('transform', 'translate(30, 290)');
  [
    { c: '#a855f7', l: 'Supervisor' },
    { c: '#22d3ee', l: 'RAG检索' },
    { c: '#3b82f6', l: 'Worker' },
    { c: '#f59e0b', l: 'Memory' },
    { c: '#ef4444', l: 'Safety' },
  ].forEach((item, i) => {
    const x = i * 130;
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x);
    rect.setAttribute('y', 0);
    rect.setAttribute('width', 10);
    rect.setAttribute('height', 10);
    rect.setAttribute('fill', item.c);
    rect.setAttribute('rx', '2');
    legend.appendChild(rect);
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', x + 14);
    text.setAttribute('y', 9);
    text.setAttribute('font-size', '10px');
    text.setAttribute('fill', '#71717a');
    text.textContent = item.l;
    legend.appendChild(text);
  });
  svg.appendChild(legend);

  return svg;
}

// Render
function render() {
  const root = document.getElementById('root');
  root.innerHTML = '';

  const app = document.createElement('div');
  app.className = 'app';

  app.appendChild(renderSidebar());
  app.appendChild(renderMain());

  if (showConfigModal) {
    app.appendChild(renderConfigModal());
  }

  root.appendChild(app);
}

function renderSidebar() {
  const sidebar = document.createElement('div');
  sidebar.className = 'sidebar';

  const sectionIcons = { agents: '◉', workflow: '🔄', skills: '🎯', mcp: '🔧', chat: '💬', rag: '📚', memory: '💾' };

  sidebar.innerHTML = `
    <div class="sidebar-header">
      <div class="logo">
        <div class="logo-icon">⚡</div>
        <div class="logo-text">
          Multi-Agent
          <small>协作系统</small>
        </div>
      </div>
    </div>
    <nav class="sidebar-nav">
      <div class="nav-section">
        <div class="nav-section-title">管理中心</div>
        <button class="nav-item ${activeSection === 'agents' ? 'active' : ''}" onclick="setSection('agents')">
          <span class="icon">${sectionIcons['agents']}</span>Agent管理
          <span class="count">${agents.length}</span>
        </button>
        <button class="nav-item ${activeSection === 'workflow' ? 'active' : ''}" onclick="setSection('workflow')">
          <span class="icon">${sectionIcons['workflow']}</span>工作流
        </button>
        <button class="nav-item ${activeSection === 'chat' ? 'active' : ''}" onclick="setSection('chat')">
          <span class="icon">${sectionIcons['chat']}</span>对话
        </button>
      </div>
      <div class="nav-section">
        <div class="nav-section-title">配置中心</div>
        <button class="nav-item ${activeSection === 'skills' ? 'active' : ''}" onclick="setSection('skills')">
          <span class="icon">${sectionIcons['skills']}</span>Skill配置
        </button>
        <button class="nav-item ${activeSection === 'mcp' ? 'active' : ''}" onclick="setSection('mcp')">
          <span class="icon">${sectionIcons['mcp']}</span>MCP工具
        </button>
      </div>
      <div class="nav-section">
        <div class="nav-section-title">知识管理</div>
        <button class="nav-item ${activeSection === 'rag' ? 'active' : ''}" onclick="setSection('rag')">
          <span class="icon">${sectionIcons['rag']}</span>RAG文档检索
        </button>
        <button class="nav-item ${activeSection === 'memory' ? 'active' : ''}" onclick="setSection('memory')">
          <span class="icon">${sectionIcons['memory']}</span>分层记忆
        </button>
      </div>
    </nav>
    <div class="sidebar-footer">
      <div class="agent-list-sidebar">
        <div class="nav-section-title" style="padding: 8px 12px;">在线Agent (${agents.filter(a => a.status === 'online').length})</div>
        ${agents.map(a => `
          <div class="agent-sidebar-item ${selectedAgentId === a.id ? 'active' : ''}" onclick="selectAgent('${a.id}')">
            <div class="agent-avatar-sm">${a.avatar}</div>
            <div class="agent-sidebar-info">
              <div class="agent-sidebar-name">${a.name}</div>
              <div class="agent-sidebar-status">
                <span class="status-dot-sm ${a.status}"></span>
                ${a.status === 'online' ? '运行中' : '空闲'}
              </div>
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;

  return sidebar;
}

function renderMain() {
  const main = document.createElement('div');
  main.className = 'main';
  main.appendChild(renderTopbar());
  main.appendChild(renderContent());
  return main;
}

function renderTopbar() {
  const titles = {
    dashboard: '仪表盘',
    workflow: '工作流编排',
    agents: 'Agent管理',
    chat: '智能对话',
    skills: 'Skill配置',
    mcp: 'MCP工具',
    rag: 'RAG文档检索',
    memory: '分层记忆'
  };

  const topbar = document.createElement('div');
  topbar.className = 'topbar';
  topbar.innerHTML = `
    <div class="topbar-title">${titles[activeSection]}</div>
    <div class="topbar-actions">
      <button class="btn" onclick="exportConfig()">📤 导出配置</button>
      <button class="btn" onclick="importConfig()">📥 导入配置</button>
      ${activeSection === 'skills' ? '<button class="btn btn-primary" onclick="openConfigModal(\'skill\')">+ 添加Skill</button>' : ''}
      ${activeSection === 'mcp' ? '<button class="btn btn-primary" onclick="openConfigModal(\'mcp\')">+ 添加MCP工具</button>' : ''}
    </div>
  `;
  return topbar;
}

function renderContent() {
  const content = document.createElement('div');
  content.className = 'content';

  switch (activeSection) {
    case 'agents': content.appendChild(renderAgentsView()); break;
    case 'workflow': content.appendChild(renderWorkflowView()); break;
    case 'chat': content.appendChild(renderChatView()); break;
    case 'skills': content.appendChild(renderSkillsView()); break;
    case 'mcp': content.appendChild(renderMCPView()); break;
    case 'rag': content.appendChild(renderRAGView()); break;
    case 'memory': content.appendChild(renderMemoryView()); break;
    default: content.appendChild(renderAgentsView());
  }

  return content;
}

function renderAgentsView() {
  const selected = agents.find(a => a.id === selectedAgentId) || agents[0];

  const div = document.createElement('div');
  div.className = 'agents-layout';

  // Left: Agent list
  const leftDiv = document.createElement('div');
  leftDiv.className = 'agents-list-panel';
  leftDiv.innerHTML = `
    <div class="card" style="margin-bottom: 0; height: 100%;">
      <div class="card-header">
        <div class="card-title"><span class="icon">◉</span>Agent列表</div>
        <span class="card-badge">${agents.length}个</span>
      </div>
      <div class="card-body" style="padding: 8px;">
        ${agents.map(a => `
          <div class="agent-list-item ${selectedAgentId === a.id ? 'active' : ''}" onclick="selectAgent('${a.id}')">
            <div class="agent-list-avatar">${a.avatar}</div>
            <div class="agent-list-info">
              <div class="agent-list-name">${a.name}</div>
              <div class="agent-list-role">${a.role}</div>
            </div>
            <span class="status-dot-sm ${a.status}"></span>
          </div>
        `).join('')}
      </div>
    </div>
  `;

  // Right: Agent detail
  const rightDiv = document.createElement('div');
  rightDiv.className = 'agent-detail-panel';
  rightDiv.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">${selected.avatar}</span>${selected.name}</div>
        <span class="card-badge ${selected.status}">${selected.status === 'online' ? '运行中' : '空闲'}</span>
      </div>
      <div class="card-body">
        <div class="agent-detail-grid">
          <div class="agent-detail-stats">
            <div class="stat-item">
              <div class="stat-label">总任务</div>
              <div class="stat-value">${selected.tasks}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">当前状态</div>
              <div class="stat-value">${selected.current}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">模型</div>
              <div class="stat-value">${selected.config.model}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">Temperature</div>
              <div class="stat-value">${selected.config.temp}</div>
            </div>
          </div>

          <div class="section-divider"></div>

          <div class="section">
            <div class="section-header">
              <span class="section-title">Skills</span>
              <button class="btn btn-sm" onclick="editAgentSkills('${selected.id}')">编辑</button>
            </div>
            <div class="skills-tags">
              ${selected.skills.map(s => `<span class="tag skill">${s}</span>`).join('')}
            </div>
          </div>

          <div class="section">
            <div class="section-header">
              <span class="section-title">MCP工具</span>
              <button class="btn btn-sm" onclick="editAgentTools('${selected.id}')">编辑</button>
            </div>
            <div class="skills-tags">
              ${selected.tools.map(t => {
                const server = mcpServers.find(m => m.id === t);
                return `<span class="tag tool">${server ? server.icon + ' ' + server.name : t}</span>`;
              }).join('')}
            </div>
          </div>

          <div class="section-divider"></div>

          <div class="section">
            <div class="section-header">
              <span class="section-title">模型配置</span>
            </div>
            <div class="config-grid">
              <div class="config-row">
                <span class="config-label">Model</span>
                <span class="config-value">${selected.config.model}</span>
              </div>
              <div class="config-row">
                <span class="config-label">Temperature</span>
                <span class="config-value">${selected.config.temp}</span>
              </div>
              <div class="config-row">
                <span class="config-label">Max Tokens</span>
                <span class="config-value">${selected.config.maxTokens}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  div.appendChild(leftDiv);
  div.appendChild(rightDiv);
  return div;
}

function renderWorkflowView() {
  const div = document.createElement('div');
  div.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🔄</span>LangGraph 状态机工作流</div>
        <div style="display: flex; gap: 8px;">
          <button class="btn">▶ 运行</button>
          <button class="btn">⏸ 暂停</button>
          <button class="btn">🔄 重置</button>
        </div>
      </div>
      <div class="card-body">
        <div class="workflow-container"></div>
      </div>
    </div>
  `;
  div.querySelector('.workflow-container').appendChild(createWorkflowSVG());
  return div;
}

function renderChatView() {
  const div = document.createElement('div');
  div.className = 'chat-layout';

  // Chat panel
  const chatPanel = document.createElement('div');
  chatPanel.className = 'chat-panel';
  chatPanel.innerHTML = `
    <div class="card" style="height: 100%; margin: 0;">
      <div class="card-header">
        <div class="card-title"><span class="icon">💬</span>智能对话</div>
        <div style="display: flex; gap: 8px;">
          <button class="btn btn-sm">🗑️ 清空</button>
          <button class="btn btn-sm">📋 导出</button>
        </div>
      </div>
      <div class="card-body" style="display: flex; flex-direction: column; padding: 0; height: calc(100% - 52px);">
        <div class="chat-messages">
          ${currentChat.map((msg, idx) => `
            <div class="chat-message ${msg.role}">
              <div class="chat-bubble">
                ${msg.content.replace(/\n/g, '<br>')}
                ${msg.thinking ? `
                  <div class="chat-thinking" onclick="toggleThinking(${idx})">
                    <div class="chat-thinking-header">
                      🧠 思考过程 <span>[点击展开]</span>
                    </div>
                    <div class="chat-thinking-content collapsed" id="thinking-${idx}">
                      ${msg.thinking.replace(/\n/g, '<br>')}
                    </div>
                  </div>
                ` : ''}
                ${msg.tools ? `
                  <div class="chat-tools">
                    <div class="chat-tools-header">🔧 工具调用</div>
                    ${msg.tools.map(t => `
                      <div class="chat-tool-item">
                        <span class="chat-tool-icon">${t.icon}</span>
                        <span class="chat-tool-name">${t.name}</span>
                        <span class="chat-tool-status ${t.status}">${t.status === 'success' ? '✓ 成功' : '⏳ 运行中'}</span>
                      </div>
                    `).join('')}
                  </div>
                ` : ''}
                ${msg.sources ? `
                  <div class="chat-source">
                    <div class="chat-source-title">🔗 RAG检索来源</div>
                    ${msg.sources.map(s => `
                      <div class="chat-source-item">
                        📄 ${s.doc} <span style="color: var(--success)">${s.score}%</span>
                        <br><small>${s.snippet}</small>
                      </div>
                    `).join('')}
                  </div>
                ` : ''}
              </div>
            </div>
          `).join('')}
        </div>
        <div class="chat-input-area">
          <input class="chat-input" type="text" placeholder="输入问题..." />
          <button class="chat-send">发送</button>
        </div>
      </div>
    </div>
  `;

  // Session panel
  const sessionPanel = document.createElement('div');
  sessionPanel.className = 'session-panel';
  sessionPanel.innerHTML = `
    <div class="card" style="height: 100%; margin: 0;">
      <div class="card-header">
        <div class="card-title"><span class="icon">📋</span>会话记录</div>
        <button class="btn btn-sm">+ 新建</button>
      </div>
      <div class="card-body">
        <div class="session-list">
          <div class="session-item active">
            <div class="session-title">销售数据分析</div>
            <div class="session-time">10:32</div>
          </div>
          <div class="session-item">
            <div class="session-title">竞品调研报告</div>
            <div class="session-time">昨天</div>
          </div>
          <div class="session-item">
            <div class="session-title">代码审查请求</div>
            <div class="session-time">3天前</div>
          </div>
        </div>
      </div>
    </div>
  `;

  div.appendChild(chatPanel);
  div.appendChild(sessionPanel);

  // Add event listeners
  setTimeout(() => {
    const input = div.querySelector('.chat-input');
    const sendBtn = div.querySelector('.chat-send');
    if (input && sendBtn) {
      const sendMessage = () => {
        if (!input.value.trim()) return;
        currentChat.push({ role: 'user', content: input.value });
        input.value = '';
        render();
      };
      sendBtn.onclick = sendMessage;
      input.onkeypress = (e) => { if (e.key === 'Enter') sendMessage(); };
    }
  }, 0);

  return div;
}

function renderSkillsView() {
  const div = document.createElement('div');
  div.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🎯</span>Skill配置</div>
      </div>
      <div class="card-body">
        <div class="skills-grid">
          ${skills.map(s => `
            <div class="skill-card ${!s.enabled ? 'disabled' : ''}">
              <div class="skill-card-header">
                <span class="skill-icon">${s.icon}</span>
                <span class="skill-name">${s.name}</span>
                <span class="skill-toggle ${s.enabled ? 'on' : ''}">${s.enabled ? '已启用' : '已禁用'}</span>
              </div>
              <div class="skill-items">
                ${s.skills.map(skill => `<span class="skill-item">${skill}</span>`).join('')}
              </div>
            </div>
          `).join('')}
        </div>
      </div>
    </div>
  `;
  return div;
}

function renderMCPView() {
  const div = document.createElement('div');

  const grouped = { tools: [], web: [], ai: [], doc: [] };
  mcpServers.forEach(s => {
    if (grouped[s.category]) grouped[s.category].push(s);
  });

  const categoryNames = { tools: '🔧 工具类', web: '🌐 网络类', ai: '🤖 AI类', doc: '📄 文档类' };

  div.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">🔧</span>MCP工具配置</div>
        <span class="card-badge">${mcpServers.filter(s => s.enabled).length}/${mcpServers.length} 已启用</span>
      </div>
      <div class="card-body">
        ${Object.entries(grouped).map(([cat, servers]) => `
          <div class="mcp-category">
            <div class="mcp-category-title">${categoryNames[cat] || cat}</div>
            <div class="mcp-grid">
              ${servers.map(s => `
                <div class="mcp-card ${!s.enabled ? 'disabled' : ''}">
                  <div class="mcp-card-header">
                    <span class="mcp-icon">${s.icon}</span>
                    <span class="mcp-name">${s.name}</span>
                    <span class="mcp-toggle ${s.enabled ? 'on' : ''}">${s.enabled ? '启用' : '禁用'}</span>
                  </div>
                  <div class="mcp-desc">${s.desc}</div>
                </div>
              `).join('')}
            </div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
  return div;
}

function renderRAGView() {
  const div = document.createElement('div');
  div.innerHTML = `
    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📚</span>双路混合RAG文档检索</div>
        <div style="display: flex; gap: 8px;">
          <button class="btn" onclick="loadRAGDocuments()">🔄 刷新文档</button>
          <button class="btn btn-primary" onclick="uploadRAGDocument()">+ 导入文档</button>
        </div>
      </div>
      <div class="card-body">
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px;">
          <div>
            <div class="section-title">检索查询</div>
            <div style="display: flex; gap: 8px;">
              <input class="chat-input" type="text" id="rag-query" placeholder="输入查询关键词..." style="flex: 1;" />
              <button class="btn btn-primary" onclick="searchRAG()">搜索</button>
            </div>
          </div>
          <div>
            <div class="section-title">融合策略</div>
            <select id="rag-fusion-method" style="padding: 10px 12px; background: var(--bg-tertiary); border: 1px solid var(--border); border-radius: 8px; color: var(--text-primary); width: 100%;">
              <option value="rrf">RRF 倒数排名融合</option>
              <option value="weighted">加权融合 (Vector 0.6 + KG 0.4)</option>
            </select>
          </div>
        </div>

        <div class="section-divider"></div>

        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
          <div>
            <div class="section-title">📊 Milvus 向量检索</div>
            <div id="vector-results" style="color: var(--text-secondary); font-size: 11px;">
              输入查询后显示向量检索结果...
            </div>
          </div>
          <div>
            <div class="section-title">🕸️ Neo4j 知识图谱</div>
            <div id="kg-results" style="color: var(--text-secondary); font-size: 11px;">
              输入查询后显示图谱检索结果...
            </div>
          </div>
        </div>

        <div class="section-divider"></div>

        <div>
          <div class="section-title">📋 检索结果（融合排序）</div>
          <div id="rag-results" style="color: var(--text-secondary); font-size: 13px;">
            请输入查询关键词进行搜索...
          </div>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <div class="card-title"><span class="icon">📁</span>知识库文档</div>
        <span class="card-badge" id="doc-count">0 个文档</span>
      </div>
      <div class="card-body">
        <div class="upload-zone" onclick="triggerDocUpload()" style="margin-bottom: 16px;">
          <div style="font-size: 28px; margin-bottom: 8px;">📤</div>
          <div style="font-weight: 500;">点击上传文档 (PDF/Word/TXT/MD)</div>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">支持批量导入，自动解析清洗和向量化</div>
        </div>
        <input type="file" id="doc-upload-input" style="display: none;" multiple accept=".pdf,.docx,.doc,.txt,.md" onchange="handleDocUpload(event)" />
        <div id="doc-list" style="color: var(--text-secondary); font-size: 12px;">
          暂无文档，请点击上方区域导入...
        </div>
      </div>
    </div>
  `;
  return div;
}

function renderMemoryView() {
  const div = document.createElement('div');
  div.innerHTML = `
    <div style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-bottom: 16px;">
      <div class="stat-card">
        <div class="stat-label">🧠 技能模板</div>
        <div class="stat-value" id="mem-skills">--</div>
        <div class="stat-change up">自动生成 + 迭代优化</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">⚡ 活跃技能</div>
        <div class="stat-value" id="mem-active">--</div>
        <div class="stat-change up">成功率 > 60%</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">📊 技能评估</div>
        <div class="stat-value" id="mem-evals">--</div>
        <div class="stat-change up">累计评估次数</div>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🎯</span>三层记忆架构</div>
        </div>
        <div class="card-body">
          <div style="display: flex; flex-direction: column; gap: 12px;">
            <div style="padding: 14px; background: var(--bg-tertiary); border-left: 3px solid var(--success); border-radius: 6px;">
              <div style="font-weight: 600; margin-bottom: 6px;">🟢 会话记忆 <small style="color: var(--text-muted);">Redis</small></div>
              <div style="font-size: 11px; color: var(--text-secondary);">存储会话临时上下文与任务状态，TTL: 3600s</div>
              <div style="font-size: 10px; color: var(--text-muted); margin-top: 4px;">对话历史 · Agent状态 · 实时黑板</div>
            </div>
            <div style="padding: 14px; background: var(--bg-tertiary); border-left: 3px solid var(--accent); border-radius: 6px;">
              <div style="font-weight: 600; margin-bottom: 6px;">🔵 技能记忆 <small style="color: var(--text-muted);">PostgreSQL</small></div>
              <div style="font-size: 11px; color: var(--text-secondary);">标准化工具调用、问答解析等可复用技能模板</div>
              <div style="font-size: 10px; color: var(--text-muted); margin-top: 4px;">Skill模板 · 输入Schema · 成功率追踪</div>
            </div>
            <div style="padding: 14px; background: var(--bg-tertiary); border-left: 3px solid var(--purple); border-radius: 6px;">
              <div style="font-weight: 600; margin-bottom: 6px;">🟣 长期记忆 <small style="color: var(--text-muted);">Milvus + Neo4j</small></div>
              <div style="font-size: 11px; color: var(--text-secondary);">向量数据库存储全局业务知识，图数据库存储历史任务关系</div>
              <div style="font-size: 10px; color: var(--text-muted); margin-top: 4px;">语义检索 · 实体关联 · 经验沉淀</div>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <div class="card-title"><span class="icon">🔄</span>技能自进化流程</div>
        </div>
        <div class="card-body">
          <div style="display: flex; flex-direction: column; gap: 10px;">
            <div style="display: flex; align-items: center; gap: 10px;">
              <span style="width: 28px; height: 28px; background: var(--accent-light); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 12px;">1</span>
              <div style="font-size: 12px;">记录任务执行 → 分析高频模式</div>
            </div>
            <div style="margin-left: 24px; width: 2px; height: 16px; background: var(--border);"></div>
            <div style="display: flex; align-items: center; gap: 10px;">
              <span style="width: 28px; height: 28px; background: var(--accent-light); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 12px;">2</span>
              <div style="font-size: 12px;">自动封装 → 生成Skill模板</div>
            </div>
            <div style="margin-left: 24px; width: 2px; height: 16px; background: var(--border);"></div>
            <div style="display: flex; align-items: center; gap: 10px;">
              <span style="width: 28px; height: 28px; background: var(--accent-light); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 12px;">3</span>
              <div style="font-size: 12px;">评估链路 → 追踪成功率</div>
            </div>
            <div style="margin-left: 24px; width: 2px; height: 16px; background: var(--border);"></div>
            <div style="display: flex; align-items: center; gap: 10px;">
              <span style="width: 28px; height: 28px; background: var(--accent-light); border-radius: 14px; display: flex; align-items: center; justify-content: center; font-size: 12px;">4</span>
              <div style="font-size: 12px;">迭代优化 / 冗余淘汰</div>
            </div>
          </div>
          <div class="section-divider" style="margin: 16px 0;"></div>
          <div style="font-size: 12px; color: var(--text-muted);">
            阈值配置：高频触发 ≥ 3次 | 合格成功率 ≥ 60% | 最大技能数 100
          </div>
        </div>
      </div>
    </div>

    <div class="card" style="margin-top: 16px;">
      <div class="card-header">
        <div class="card-title"><span class="icon">📋</span>技能模板列表</div>
        <button class="btn btn-sm" onclick="refreshSkillList()">🔄 刷新</button>
      </div>
      <div class="card-body" id="skill-list-container">
        <div style="color: var(--text-muted); font-size: 12px;">加载中...</div>
      </div>
    </div>
  `;

  setTimeout(() => {
    loadMemoryStats();
    refreshSkillList();
  }, 100);

  return div;
}

// RAG API调用
let ragDocuments = [];

window.loadRAGDocuments = async function() {
  try {
    const res = await fetch('/api/v1/rag/documents');
    if (res.ok) {
      const data = await res.json();
      ragDocuments = data.documents || [];
      renderDocList();
      document.getElementById('doc-count').textContent = ragDocuments.length + ' 个文档';
    }
  } catch (e) {
    console.log('RAG documents endpoint not available yet');
  }
};

window.searchRAG = async function() {
  const query = document.getElementById('rag-query')?.value || '';
  const method = document.getElementById('rag-fusion-method')?.value || 'rrf';
  if (!query.trim()) return;

  const resultsDiv = document.getElementById('rag-results');
  const vectorDiv = document.getElementById('vector-results');
  const kgDiv = document.getElementById('kg-results');

  try {
    const res = await fetch('/api/v1/rag/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, fusion_method: method, top_k: 5 })
    });

    if (res.ok) {
      const data = await res.json();
      resultsDiv.innerHTML = data.results?.length
        ? data.results.map((r, i) => `
            <div class="chat-source-item" style="margin-bottom: 8px;">
              <strong>[${i + 1}]</strong> ${r.source}
              <span style="color: var(--success); float: right;">${(r.score * 100).toFixed(1)}%</span>
              <br><small>${(r.text || '').substring(0, 150)}...</small>
            </div>`).join('')
        : '未找到相关文档';

      if (data.sources) {
        vectorDiv.innerHTML = data.sources.filter(s => s.source === 'vector').length
          ? data.sources.filter(s => s.source === 'vector').map(s => `<div style="margin-bottom:4px;">📄 ${s.preview} (${(s.score * 100).toFixed(1)}%)</div>`).join('')
          : '无向量检索结果';
        kgDiv.innerHTML = data.sources.filter(s => s.source === 'knowledge_graph').length
          ? data.sources.filter(s => s.source === 'knowledge_graph').map(s => `<div style="margin-bottom:4px;">🕸️ ${s.preview} (${(s.score * 100).toFixed(1)}%)</div>`).join('')
          : '无图谱检索结果';
      }
    } else {
      resultsDiv.innerHTML = '检索失败，RAG服务未就绪';
    }
  } catch (e) {
    resultsDiv.innerHTML = 'RAG服务未连接，请确认后端已启动';
    vectorDiv.innerHTML = '等待服务...';
    kgDiv.innerHTML = '等待服务...';
  }
};

window.uploadRAGDocument = function() {
  document.getElementById('doc-upload-input')?.click();
};

window.triggerDocUpload = function() {
  document.getElementById('doc-upload-input')?.click();
};

window.handleDocUpload = async function(event) {
  const files = event.target.files;
  if (!files.length) return;

  const docList = document.getElementById('doc-list');
  docList.innerHTML = '文档处理中...';

  for (const file of files) {
    const formData = new FormData();
    formData.append('file', file);
    try {
      await fetch('/api/v1/rag/documents/import', { method: 'POST', body: formData });
    } catch (e) {
      console.log('Document import endpoint not available');
    }
  }

  await loadRAGDocuments();
};

function renderDocList() {
  const container = document.getElementById('doc-list');
  if (!container) return;
  if (!ragDocuments.length) {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px;">暂无文档，请点击上方区域导入...</div>';
    return;
  }
  container.innerHTML = ragDocuments.map(d => `
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 12px; background: var(--bg-tertiary); border-radius: 6px; margin-bottom: 8px;">
      <div>
        <span style="font-weight: 500;">📄 ${d.filename || d.id}</span>
        <span style="font-size: 10px; color: var(--text-muted); margin-left: 8px;">${d.file_type || ''} · ${d.chunk_count || 0} chunks</span>
      </div>
      <div>
        <span style="font-size: 10px; color: var(--text-muted);">${new Date(d.created_at || Date.now()).toLocaleDateString()}</span>
      </div>
    </div>
  `).join('');
}

// Memory API调用
window.loadMemoryStats = async function() {
  try {
    const res = await fetch('/api/v1/memory/skills/stats');
    if (res.ok) {
      const data = await res.json();
      document.getElementById('mem-skills').textContent = data.total_skills || '0';
      document.getElementById('mem-active').textContent = data.active_skills || '0';
      document.getElementById('mem-evals').textContent = data.total_evaluations || '0';
    }
  } catch (e) {
    document.getElementById('mem-skills').textContent = '--';
    document.getElementById('mem-active').textContent = '--';
    document.getElementById('mem-evals').textContent = '--';
  }
};

window.refreshSkillList = async function() {
  const container = document.getElementById('skill-list-container');
  if (!container) return;

  try {
    const res = await fetch('/api/v1/memory/skills');
    if (res.ok) {
      const data = await res.json();
      const skills = data.skills || [];
      if (!skills.length) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px;">暂无技能模板（系统将自动从高频任务中生成）</div>';
        return;
      }
      container.innerHTML = skills.map(s => `
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px; background: var(--bg-tertiary); border-radius: 6px; margin-bottom: 8px;">
          <div style="flex: 1;">
            <div style="font-weight: 500; margin-bottom: 4px;">${s.name}</div>
            <div style="font-size: 11px; color: var(--text-secondary);">${s.description || ''}</div>
            <div style="margin-top: 6px; display: flex; gap: 6px;">
              <span class="tag">${s.task_type}</span>
              <span class="tag tool">使用 ${s.usage_count || 0} 次</span>
            </div>
          </div>
          <div style="text-align: right;">
            <div style="font-size: 18px; font-weight: 600; color: ${(s.success_rate || 0) >= 0.6 ? 'var(--success)' : 'var(--warning)'}">
              ${((s.success_rate || 0) * 100).toFixed(0)}%
            </div>
            <div style="font-size: 10px; color: var(--text-muted);">成功率</div>
          </div>
        </div>
      `).join('');
    }
  } catch (e) {
    container.innerHTML = '<div style="color: var(--text-muted); font-size: 12px;">技能管理服务未连接</div>';
  }
};

function renderConfigModal() {
  const modal = document.createElement('div');
  modal.className = 'modal-overlay';
  modal.onclick = (e) => { if (e.target === modal) closeConfigModal(); };

  let title = '';
  let content = '';

  if (configType === 'skill') {
    title = '导入Skill配置';
    content = `
      <div class="modal-body">
        <p style="color: var(--text-secondary); margin-bottom: 16px;">支持导入JSON格式的Skill配置文件，可自定义技能分类和能力范围。</p>
        <div class="upload-zone">
          <div style="font-size: 32px; margin-bottom: 12px;">📁</div>
          <div style="font-weight: 500;">点击上传或拖拽文件到此处</div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">支持 .json 格式</div>
        </div>
        <div style="margin-top: 16px;">
          <label style="font-size: 12px; color: var(--text-muted);">或粘贴JSON内容：</label>
          <textarea class="config-textarea" placeholder='{"skills": [{"name": "自定义技能", ...}]}'></textarea>
        </div>
      </div>
    `;
  } else if (configType === 'mcp') {
    title = '导入MCP工具配置';
    content = `
      <div class="modal-body">
        <p style="color: var(--text-secondary); margin-bottom: 16px;">支持导入MCP Server配置文件，添加自定义工具能力。</p>
        <div class="upload-zone">
          <div style="font-size: 32px; margin-bottom: 12px;">📁</div>
          <div style="font-weight: 500;">点击上传或拖拽文件到此处</div>
          <div style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">支持 .json 格式</div>
        </div>
        <div style="margin-top: 16px;">
          <label style="font-size: 12px; color: var(--text-muted);">或粘贴JSON内容：</label>
          <textarea class="config-textarea" placeholder='{"mcpServers": [{"name": "custom_server", ...}]}'></textarea>
        </div>
      </div>
    `;
  }

  modal.innerHTML = `
    <div class="modal">
      <div class="modal-header">
        <div class="modal-title">${title}</div>
        <button class="modal-close" onclick="closeConfigModal()">×</button>
      </div>
      ${content}
      <div class="modal-footer">
        <button class="btn" onclick="closeConfigModal()">取消</button>
        <button class="btn btn-primary" onclick="saveConfig()">确认导入</button>
      </div>
    </div>
  `;

  return modal;
}

// Global handlers
window.setSection = (section) => { activeSection = section; render(); };
window.selectAgent = (id) => { selectedAgentId = id; render(); };
window.toggleThinking = (idx) => {
  const content = document.getElementById(`thinking-${idx}`);
  if (content) content.classList.toggle('collapsed');
};
window.openConfigModal = (type) => { configType = type; showConfigModal = true; render(); };
window.closeConfigModal = () => { showConfigModal = false; render(); };
window.saveConfig = () => { alert('配置导入成功！'); closeConfigModal(); };
window.exportConfig = () => {
  const config = activeSection === 'skills' ? skills : mcpServers;
  const blob = new Blob([JSON.stringify(config, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `${activeSection}_config.json`;
  a.click();
  URL.revokeObjectURL(url);
};
window.importConfig = () => {
  const input = document.createElement('input');
  input.type = 'file';
  input.accept = '.json';
  input.onchange = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          JSON.parse(e.target.result);
          alert('配置导入成功！');
        } catch {
          alert('JSON格式错误！');
        }
      };
      reader.readAsText(file);
    }
  };
  input.click();
};
window.editAgentSkills = (id) => { alert('打开Skill编辑面板'); };
window.editAgentTools = (id) => { alert('打开MCP工具编辑面板'); };

// Init
render();
