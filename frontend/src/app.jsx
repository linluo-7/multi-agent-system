// Mock data for demo
const mockData = {
  stats: { totalTasks: 2847, activeAgents: 5, successRate: 98.2, avgResponseTime: '1.2s' },
  agents: [
    { name: 'Supervisor', role: '总控', avatar: '🎯', status: 'online', tasks: 156, current: '任务协调中' },
    { name: 'Search', role: '搜索', avatar: '🔍', status: 'online', tasks: 423, current: '信息检索' },
    { name: 'Code', role: '编码', avatar: '💻', status: 'online', tasks: 287, current: '代码生成' },
    { name: 'Doc', role: '文档', avatar: '📄', status: 'idle', tasks: 189, current: '待命' },
    { name: 'RAG', role: '检索', avatar: '📚', status: 'online', tasks: 312, current: '知识库问答' }
  ],
  recentTasks: [
    { time: '10:32', title: '任务 #2847', desc: '分析销售数据并生成报告', status: 'completed' },
    { time: '10:28', title: '任务 #2846', desc: '搜索竞品信息完成', status: 'completed' },
    { time: '10:25', title: '任务 #2845', desc: '代码审查与优化建议', status: 'running' },
    { time: '10:20', title: '任务 #2844', desc: '生成API接口文档', status: 'completed' }
  ],
  metrics: { cpu: 34, memory: 67, tasksToday: 127, uptime: 99.9 }
};

const initMessages = [
  { role: 'user', content: '帮我分析一下最近的销售数据，找出增长趋势' },
  { role: 'assistant', content: '好的，我来分析最近30天的销售数据。\n\n**主要发现：**\n1. 整体销售额较上月增长 **23.5%**\n2. 华东地区增速最快，达到 **31.2%**\n3. 周末销量环比增长 **18.7%**\n\n> 📚 来源: 销售数据库 [1]\n\n需要我进一步分析某个具体维度吗？' },
];

const API_BASE = '';

// ---- Sidebar ----
function Sidebar({ activeTab, setActiveTab }) {
  const navItems = [
    { id: 'dashboard', icon: '◈', label: '仪表盘' },
    { id: 'agents', icon: '◉', label: 'Agent状态' },
    { id: 'workflow', icon: '◎', label: '工作流' },
    { id: 'tasks', icon: '◇', label: '任务记录' },
    { id: 'chat', icon: '○', label: '对话' },
    { id: 'knowledge', icon: '📚', label: '知识库' },
  ];
  return (
    <div className="sidebar">
      <div className="logo"><h1>Multi-Agent</h1><span>协作系统 v2.0</span></div>
      {navItems.map(item => (
        <button key={item.id} className={`nav-item ${activeTab === item.id ? 'active' : ''}`} onClick={() => setActiveTab(item.id)}>
          <span className="icon">{item.icon}</span>{item.label}
        </button>
      ))}
    </div>
  );
}

// ---- Dashboard ----
function Dashboard() { /* unchanged mock dashboard */ return (<div className="panel">仪表盘</div>); }
function AgentsView() { return (<div className="panel">Agent状态视图</div>); }
function WorkflowView() { return (<div className="panel">工作流视图</div>); }
function TasksView() { return (<div className="panel">任务记录</div>); }

// ---- ChatView (P4-6: real API) ----
function ChatView() {
  const [chatMessages, setChatMessages] = React.useState(initMessages);
  const [loading, setLoading] = React.useState(false);
  const [ragMode, setRagMode] = React.useState(true);

  const handleSend = async (e) => {
    e.preventDefault();
    const input = e.target.querySelector('input');
    if (!input.value.trim()) return;
    const query = input.value.trim();
    input.value = '';
    setChatMessages(prev => [...prev, { role: 'user', content: query }]);
    setLoading(true);

    try {
      const endpoint = ragMode ? `${API_BASE}/api/v1/rag/search` : `${API_BASE}/api/v1/chat`;
      const body = ragMode ? { query, kb_name: 'default' } : { message: query, conversation_id: 'default' };
      const resp = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const data = await resp.json();
      const answer = ragMode
        ? (data.context || '未找到相关信息') + '\n\n> 📚 共找到 ' + (data.total_found || 0) + ' 条相关文档'
        : (data.response || JSON.stringify(data));
      setChatMessages(prev => [...prev, { role: 'assistant', content: answer }]);
    } catch (err) {
      setChatMessages(prev => [...prev, { role: 'assistant', content: '抱歉，服务暂不可用 (' + err.message + ')' }]);
    }
    setLoading(false);
  };

  const renderContent = (content) => {
    let html = content
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/\n/g, '<br/>')
      .replace(/\[(\d+(?:[-,]\d+)*)\]/g, '<sup class="citation">[$1]</sup>')
      .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    return { __html: html };
  };

  return (
    <div className="chat-container">
      <div style={{ padding: '8px 16px', borderBottom: '1px solid #2d2d3f' }}>
        <label style={{ color: '#a1a1aa', fontSize: '14px', cursor: 'pointer' }}>
          <input type="checkbox" checked={ragMode} onChange={() => setRagMode(!ragMode)} style={{ marginRight: 8 }} />
          知识库RAG模式 {ragMode ? '(检索文档回答)' : '(Agent协作)'}
        </label>
      </div>
      <div className="chat-messages">
        {chatMessages.map((msg, idx) => (
          <div key={idx} className={`chat-message ${msg.role === 'user' ? 'user' : 'assistant'}`}>
            <div className="chat-bubble" dangerouslySetInnerHTML={renderContent(msg.content)} />
          </div>
        ))}
        {loading && <div className="chat-message assistant"><div className="chat-bubble">⏳ 检索中...</div></div>}
      </div>
      <form className="chat-input-container" onSubmit={handleSend}>
        <input className="chat-input" type="text" placeholder="输入问题（支持知识库检索 + Agent协作）..." />
        <button type="submit" className="chat-send" disabled={loading}>发送</button>
      </form>
    </div>
  );
}

// ---- KnowledgeBaseView (P4-1/2) ----
function KnowledgeBaseView() {
  const [docs, setDocs] = React.useState([]);
  const [kbs, setKbs] = React.useState([]);
  const [activeKb, setActiveKb] = React.useState('default');
  const [uploading, setUploading] = React.useState(false);
  const [message, setMessage] = React.useState('');
  const fileInputRef = React.useRef(null);
  const [dragOver, setDragOver] = React.useState(false);

  const loadDocs = async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/rag/documents?kb_name=${activeKb}`);
      const data = await resp.json();
      setDocs(data.documents || []);
    } catch (err) { console.error(err); }
  };

  const loadKBs = async () => {
    try {
      const resp = await fetch(`${API_BASE}/api/v1/rag/knowledge-bases`);
      const data = await resp.json();
      setKbs(data.knowledge_bases || []);
    } catch (err) {}
  };

  React.useEffect(() => { loadKBs(); }, []);
  React.useEffect(() => { loadDocs(); }, [activeKb]);
  React.useEffect(() => { if (message) { const t = setTimeout(() => setMessage(''), 3000); return () => clearTimeout(t); } }, [message]);

  const handleUpload = async (files) => {
    setUploading(true);
    let count = 0;
    for (const file of files) {
      try {
        const formData = new FormData();
        formData.append('file', file);
        formData.append('kb_name', activeKb);
        const resp = await fetch(`${API_BASE}/api/v1/rag/documents/upload`, { method: 'POST', body: formData });
        const data = await resp.json();
        if (data.status === 'ok') count++;
      } catch (err) { console.error(err); }
    }
    setMessage(`成功导入 ${count}/${files.length} 个文档`);
    setUploading(false);
    loadDocs();
  };

  const handleDelete = async (docId) => {
    try {
      await fetch(`${API_BASE}/api/v1/rag/documents/delete`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ doc_id: docId })
      });
      loadDocs();
      setMessage('文档已删除');
    } catch (err) { console.error(err); }
  };

  const handleUrlImport = async () => {
    const url = prompt('输入文档URL：');
    if (!url) return;
    try {
      const resp = await fetch(`${API_BASE}/api/v1/rag/documents/import-url`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url, kb_name: activeKb })
      });
      const data = await resp.json();
      setMessage(data.status === 'ok' ? 'URL导入成功' : '导入失败: ' + data.message);
      loadDocs();
    } catch (err) { setMessage('导入失败: ' + err.message); }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setDragOver(false);
    handleUpload(e.dataTransfer.files);
  };

  return (
    <div>
      {message && <div style={{ padding: '10px 16px', background: '#1a3a2a', color: '#4ade80', borderRadius: 6, marginBottom: 16 }}>{message}</div>}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
        <div className="panel">
          <div className="panel-header"><h3>知识库列表</h3></div>
          <div className="panel-body">
            {kbs.map(kb => (
              <div key={kb.name} onClick={() => setActiveKb(kb.name)}
                style={{ padding: '10px', margin: '4px 0', borderRadius: 6, cursor: 'pointer',
                  background: activeKb === kb.name ? '#3b82f620' : 'transparent',
                  border: activeKb === kb.name ? '1px solid #3b82f6' : '1px solid transparent' }}>
                <div style={{ fontWeight: 600 }}>{kb.name} <span style={{ color: '#71717a' }}>({kb.doc_count} 文档)</span></div>
                <div style={{ fontSize: 13, color: '#71717a' }}>{kb.description}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header"><h3>导入文档 ({activeKb})</h3></div>
          <div className="panel-body">
            <div onDrop={handleDrop} onDragOver={e => { e.preventDefault(); setDragOver(true); }} onDragLeave={() => setDragOver(false)}
              style={{ border: `2px dashed ${dragOver ? '#3b82f6' : '#3f3f5c'}`, borderRadius: 8, padding: '30px', textAlign: 'center',
                cursor: 'pointer', background: dragOver ? '#3b82f610' : 'transparent', marginBottom: 12 }}
              onClick={() => fileInputRef.current?.click()}>
              {uploading ? '⏳ 上传中...' : '📁 拖拽文件到此上传 或 点击选择'}
              <input ref={fileInputRef} type="file" multiple hidden
                onChange={e => { if (e.target.files.length) handleUpload(e.target.files); e.target.value = ''; }}
                accept=".pdf,.docx,.doc,.txt,.md,.html,.csv,.json,.yaml,.xml" />
            </div>
            <button onClick={handleUrlImport} style={{ width: '100%', padding: '8px', background: '#3b82f6', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer' }}>
              🌐 从URL导入
            </button>
          </div>
        </div>
      </div>

      <div className="panel" style={{ marginTop: 16 }}>
        <div className="panel-header"><h3>已索引文档 ({docs.length})</h3></div>
        <div className="panel-body">
          {docs.length === 0 ? <div style={{ color: '#71717a', textAlign: 'center', padding: 20 }}>暂无文档，请上传或导入</div> :
            docs.map((doc, idx) => (
              <div key={doc.id || idx} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                padding: '10px', borderBottom: '1px solid #2d2d3f' }}>
                <div>
                  <div style={{ fontWeight: 600 }}>{doc.filename}</div>
                  <div style={{ fontSize: 12, color: '#71717a' }}>
                    {doc.file_type} · {doc.chunk_count} chunks · {new Date(doc.created_at).toLocaleDateString()}
                  </div>
                </div>
                <button onClick={() => handleDelete(doc.id)}
                  style={{ padding: '4px 12px', background: '#dc262620', color: '#dc2626', border: '1px solid #dc262640', borderRadius: 4, cursor: 'pointer' }}>
                  删除
                </button>
              </div>
            ))
          }
        </div>
      </div>
    </div>
  );
}

// ---- App ----
function App() {
  const [activeTab, setActiveTab] = React.useState('dashboard');
  const renderContent = () => {
    switch (activeTab) {
      case 'dashboard': return <Dashboard />;
      case 'agents': return <AgentsView />;
      case 'workflow': return <WorkflowView />;
      case 'tasks': return <TasksView />;
      case 'chat': return <ChatView />;
      case 'knowledge': return <KnowledgeBaseView />;
      default: return <Dashboard />;
    }
  };
  const titles = { dashboard: '仪表盘', agents: 'Agent 状态', workflow: '工作流', tasks: '任务记录', chat: '对话', knowledge: '知识库管理' };
  return (
    <div className="app">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      <div className="main-content">
        <div className="header">
          <h2>{titles[activeTab]}</h2>
          <div className="header-meta"><div className="status-badge"><span className="status-dot"></span>系统正常</div></div>
        </div>
        <div className="content">{renderContent()}</div>
      </div>
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById('root'));
root.render(<App />);
