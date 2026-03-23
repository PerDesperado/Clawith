import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { agentApi, taskApi, teamApi } from '../services/api';

// API helper
async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
    const token = localStorage.getItem('token');
    const res = await fetch(`/api${url}`, {
        ...options,
        headers: {
            'Content-Type': 'application/json',
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
    });
    if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || 'Error');
    if (res.status === 204) return undefined as T;
    return res.json();
}

interface Binding {
    id: string;
    user_id: string;
    agent_id: string;
    is_active: boolean;
    created_at: string;
    agent_name: string | null;
    agent_avatar: string | null;
    agent_role: string | null;
    agent_status: string | null;
}

interface DailySummaryItem {
    id: string;
    user_id: string;
    summary_date: string;
    content: string;
    agent_details: Record<string, any>;
    total_tasks_completed: number;
    total_messages: number;
    total_tokens_used: number;
    created_at: string;
}

interface AgentTask {
    id: string;
    title: string;
    description?: string;
    status: string;
    priority: string;
    type: string;
    created_at: string;
    completed_at?: string;
}

const STATUS_COLORS: Record<string, string> = {
    running: '#22c55e',
    idle: '#eab308',
    stopped: '#6b7280',
    error: '#ef4444',
    creating: '#6366f1',
};

const TASK_STATUS_LABELS: Record<string, { label: string; color: string }> = {
    pending: { label: '待处理', color: '#eab308' },
    doing: { label: '执行中', color: '#6366f1' },
    done: { label: '已完成', color: '#22c55e' },
    failed: { label: '失败', color: '#ef4444' },
};

const PRIORITY_COLORS: Record<string, string> = {
    high: '#ef4444',
    medium: '#eab308',
    low: '#6b7280',
};

export default function MyAgents() {
    const { t } = useTranslation();
    const [activeTab, setActiveTab] = useState<'bindings' | 'reports' | 'summaries'>('bindings');
    const [bindings, setBindings] = useState<Binding[]>([]);
    const [summaries, setSummaries] = useState<DailySummaryItem[]>([]);
    const [allAgents, setAllAgents] = useState<any[]>([]);
    const [selectedAgent, setSelectedAgent] = useState('');
    const [loading, setLoading] = useState(false);
    const [generating, setGenerating] = useState(false);
    const [selectedSummary, setSelectedSummary] = useState<DailySummaryItem | null>(null);
    const [expandedAgent, setExpandedAgent] = useState<string | null>(null);
    const [agentTasks, setAgentTasks] = useState<Record<string, AgentTask[]>>({});
    const [loadingTasks, setLoadingTasks] = useState<Record<string, boolean>>({});
    // Daily reports
    const [pendingReports, setPendingReports] = useState<any[]>([]);
    const [loadingReports, setLoadingReports] = useState(false);
    const [confirmingId, setConfirmingId] = useState<string | null>(null);
    const [rejectComment, setRejectComment] = useState<Record<string, string>>({});
    const [showRejectInput, setShowRejectInput] = useState<string | null>(null);

    // Load bindings
    const loadBindings = async () => {
        try {
            const data = await fetchJson<Binding[]>('/bindings/');
            setBindings(data);
        } catch (e) {
            console.error('Failed to load bindings:', e);
        }
    };

    // Load all agents for binding picker
    const loadAgents = async () => {
        try {
            const data = await agentApi.list();
            setAllAgents(data);
        } catch (e) {
            console.error('Failed to load agents:', e);
        }
    };

    // Load daily summaries
    const loadSummaries = async () => {
        try {
            const data = await fetchJson<DailySummaryItem[]>('/bindings/summaries');
            setSummaries(data);
        } catch (e) {
            console.error('Failed to load summaries:', e);
        }
    };

    useEffect(() => {
        loadBindings();
        loadAgents();
        loadSummaries();
        loadPendingReports();
    }, []);

    // Load pending daily reports
    const loadPendingReports = async () => {
        setLoadingReports(true);
        try {
            const data = await teamApi.listPendingReports();
            setPendingReports(data);
        } catch (e) {
            console.error('Failed to load pending reports:', e);
        }
        setLoadingReports(false);
    };

    const handleConfirmReport = async (reportId: string) => {
        setConfirmingId(reportId);
        try {
            await teamApi.confirmReport(reportId, 'confirm');
            await loadPendingReports();
        } catch (e: any) {
            alert(e.message);
        }
        setConfirmingId(null);
    };

    const handleRejectReport = async (reportId: string) => {
        setConfirmingId(reportId);
        try {
            await teamApi.confirmReport(reportId, 'reject', rejectComment[reportId] || '');
            setShowRejectInput(null);
            setRejectComment(prev => ({ ...prev, [reportId]: '' }));
            await loadPendingReports();
        } catch (e: any) {
            alert(e.message);
        }
        setConfirmingId(null);
    };

    const handleBind = async () => {
        if (!selectedAgent) return;
        setLoading(true);
        try {
            await fetchJson('/bindings/', {
                method: 'POST',
                body: JSON.stringify({ agent_id: selectedAgent }),
            });
            setSelectedAgent('');
            await loadBindings();
        } catch (e: any) {
            alert(e.message);
        }
        setLoading(false);
    };

    const handleUnbind = async (bindingId: string) => {
        if (!confirm('确定解除绑定？')) return;
        try {
            await fetchJson(`/bindings/${bindingId}`, { method: 'DELETE' });
            await loadBindings();
        } catch (e: any) {
            alert(e.message);
        }
    };

    const handleToggle = async (bindingId: string) => {
        try {
            await fetchJson(`/bindings/${bindingId}/toggle`, { method: 'PATCH' });
            await loadBindings();
        } catch (e: any) {
            alert(e.message);
        }
    };

    const handleGenerateSummary = async () => {
        setGenerating(true);
        try {
            await fetchJson('/bindings/summaries/generate', { method: 'POST' });
            await loadSummaries();
        } catch (e: any) {
            alert(e.message);
        }
        setGenerating(false);
    };

    // Filter out already bound agents
    const availableAgents = allAgents.filter(
        a => !bindings.some(b => b.agent_id === a.id)
    );

    // Load tasks for a specific agent
    const loadAgentTasks = async (agentId: string) => {
        setLoadingTasks(prev => ({ ...prev, [agentId]: true }));
        try {
            const tasks = await taskApi.list(agentId);
            setAgentTasks(prev => ({ ...prev, [agentId]: tasks }));
        } catch (e) {
            console.error('Failed to load tasks for agent:', agentId, e);
            setAgentTasks(prev => ({ ...prev, [agentId]: [] }));
        }
        setLoadingTasks(prev => ({ ...prev, [agentId]: false }));
    };

    // Toggle expand agent task list
    const toggleAgentExpand = (agentId: string) => {
        if (expandedAgent === agentId) {
            setExpandedAgent(null);
        } else {
            setExpandedAgent(agentId);
            if (!agentTasks[agentId]) {
                loadAgentTasks(agentId);
            }
        }
    };

    return (
        <div>
            <div className="page-header">
                <div>
                    <h1 className="page-title">我的数字员工</h1>
                    <p style={{ fontSize: '13px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                        绑定多个数字员工，查看每日工作总结
                    </p>
                </div>
            </div>

            <div className="tabs" style={{ marginBottom: '16px' }}>
                <div className={`tab ${activeTab === 'bindings' ? 'active' : ''}`} onClick={() => setActiveTab('bindings')}>
                    数字员工绑定
                </div>
                <div className={`tab ${activeTab === 'reports' ? 'active' : ''}`} onClick={() => { setActiveTab('reports'); loadPendingReports(); }}>
                    工作日报
                    {pendingReports.length > 0 && (
                        <span style={{
                            display: 'inline-block', marginLeft: '6px',
                            background: 'var(--error)', color: '#fff',
                            fontSize: '10px', fontWeight: 600,
                            padding: '1px 6px', borderRadius: '10px',
                            minWidth: '16px', textAlign: 'center',
                        }}>
                            {pendingReports.length}
                        </span>
                    )}
                </div>
                <div className={`tab ${activeTab === 'summaries' ? 'active' : ''}`} onClick={() => setActiveTab('summaries')}>
                    每日工作总结
                </div>
            </div>

            {/* Bindings Tab */}
            {activeTab === 'bindings' && (
                <div>
                    {/* Add binding */}
                    <div className="card" style={{ marginBottom: '16px' }}>
                        <h4 style={{ marginBottom: '12px' }}>绑定新的数字员工</h4>
                        <div style={{ display: 'flex', gap: '12px', alignItems: 'flex-end' }}>
                            <div style={{ flex: 1 }}>
                                <label style={{ fontSize: '12px', fontWeight: 500, display: 'block', marginBottom: '4px' }}>选择数字员工</label>
                                <select
                                    className="input"
                                    value={selectedAgent}
                                    onChange={e => setSelectedAgent(e.target.value)}
                                    style={{ width: '100%', height: '36px' }}
                                >
                                    <option value="">请选择...</option>
                                    {availableAgents.map(a => (
                                        <option key={a.id} value={a.id}>
                                            {a.name} - {a.role_description || '无描述'}
                                        </option>
                                    ))}
                                </select>
                            </div>
                            <button className="btn btn-primary" onClick={handleBind} disabled={loading || !selectedAgent}>
                                {loading ? '绑定中...' : '绑定'}
                            </button>
                        </div>
                        {availableAgents.length === 0 && bindings.length > 0 && (
                            <p style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '8px' }}>
                                所有可用的数字员工都已绑定
                            </p>
                        )}
                    </div>

                    {/* Binding list */}
                    <div className="card">
                        <h4 style={{ marginBottom: '12px' }}>
                            已绑定的数字员工
                            <span style={{ fontSize: '12px', fontWeight: 400, color: 'var(--text-tertiary)', marginLeft: '8px' }}>
                                ({bindings.length})
                            </span>
                        </h4>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                            {bindings.length === 0 && (
                                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                                    <div style={{ fontSize: '36px', marginBottom: '8px' }}>🤖</div>
                                    <div>暂未绑定任何数字员工</div>
                                    <div style={{ fontSize: '12px', marginTop: '4px' }}>从上方选择数字员工进行绑定</div>
                                </div>
                            )}
                            {bindings.map(b => {
                                const isExpanded = expandedAgent === b.agent_id;
                                const tasks = agentTasks[b.agent_id] || [];
                                const isLoadingTasks = loadingTasks[b.agent_id] || false;
                                return (
                                <div key={b.id} style={{
                                    borderRadius: '10px',
                                    border: isExpanded ? '2px solid var(--accent-primary)' : '1px solid var(--border-subtle)',
                                    opacity: b.is_active ? 1 : 0.5,
                                    overflow: 'hidden',
                                }}>
                                    <div style={{
                                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                        padding: '12px 16px',
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, cursor: 'pointer' }}
                                            onClick={() => toggleAgentExpand(b.agent_id)}
                                        >
                                            <div style={{
                                                width: '40px', height: '40px', borderRadius: '10px',
                                                background: 'var(--accent-primary)',
                                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                fontSize: '20px', color: '#fff', flexShrink: 0,
                                            }}>
                                                {b.agent_avatar ? (
                                                    <img src={b.agent_avatar} alt="" style={{ width: '100%', height: '100%', borderRadius: '10px', objectFit: 'cover' }} />
                                                ) : '🤖'}
                                            </div>
                                            <div style={{ flex: 1 }}>
                                                <div style={{ fontWeight: 600, fontSize: '14px' }}>
                                                    {b.agent_name || '未命名'}
                                                    <span style={{
                                                        display: 'inline-block',
                                                        width: '8px', height: '8px', borderRadius: '50%',
                                                        background: STATUS_COLORS[b.agent_status || 'stopped'] || '#6b7280',
                                                        marginLeft: '8px',
                                                        verticalAlign: 'middle',
                                                    }} />
                                                </div>
                                                <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                                                    {b.agent_role || '无角色描述'}
                                                    {!b.is_active && <span style={{ color: 'var(--warning)', marginLeft: '8px' }}>已暂停</span>}
                                                </div>
                                            </div>
                                            <span style={{
                                                fontSize: '12px', color: 'var(--text-tertiary)',
                                                transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                                                transition: 'transform 0.2s',
                                            }}>▼</span>
                                        </div>
                                        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginLeft: '12px' }}>
                                            <button
                                                className="btn btn-ghost"
                                                style={{ fontSize: '12px' }}
                                                onClick={() => handleToggle(b.id)}
                                            >
                                                {b.is_active ? '暂停' : '启用'}
                                            </button>
                                            <button
                                                className="btn btn-ghost"
                                                style={{ fontSize: '12px', color: 'var(--error)' }}
                                                onClick={() => handleUnbind(b.id)}
                                            >
                                                解绑
                                            </button>
                                        </div>
                                    </div>

                                    {/* Task list panel */}
                                    {isExpanded && (
                                        <div style={{
                                            borderTop: '1px solid var(--border-subtle)',
                                            padding: '12px 16px',
                                            background: 'var(--bg-secondary)',
                                        }}>
                                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '10px' }}>
                                                <h5 style={{ fontSize: '13px', fontWeight: 600, margin: 0 }}>
                                                    任务列表
                                                    <span style={{ fontSize: '11px', fontWeight: 400, color: 'var(--text-tertiary)', marginLeft: '6px' }}>
                                                        ({tasks.length})
                                                    </span>
                                                </h5>
                                                <button
                                                    className="btn btn-ghost"
                                                    style={{ fontSize: '11px', padding: '2px 8px' }}
                                                    onClick={() => loadAgentTasks(b.agent_id)}
                                                    disabled={isLoadingTasks}
                                                >
                                                    {isLoadingTasks ? '加载中...' : '刷新'}
                                                </button>
                                            </div>
                                            <div style={{
                                                maxHeight: '320px',
                                                overflowY: 'auto',
                                                display: 'flex', flexDirection: 'column', gap: '6px',
                                            }}>
                                                {isLoadingTasks && tasks.length === 0 && (
                                                    <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-tertiary)', fontSize: '12px' }}>
                                                        加载中...
                                                    </div>
                                                )}
                                                {!isLoadingTasks && tasks.length === 0 && (
                                                    <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-tertiary)', fontSize: '12px' }}>
                                                        暂无任务
                                                    </div>
                                                )}
                                                {tasks.map(task => {
                                                    const statusInfo = TASK_STATUS_LABELS[task.status] || { label: task.status, color: '#6b7280' };
                                                    return (
                                                        <div key={task.id} style={{
                                                            padding: '10px 12px', borderRadius: '8px',
                                                            background: 'var(--bg-primary)',
                                                            border: '1px solid var(--border-subtle)',
                                                        }}>
                                                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                                    <div style={{
                                                                        fontSize: '13px', fontWeight: 500,
                                                                        whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                                                    }}>
                                                                        {task.title}
                                                                    </div>
                                                                    {task.description && (
                                                                        <div style={{
                                                                            fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '3px',
                                                                            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                                                                        }}>
                                                                            {task.description}
                                                                        </div>
                                                                    )}
                                                                </div>
                                                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexShrink: 0 }}>
                                                                    {task.priority && (
                                                                        <span style={{
                                                                            fontSize: '10px', padding: '2px 6px', borderRadius: '4px',
                                                                            background: `${PRIORITY_COLORS[task.priority] || '#6b7280'}20`,
                                                                            color: PRIORITY_COLORS[task.priority] || '#6b7280',
                                                                        }}>
                                                                            {task.priority === 'high' ? '高' : task.priority === 'medium' ? '中' : '低'}
                                                                        </span>
                                                                    )}
                                                                    <span style={{
                                                                        fontSize: '10px', padding: '2px 6px', borderRadius: '4px',
                                                                        background: `${statusInfo.color}20`,
                                                                        color: statusInfo.color,
                                                                        fontWeight: 500,
                                                                    }}>
                                                                        {statusInfo.label}
                                                                    </span>
                                                                </div>
                                                            </div>
                                                            <div style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginTop: '6px' }}>
                                                                {task.type === 'todo' ? '待办' : task.type === 'supervision' ? '督办' : task.type}
                                                                {' · '}
                                                                {new Date(task.created_at).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                                                {task.completed_at && (
                                                                    <span style={{ color: 'var(--success)' }}>
                                                                        {' · 完成于 '}
                                                                        {new Date(task.completed_at).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
                                                                    </span>
                                                                )}
                                                            </div>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        </div>
                                    )}
                                </div>
                                );
                            })}
                        </div>
                    </div>
                </div>
            )}

            {/* Daily Reports Tab */}
            {activeTab === 'reports' && (
                <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <h4>
                            待确认日报
                            <span style={{ fontSize: '12px', fontWeight: 400, color: 'var(--text-tertiary)', marginLeft: '8px' }}>
                                ({pendingReports.length})
                            </span>
                        </h4>
                        <button className="btn btn-ghost" onClick={loadPendingReports} disabled={loadingReports} style={{ fontSize: '12px' }}>
                            {loadingReports ? '加载中...' : '刷新'}
                        </button>
                    </div>

                    <p style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '16px' }}>
                        数字员工每天自动生成工作日报，经您确认后发布，管理员可在仪表盘查看。
                    </p>

                    {loadingReports && pendingReports.length === 0 && (
                        <div className="card" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                            加载中...
                        </div>
                    )}

                    {!loadingReports && pendingReports.length === 0 && (
                        <div className="card" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                            <div style={{ fontSize: '36px', marginBottom: '8px' }}>📝</div>
                            <div>暂无待确认的日报</div>
                            <div style={{ fontSize: '12px', marginTop: '4px' }}>数字员工的工作日报会在每日结束时自动生成</div>
                        </div>
                    )}

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        {pendingReports.map(report => (
                            <div key={report.id} className="card" style={{ padding: '16px' }}>
                                {/* Header */}
                                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                                    <div style={{
                                        width: '36px', height: '36px', borderRadius: '50%',
                                        background: 'var(--accent-primary)',
                                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                                        fontSize: '18px', color: '#fff',
                                    }}>
                                        {report.agent_avatar ? (
                                            <img src={report.agent_avatar} alt="" style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover' }} />
                                        ) : '🤖'}
                                    </div>
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontWeight: 600, fontSize: '14px' }}>
                                            {report.agent_name || '数字员工'}
                                        </div>
                                        <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                                            {report.report_date ? new Date(report.report_date).toLocaleDateString('zh-CN') : '-'}
                                            <span style={{
                                                marginLeft: '8px', padding: '1px 6px', borderRadius: '4px',
                                                background: report.report_status === 'draft' ? '#eab30820' : '#6366f120',
                                                color: report.report_status === 'draft' ? '#eab308' : '#6366f1',
                                                fontSize: '10px', fontWeight: 500,
                                            }}>
                                                {report.report_status === 'draft' ? '待确认' : '审核中'}
                                            </span>
                                        </div>
                                    </div>
                                </div>

                                {/* Summary */}
                                <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.6', marginBottom: '12px' }}>
                                    {report.summary || '暂无工作总结'}
                                </div>

                                {/* Stats */}
                                <div style={{ display: 'flex', gap: '16px', marginBottom: '12px', paddingBottom: '12px', borderBottom: '1px solid var(--border-subtle)' }}>
                                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                                        <span style={{ color: 'var(--success)', fontWeight: 600 }}>{report.tasks_completed_count || 0}</span> 完成
                                    </div>
                                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                                        <span style={{ color: 'var(--accent-primary)', fontWeight: 600 }}>{report.tasks_in_progress_count || 0}</span> 进行中
                                    </div>
                                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                                        <span style={{ fontWeight: 600 }}>{report.messages_sent || 0}</span> 消息
                                    </div>
                                </div>

                                {/* Completed tasks details */}
                                {report.completed_tasks && report.completed_tasks.length > 0 && (
                                    <div style={{ marginBottom: '12px' }}>
                                        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>已完成任务：</div>
                                        {report.completed_tasks.slice(0, 5).map((t: any, i: number) => (
                                            <div key={i} style={{ fontSize: '12px', padding: '2px 0', color: 'var(--text-secondary)' }}>
                                                ✅ {t.title}
                                            </div>
                                        ))}
                                        {report.completed_tasks.length > 5 && (
                                            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>...还有 {report.completed_tasks.length - 5} 项</div>
                                        )}
                                    </div>
                                )}

                                {/* In progress tasks */}
                                {report.in_progress_tasks && report.in_progress_tasks.length > 0 && (
                                    <div style={{ marginBottom: '12px' }}>
                                        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>进行中任务：</div>
                                        {report.in_progress_tasks.slice(0, 3).map((t: any, i: number) => (
                                            <div key={i} style={{ fontSize: '12px', padding: '2px 0', color: 'var(--text-secondary)' }}>
                                                🔄 {t.title}
                                            </div>
                                        ))}
                                    </div>
                                )}

                                {/* Reject comment input */}
                                {showRejectInput === report.id && (
                                    <div style={{ marginBottom: '12px' }}>
                                        <textarea
                                            className="input"
                                            placeholder="退回原因（可选）..."
                                            value={rejectComment[report.id] || ''}
                                            onChange={e => setRejectComment(prev => ({ ...prev, [report.id]: e.target.value }))}
                                            style={{ width: '100%', height: '60px', fontSize: '12px', resize: 'vertical' }}
                                        />
                                    </div>
                                )}

                                {/* Action buttons */}
                                <div style={{ display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                                    {showRejectInput === report.id ? (
                                        <>
                                            <button
                                                className="btn btn-ghost"
                                                style={{ fontSize: '12px' }}
                                                onClick={() => setShowRejectInput(null)}
                                            >
                                                取消
                                            </button>
                                            <button
                                                className="btn btn-ghost"
                                                style={{ fontSize: '12px', color: 'var(--error)' }}
                                                onClick={() => handleRejectReport(report.id)}
                                                disabled={confirmingId === report.id}
                                            >
                                                {confirmingId === report.id ? '处理中...' : '确认退回'}
                                            </button>
                                        </>
                                    ) : (
                                        <>
                                            <button
                                                className="btn btn-ghost"
                                                style={{ fontSize: '12px', color: 'var(--error)' }}
                                                onClick={() => setShowRejectInput(report.id)}
                                            >
                                                退回修改
                                            </button>
                                            <button
                                                className="btn btn-primary"
                                                style={{ fontSize: '12px' }}
                                                onClick={() => handleConfirmReport(report.id)}
                                                disabled={confirmingId === report.id}
                                            >
                                                {confirmingId === report.id ? '发布中...' : '确认发布'}
                                            </button>
                                        </>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            )}

            {/* Daily Summaries Tab */}
            {activeTab === 'summaries' && (
                <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                        <h4>工作总结记录</h4>
                        <button className="btn btn-primary" onClick={handleGenerateSummary} disabled={generating}>
                            {generating ? '生成中...' : '生成今日总结'}
                        </button>
                    </div>

                    <div style={{ display: 'flex', gap: '16px' }}>
                        {/* Summary list */}
                        <div style={{ width: '300px', flexShrink: 0 }}>
                            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                                {summaries.length === 0 && (
                                    <div className="card" style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                                        <div style={{ fontSize: '36px', marginBottom: '8px' }}>📊</div>
                                        <div>暂无工作总结</div>
                                        <div style={{ fontSize: '12px', marginTop: '4px' }}>点击「生成今日总结」开始</div>
                                    </div>
                                )}
                                {summaries.map(s => (
                                    <div
                                        key={s.id}
                                        className="card"
                                        style={{
                                            padding: '12px 16px', cursor: 'pointer',
                                            border: selectedSummary?.id === s.id ? '2px solid var(--accent-primary)' : '1px solid var(--border-subtle)',
                                        }}
                                        onClick={() => setSelectedSummary(s)}
                                    >
                                        <div style={{ fontWeight: 600, fontSize: '14px' }}>{s.summary_date}</div>
                                        <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                                            任务 {s.total_tasks_completed} · 消息 {s.total_messages} · Token {s.total_tokens_used}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Summary detail */}
                        <div style={{ flex: 1 }}>
                            {selectedSummary ? (
                                <div className="card" style={{ padding: '24px' }}>
                                    <h3 style={{ marginBottom: '16px' }}>{selectedSummary.summary_date} 工作总结</h3>

                                    {/* Stats */}
                                    <div style={{ display: 'flex', gap: '16px', marginBottom: '24px' }}>
                                        <div style={{
                                            flex: 1, padding: '16px', borderRadius: '10px',
                                            background: 'rgba(34,197,94,0.1)',
                                            textAlign: 'center',
                                        }}>
                                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--success)' }}>{selectedSummary.total_tasks_completed}</div>
                                            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>完成任务</div>
                                        </div>
                                        <div style={{
                                            flex: 1, padding: '16px', borderRadius: '10px',
                                            background: 'rgba(99,102,241,0.1)',
                                            textAlign: 'center',
                                        }}>
                                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--accent-primary)' }}>{selectedSummary.total_messages}</div>
                                            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>交互消息</div>
                                        </div>
                                        <div style={{
                                            flex: 1, padding: '16px', borderRadius: '10px',
                                            background: 'rgba(234,179,8,0.1)',
                                            textAlign: 'center',
                                        }}>
                                            <div style={{ fontSize: '28px', fontWeight: 700, color: 'var(--warning)' }}>{selectedSummary.total_tokens_used}</div>
                                            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>Token 消耗</div>
                                        </div>
                                    </div>

                                    {/* Per-agent details */}
                                    {Object.entries(selectedSummary.agent_details).length > 0 && (
                                        <div>
                                            <h4 style={{ marginBottom: '12px', fontSize: '14px' }}>各数字员工详情</h4>
                                            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                                {Object.entries(selectedSummary.agent_details).map(([agentId, detail]: [string, any]) => (
                                                    <div key={agentId} style={{
                                                        padding: '14px', borderRadius: '8px',
                                                        border: '1px solid var(--border-subtle)',
                                                    }}>
                                                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                                                            <div style={{ fontWeight: 600 }}>
                                                                🤖 {detail.name}
                                                                <span style={{
                                                                    display: 'inline-block',
                                                                    width: '8px', height: '8px', borderRadius: '50%',
                                                                    background: STATUS_COLORS[detail.status] || '#6b7280',
                                                                    marginLeft: '8px', verticalAlign: 'middle',
                                                                }} />
                                                            </div>
                                                            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                                                                {detail.role}
                                                            </span>
                                                        </div>
                                                        <div style={{ display: 'flex', gap: '16px', fontSize: '13px' }}>
                                                            <span>完成 <strong>{detail.tasks_completed}</strong> 任务</span>
                                                            <span>进行中 <strong>{detail.tasks_in_progress}</strong></span>
                                                            <span>消息 <strong>{detail.messages_count}</strong></span>
                                                            <span>Token <strong>{detail.tokens_used_today}</strong></span>
                                                        </div>
                                                        {detail.completed_task_titles?.length > 0 && (
                                                            <div style={{ marginTop: '8px', paddingTop: '8px', borderTop: '1px solid var(--border-subtle)' }}>
                                                                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>完成的任务：</div>
                                                                {detail.completed_task_titles.map((title: string, i: number) => (
                                                                    <div key={i} style={{ fontSize: '12px', padding: '2px 0', color: 'var(--text-secondary)' }}>
                                                                        · {title}
                                                                    </div>
                                                                ))}
                                                            </div>
                                                        )}
                                                    </div>
                                                ))}
                                            </div>
                                        </div>
                                    )}

                                    {/* Raw content */}
                                    <div style={{ marginTop: '24px', paddingTop: '16px', borderTop: '1px solid var(--border-subtle)' }}>
                                        <h4 style={{ marginBottom: '8px', fontSize: '14px' }}>总结内容</h4>
                                        <pre style={{
                                            fontSize: '13px', lineHeight: 1.6,
                                            background: 'var(--bg-tertiary)',
                                            padding: '16px', borderRadius: '8px',
                                            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                            maxHeight: '400px', overflow: 'auto',
                                        }}>
                                            {selectedSummary.content}
                                        </pre>
                                    </div>
                                </div>
                            ) : (
                                <div className="card" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '300px', color: 'var(--text-tertiary)' }}>
                                    <div style={{ textAlign: 'center' }}>
                                        <div style={{ fontSize: '48px', marginBottom: '8px' }}>👈</div>
                                        <div>选择左侧的日期查看详细总结</div>
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}
