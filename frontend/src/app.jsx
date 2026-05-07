// Mock data for demo
const mockData = {
  stats: {
    totalTasks: 2847,
    activeAgents: 5,
    successRate: 98.2,
    avgResponseTime: '1.2s'
  },
  agents: [
    { name: 'Supervisor', role: '总控', avatar: '🎯', status: 'online', tasks: 156, current: '任务协调中' },
    { name: 'Search', role: '搜索', avatar: '🔍', status: 'online', tasks: 423, current: '信息检索' },
    { name: 'Code', role: '编码', avatar: '💻', status: 'online', tasks: 287, current: '代码生成' },
    { name: 'Doc', role: '文档', avatar: '📄', status: 'idle', tasks: 189, current: '待命' },
    { name: 'Data', role: '数据', avatar: '📊', status: 'online', tasks: 312, current: '分析处理' }
  ],
  recentTasks: [
    { time: '10:32', title: '任务 #2847', desc: '分析销售数据并生成报告', status: 'completed' },
    { time: '10:28', title: '任务 #2846', desc: '搜索竞品信息完成', status: 'completed' },
    { time: '10:25', title: '任务 #2845', desc: '代码审查与优化建议', status: 'running' },
    { time: '10:20', title: '任务 #2844', desc: '生成API接口文档', status: 'completed' }
  ],
  metrics: {
    cpu: 34,
    memory: 67,
    tasksToday: 127,
    uptime: 99.9
  }
};

const messages = [
  { role: 'user', content: '帮我分析一下最近的销售数据，找出增长趋势' },
  { role: 'assistant', content: '好的，我来分析最近30天的销售数据。\n\n**主要发现：**\n1. 整体销售额较上月增长 **23.5%**\n2. 华东地区增速最快，达到 **31.2%**\n3. 周末销量环比增长 **18.7%**\n\n需要我进一步分析某个具体维度吗？' },
  { role: 'user', content: '华东地区的增长原因是什么？' },
  { role: 'assistant', content: '根据数据分析，华东地区增长主要原因：\n\n**1. 渠道拓展**\n- 新增3个分销商，贡献15%增量\n- 线上渠道覆盖率提升至78%\n\n**2. 促销活动**\n- 618大促期间GMV峰值达2300万\n- 会员复购率提升至45%\n\n**3. 产品结构**\n- 高客单价产品占比增加12%\n\n是否需要生成详细报告？' }
];

// Components
function Sidebar({ activeTab, setActiveTab }) {
  const navItems = [
    { id: 'dashboard', icon: '◈', label: '仪表盘' },
    { id: 'agents', icon: '◉', label: 'Agent状态' },
    { id: 'workflow', icon: '◎', label: '工作流' },
    { id: 'tasks', icon: '◇', label: '任务记录' },
    { id: 'chat', icon: '○', label: '对话' },
  ];

  return (
    <div className="sidebar">
      <div className="logo">
        <h1>Multi-Agent</h1>
        <span>协作系统 v2.0</span>
      </div>
      {navItems.map(item => (
        <button
          key={item.id}
          className={`nav-item ${activeTab === item.id ? 'active' : ''}`}
          onClick={() => setActiveTab(item.id)}
        >
          <span className="icon">{item.icon}</span>
          {item.label}
        </button>
      ))}
    </div>
  );
}

function Dashboard() {
  return (
    <>
      <div className="dashboard-grid">
        <div className="stat-card">
          <div className="label">总任务数</div>
          <div className="value">{mockData.stats.totalTasks.toLocaleString()}</div>
          <div className="change positive">↑ 12.5% 较上周</div>
        </div>
        <div className="stat-card">
          <div className="label">活跃Agent</div>
          <div className="value">{mockData.stats.activeAgents}</div>
          <div className="change positive">全部在线</div>
        </div>
        <div className="stat-card">
          <div className="label">成功率</div>
          <div className="value">{mockData.stats.successRate}%</div>
          <div className="change positive">↑ 0.3%</div>
        </div>
        <div className="stat-card">
          <div className="label">平均响应</div>
          <div className="value">{mockData.stats.avgResponseTime}</div>
          <div className="change positive">↓ 0.2s</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div className="panel">
          <div className="panel-header">
            <h3>Agent 状态</h3>
            <span className="badge">实时</span>
          </div>
          <div className="panel-body">
            <div className="agent-list">
              {mockData.agents.map(agent => (
                <div key={agent.name} className="agent-item">
                  <div className="agent-avatar">{agent.avatar}</div>
                  <div className="agent-info">
                    <div className="agent-name">{agent.name}</div>
                    <div className="agent-status">
                      <span className={agent.status === 'online' ? 'online' : ''}>●</span> {agent.current}
                    </div>
                  </div>
                  <div className="agent-tasks">{agent.tasks} 任务</div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h3>系统指标</h3>
            <span className="badge">实时</span>
          </div>
          <div className="panel-body">
            <div className="metrics-grid">
              <div className="metric-item">
                <div className="metric-header">
                  <span className="metric-label">CPU 使用率</span>
                </div>
                <div className="metric-value">{mockData.metrics.cpu}%</div>
                <div className="metric-bar">
                  <div className="metric-bar-fill" style={{ width: `${mockData.metrics.cpu}%` }}></div>
                </div>
              </div>
              <div className="metric-item">
                <div className="metric-header">
                  <span className="metric-label">内存使用</span>
                </div>
                <div className="metric-value">{mockData.metrics.memory}%</div>
                <div className="metric-bar">
                  <div className="metric-bar-fill" style={{ width: `${mockData.metrics.memory}%` }}></div>
                </div>
              </div>
              <div className="metric-item">
                <div className="metric-header">
                  <span className="metric-label">今日任务</span>
                </div>
                <div className="metric-value">{mockData.metrics.tasksToday}</div>
              </div>
              <div className="metric-item">
                <div className="metric-header">
                  <span className="metric-label">系统可用性</span>
                </div>
                <div className="metric-value">{mockData.metrics.uptime}%</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </>
  );
}

function AgentsView() {
  return (
    <div className="panel">
      <div className="panel-header">
        <h3>Agent 工作状态</h3>
        <span className="badge">5 个在线</span>
      </div>
      <div className="panel-body">
        <div className="agent-list">
          {mockData.agents.map(agent => (
            <div key={agent.name} className="agent-item">
              <div className="agent-avatar">{agent.avatar}</div>
              <div className="agent-info">
                <div className="agent-name">{agent.name} <span style={{ color: '#71717a', fontWeight: 400 }}>- {agent.role} Agent</span></div>
                <div className="agent-status">
                  <span className={agent.status === 'online' ? 'online' : ''}>●</span> {agent.status === 'online' ? '运行中' : '空闲'}
                </div>
              </div>
              <div className="agent-tasks">
                <div>已完成 {agent.tasks} 任务</div>
                <div style={{ color: '#3b82f6', marginTop: '4px' }}>{agent.current}</div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function WorkflowView() {
  return (
    <div className="panel">
      <div className="panel-header">
        <h3>Agent 协作流程</h3>
        <span className="badge">实时</span>
      </div>
      <div className="workflow-container">
        <div className="workflow">
          <div className="workflow-node">
            <div className="workflow-box supervisor">
              <div className="name">Supervisor</div>
              <div className="role">总控Agent</div>
            </div>
          </div>
          <div className="workflow-arrow">→</div>
          <div className="workflow-node">
            <div className="workflow-box worker">
              <div className="name">Search</div>
              <div className="role">信息检索</div>
            </div>
          </div>
          <div className="workflow-arrow">→</div>
          <div className="workflow-node">
            <div className="workflow-box worker">
              <div className="name">Code</div>
              <div className="role">代码生成</div>
            </div>
          </div>
          <div className="workflow-arrow">→</div>
          <div className="workflow-node">
            <div className="workflow-box worker">
              <div className="name">Doc</div>
              <div className="role">文档生成</div>
            </div>
          </div>
          <div className="workflow-arrow">→</div>
          <div className="workflow-node">
            <div className="workflow-box supervisor">
              <div className="name">整合</div>
              <div className="role">结果汇总</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function TasksView() {
  return (
    <div className="panel">
      <div className="panel-header">
        <h3>最近任务</h3>
        <span className="badge">4 条记录</span>
      </div>
      <div className="panel-body">
        <div className="task-timeline">
          {mockData.recentTasks.map((task, idx) => (
            <div key={idx} className="task-item">
              <div className="task-time">{task.time}</div>
              <div className="task-content">
                <div className="task-title">{task.title}</div>
                <div className="task-desc">{task.desc}</div>
                <span className={`task-status ${task.status}`}>
                  {task.status === 'completed' ? '已完成' : task.status === 'running' ? '进行中' : '待处理'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function ChatView() {
  const [chatMessages, setChatMessages] = React.useState(messages);

  const handleSend = (e) => {
    e.preventDefault();
    const input = e.target.querySelector('input');
    if (!input.value.trim()) return;

    setChatMessages([...chatMessages, {
      role: 'user',
      content: input.value
    }]);

    // Simulate response
    setTimeout(() => {
      setChatMessages(prev => [...prev, {
        role: 'assistant',
        content: '正在分析您的问题，请稍候...'
      }]);
    }, 1000);
    input.value = '';
  };

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {chatMessages.map((msg, idx) => (
          <div key={idx} className={`chat-message ${msg.role === 'user' ? 'user' : 'assistant'}`}>
            <div className="chat-bubble">{msg.content}</div>
          </div>
        ))}
      </div>
      <form className="chat-input-container" onSubmit={handleSend}>
        <input className="chat-input" type="text" placeholder="输入任务描述..." />
        <button type="submit" className="chat-send">发送</button>
      </form>
    </div>
  );
}

function App() {
  const [activeTab, setActiveTab] = React.useState('dashboard');

  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard />;
      case 'agents': return <AgentsView />;
      case 'workflow': return <WorkflowView />;
      case 'tasks': return <TasksView />;
      case 'chat': return <ChatView />;
      default: return <Dashboard />;
    }
  };

  const titles = {
    dashboard: '仪表盘',
    agents: 'Agent 状态',
    workflow: '工作流',
    tasks: '任务记录',
    chat: '对话'
  };

  return (
    <div className="app">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      <div className="main-content">
        <div className="header">
          <h2>{titles[activeTab]}</h2>
          <div className="header-meta">
            <div className="status-badge">
              <span className="status-dot"></span>
              系统正常
            </div>
          </div>
        </div>
        <div className="content">
          {renderContent()}
        </div>
      </div>
    </div>
  );
}

// Render
const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
