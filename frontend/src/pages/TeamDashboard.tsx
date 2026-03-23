import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../stores';

/* ────── API Functions ────── */

const API_BASE = '/api';

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
    const token = localStorage.getItem('token');
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
    const res = await fetch(`${API_BASE}${url}`, { ...options, headers });
    if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(error.detail || `HTTP ${res.status}`);
    }
    if (res.status === 204) return undefined as T;
    return res.json();
}

const teamApi = {
    // Tasks
    listTasks: (params?: Record<string, string>) => {
        const query = params ? '?' + new URLSearchParams(params).toString() : '';
        return request<any[]>(`/team/tasks${query}`);
    },
    createTask: (data: any) =>
        request<any>('/team/tasks', { method: 'POST', body: JSON.stringify(data) }),
    getTask: (id: string) =>
        request<any>(`/team/tasks/${id}`),
    updateTask: (id: string, data: any) =>
        request<any>(`/team/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    addSubtask: (parentId: string, data: any) =>
        request<any>(`/team/tasks/${parentId}/subtasks`, { method: 'POST', body: JSON.stringify(data) }),
    addLog: (taskId: string, content: string) =>
        request<any>(`/team/tasks/${taskId}/logs`, { method: 'POST', body: JSON.stringify({ content }) }),
    
    // Task decomposition by AI (calls the agent's actual LLM)
    decomposeTaskPreview: (agentId: string, task: { title: string; description: string }) =>
        request<{ subtasks: { title: string; description: string }[]; agent_name?: string }>(`/team/tasks/decompose-preview`, {
            method: 'POST',
            body: JSON.stringify({ agent_id: agentId, title: task.title, description: task.description }),
        }),
    
    // Create task with subtasks (after decomposition)
    createTaskWithSubtasks: (data: any) =>
        request<any>('/team/tasks/with-subtasks', { method: 'POST', body: JSON.stringify(data) }),
    
    // Review task result
    reviewTask: (taskId: string, action: string, feedback?: string) =>
        request<any>(`/team/tasks/${taskId}/review`, {
            method: 'POST',
            body: JSON.stringify({ action, feedback }),
        }),
    
    // Manually dispatch task
    dispatchTask: (taskId: string) =>
        request<any>(`/team/tasks/${taskId}/dispatch`, { method: 'POST' }),
    
    // Reports
    listReports: (params?: Record<string, string>) => {
        const query = params ? '?' + new URLSearchParams(params).toString() : '';
        return request<any[]>(`/team/reports/agents${query}`);
    },
    generateReport: (agentId: string, date?: string) => {
        const query = date ? `?target_date=${date}` : '';
        return request<any>(`/team/reports/agents/${agentId}/generate${query}`, { method: 'POST' });
    },
    confirmReport: (reportId: string, action: 'confirm' | 'reject', comment?: string) =>
        request<any>(`/team/reports/${reportId}/confirm`, {
            method: 'POST',
            body: JSON.stringify({ action, comment }),
        }),
    
    // Dashboard
    getDashboardStats: () =>
        request<any>('/team/dashboard/stats'),
    
    // Org
    getOrgMembers: () =>
        request<any[]>('/enterprise/org/members'),
    getBoundAgents: () =>
        request<any[]>('/bindings/'),
};

/* ────── Icons ────── */

const Icons = {
    tasks: (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="2" y="2" width="12" height="12" rx="2" />
            <path d="M5.5 8l2 2 3.5-3.5" />
        </svg>
    ),
    plus: (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
            <path d="M8 3v10M3 8h10" />
        </svg>
    ),
    report: (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 2h10a1 1 0 011 1v10a1 1 0 01-1 1H3a1 1 0 01-1-1V3a1 1 0 011-1z" />
            <path d="M5 6h6M5 9h4M5 12h2" />
        </svg>
    ),
    bot: (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="5" width="10" height="8" rx="2" />
            <circle cx="6" cy="9" r="1" fill="currentColor" stroke="none" />
            <circle cx="10" cy="9" r="1" fill="currentColor" stroke="none" />
            <path d="M8 2v3M6 2h4" />
        </svg>
    ),
    user: (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="8" cy="5.5" r="2.5" />
            <path d="M3 14v-1a4 4 0 018 0v1" />
        </svg>
    ),
    split: (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 2v4M8 6L4 10M8 6l4 4M4 10v4M12 10v4" />
        </svg>
    ),
    send: (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2 8l12-6-4 14-3-5-5-3z" />
        </svg>
    ),
    clock: (
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="8" cy="8" r="6" />
            <path d="M8 4.5V8l2.5 1.5" />
        </svg>
    ),
    check: (
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 8l4 4 6-6" />
        </svg>
    ),
};

/* ────── Helpers ────── */

const priorityColors: Record<string, string> = {
    urgent: 'var(--error)',
    high: 'var(--warning)',
    medium: 'var(--accent-primary)',
    low: 'var(--text-tertiary)',
};

const statusLabels: Record<string, { label: string; color: string }> = {
    pending: { label: '待处理', color: 'var(--text-tertiary)' },
    in_progress: { label: '进行中', color: 'var(--accent-primary)' },
    completed: { label: '已完成', color: 'var(--success)' },
    cancelled: { label: '已取消', color: 'var(--text-quaternary)' },
};

function formatDate(dateStr: string | null) {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
}

function timeAgo(dateStr: string) {
    const diff = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return '刚刚';
    if (mins < 60) return `${mins}分钟前`;
    const hours = Math.floor(mins / 60);
    if (hours < 24) return `${hours}小时前`;
    return `${Math.floor(hours / 24)}天前`;
}

/* ────── Create Task Modal with Decomposition Flow ────── */

interface Assignee {
    type: 'agent' | 'member';
    id: string;
    name: string;
    avatar?: string;
}

interface DecomposedSubtask {
    title: string;
    description: string;
    assignees: Assignee[];  // Multiple assignees allowed
}

interface CreateTaskModalProps {
    isOpen: boolean;
    onClose: () => void;
    onCreated: () => void;
    members: any[];
    boundAgents: any[];
}

type ModalStep = 'basic' | 'select_decomposer' | 'decomposing' | 'assign_subtasks' | 'direct_assign';

function CreateTaskModal({ isOpen, onClose, onCreated, members, boundAgents }: CreateTaskModalProps) {
    const [step, setStep] = useState<ModalStep>('basic');
    const [form, setForm] = useState({
        title: '',
        description: '',
        priority: 'medium',
        due_date: '',
        visibility: 'team',
    });
    const [needDecomposition, setNeedDecomposition] = useState(true);  // Default to decomposition flow
    const [selectedDecomposer, setSelectedDecomposer] = useState<string>('');  // Agent ID for decomposition
    const [decomposerName, setDecomposerName] = useState<string>('');  // Agent name that performed decomposition
    const [decomposedSubtasks, setDecomposedSubtasks] = useState<DecomposedSubtask[]>([]);
    const [directAssignees, setDirectAssignees] = useState<Assignee[]>([]);  // For direct assignment without decomposition
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');

    // All available assignees (agents + members)
    const allAgents: Assignee[] = boundAgents.map((b: any) => ({
        type: 'agent' as const,
        id: String(b.agent?.id || b.agent_id || b.id),
        name: b.agent?.name || b.agent_name || '数字员工',
        avatar: b.agent?.avatar_url || b.agent_avatar,
    }));
    
    const allMembers: Assignee[] = members.map((m: any) => ({
        type: 'member' as const,
        id: String(m.id),
        name: m.name,
        avatar: m.avatar_url,
    }));

    // Debug: log available assignees
    console.log('[CreateTaskModal] allAgents:', allAgents, 'allMembers:', allMembers, 'boundAgents raw:', boundAgents, 'members raw:', members);

    const resetForm = () => {
        setStep('basic');
        setForm({ title: '', description: '', priority: 'medium', due_date: '', visibility: 'team' });
        setNeedDecomposition(true);
        setSelectedDecomposer('');
        setDecomposerName('');
        setDecomposedSubtasks([]);
        setDirectAssignees([]);
        setError('');
    };

    const handleClose = () => {
        resetForm();
        onClose();
    };

    // Step 1: Basic info -> choose decomposition or direct
    const handleBasicNext = () => {
        if (!form.title.trim()) {
            setError('请输入任务标题');
            return;
        }
        setError('');
        if (needDecomposition) {
            setStep('select_decomposer');
        } else {
            setStep('direct_assign');
        }
    };

    // Step 2a: Select decomposer agent
    const handleStartDecompose = async () => {
        if (!selectedDecomposer) {
            setError('请选择一个数字员工来拆解任务');
            return;
        }
        setError('');
        setStep('decomposing');
        setLoading(true);
        
        try {
            // Call AI to decompose the task (this actually calls the agent's LLM!)
            const result = await teamApi.decomposeTaskPreview(selectedDecomposer, {
                title: form.title,
                description: form.description,
            });
            
            // Save the agent name that performed the decomposition
            if (result.agent_name) {
                setDecomposerName(result.agent_name);
            } else {
                // Fallback: find name from selected agent
                const agent = allAgents.find(a => a.id === selectedDecomposer);
                setDecomposerName(agent?.name || '数字员工');
            }
            
            // Initialize subtasks with empty assignees
            setDecomposedSubtasks(result.subtasks.map((st: any) => ({
                title: st.title,
                description: st.description || '',
                assignees: [],
            })));
            setStep('assign_subtasks');
        } catch (e: any) {
            setError(e.message || '任务拆解失败，请重试');
            setStep('select_decomposer');
        }
        setLoading(false);
    };

    // Toggle assignee for a subtask
    const toggleSubtaskAssignee = (subtaskIndex: number, assignee: Assignee) => {
        console.log('[toggleSubtaskAssignee] idx:', subtaskIndex, 'assignee:', assignee);
        setDecomposedSubtasks(prev => {
            const updated = prev.map((st, i) => {
                if (i !== subtaskIndex) return st;
                const current = st.assignees;
                const existingIdx = current.findIndex(a => a.type === assignee.type && a.id === assignee.id);
                const newAssignees = existingIdx >= 0
                    ? current.filter((_, j) => j !== existingIdx)
                    : [...current, assignee];
                console.log('[toggleSubtaskAssignee] newAssignees:', newAssignees);
                return { ...st, assignees: newAssignees };
            });
            return updated;
        });
    };

    // Toggle direct assignee
    const toggleDirectAssignee = (assignee: Assignee) => {
        setDirectAssignees(prev => {
            const existingIdx = prev.findIndex(a => a.type === assignee.type && a.id === assignee.id);
            if (existingIdx >= 0) {
                return prev.filter((_, i) => i !== existingIdx);
            } else {
                return [...prev, assignee];
            }
        });
    };

    // Final submit
    const handleFinalSubmit = async () => {
        setLoading(true);
        setError('');
        
        try {
            if (needDecomposition && decomposedSubtasks.length > 0) {
                // Debug: log what we're submitting
                console.log('[handleFinalSubmit] decomposedSubtasks:', JSON.stringify(decomposedSubtasks.map(st => ({
                    title: st.title,
                    assignees: st.assignees,
                }))));
                // Create main task with subtasks
                await teamApi.createTaskWithSubtasks({
                    ...form,
                    due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
                    decomposer_agent_id: selectedDecomposer,
                    subtasks: decomposedSubtasks.map(st => ({
                        title: st.title,
                        description: st.description,
                        assignees: st.assignees.map(a => ({
                            type: a.type,
                            id: a.id,
                        })),
                    })),
                });
            } else {
                // Create direct task
                if (directAssignees.length === 0) {
                    setError('请至少选择一个负责人');
                    setLoading(false);
                    return;
                }
                
                // Create a task for each assignee (or one task if single assignee)
                if (directAssignees.length === 1) {
                    const assignee = directAssignees[0];
                    await teamApi.createTask({
                        ...form,
                        due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
                        assignee_type: assignee.type,
                        assignee_agent_id: assignee.type === 'agent' ? assignee.id : '',
                        assignee_member_id: assignee.type === 'member' ? assignee.id : '',
                    });
                } else {
                    // Multiple assignees - create main task and subtasks for each
                    await teamApi.createTaskWithSubtasks({
                        ...form,
                        due_date: form.due_date ? new Date(form.due_date).toISOString() : null,
                        subtasks: directAssignees.map(a => ({
                            title: form.title,
                            description: form.description,
                            assignees: [{ type: a.type, id: a.id }],
                        })),
                    });
                }
            }
            
            onCreated();
            handleClose();
        } catch (e: any) {
            setError(e.message || '创建任务失败');
        }
        setLoading(false);
    };

    if (!isOpen) return null;

    return (
        <div 
            style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} 
            onClick={handleClose}
        >
            <div 
                style={{ background: 'var(--bg-primary)', borderRadius: '12px', width: '600px', maxHeight: '90vh', overflow: 'auto', padding: '24px', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }} 
                onClick={e => e.stopPropagation()}
            >
                {/* Header with step indicator */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
                    <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {step === 'basic' && <>{Icons.plus} 创建新任务</>}
                        {step === 'select_decomposer' && <>{Icons.bot} 选择拆解任务的数字员工</>}
                        {step === 'decomposing' && <>{Icons.split} AI 正在拆解任务...</>}
                        {step === 'assign_subtasks' && <>{Icons.user} 分配子任务负责人</>}
                        {step === 'direct_assign' && <>{Icons.user} 选择任务负责人</>}
                    </h3>
                    {step !== 'basic' && step !== 'decomposing' && (
                        <button 
                            className="btn btn-ghost" 
                            onClick={() => setStep(step === 'direct_assign' ? 'basic' : step === 'assign_subtasks' ? 'select_decomposer' : 'basic')}
                            style={{ fontSize: '12px' }}
                        >
                            ← 返回
                        </button>
                    )}
                </div>

                {/* Step indicator */}
                <div style={{ display: 'flex', gap: '8px', marginBottom: '20px' }}>
                    {['基本信息', needDecomposition ? '选择智能体' : '', needDecomposition ? '拆解任务' : '', '分配负责人'].filter(Boolean).map((label, idx) => {
                        const stepMap = needDecomposition 
                            ? ['basic', 'select_decomposer', 'decomposing', 'assign_subtasks']
                            : ['basic', 'direct_assign'];
                        const currentIdx = stepMap.indexOf(step);
                        const isActive = idx <= currentIdx;
                        const isCurrent = idx === currentIdx;
                        return (
                            <div key={idx} style={{ 
                                flex: 1, 
                                height: '3px', 
                                borderRadius: '2px',
                                background: isActive ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                                opacity: isCurrent ? 1 : 0.5,
                            }} />
                        );
                    })}
                </div>

                {error && (
                    <div style={{ padding: '10px 14px', borderRadius: '8px', background: 'rgba(255,80,80,0.1)', color: 'var(--error)', fontSize: '13px', marginBottom: '16px' }}>
                        {error}
                    </div>
                )}

                {/* Step: Basic Info */}
                {step === 'basic' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                        <div>
                            <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '4px', color: 'var(--text-secondary)' }}>任务标题 *</label>
                            <input
                                className="input"
                                value={form.title}
                                onChange={e => setForm({ ...form, title: e.target.value })}
                                placeholder="输入任务标题..."
                                style={{ width: '100%', fontSize: '14px' }}
                            />
                        </div>

                        <div>
                            <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '4px', color: 'var(--text-secondary)' }}>任务描述</label>
                            <textarea
                                className="input"
                                value={form.description}
                                onChange={e => setForm({ ...form, description: e.target.value })}
                                placeholder="详细描述任务内容，越详细越有利于 AI 拆解..."
                                style={{ width: '100%', minHeight: '100px', fontSize: '13px', resize: 'vertical' }}
                            />
                        </div>

                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                            <div>
                                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '4px', color: 'var(--text-secondary)' }}>优先级</label>
                                <select
                                    className="input"
                                    value={form.priority}
                                    onChange={e => setForm({ ...form, priority: e.target.value })}
                                    style={{ width: '100%' }}
                                >
                                    <option value="low">低</option>
                                    <option value="medium">中</option>
                                    <option value="high">高</option>
                                    <option value="urgent">紧急</option>
                                </select>
                            </div>
                            <div>
                                <label style={{ display: 'block', fontSize: '12px', fontWeight: 500, marginBottom: '4px', color: 'var(--text-secondary)' }}>截止日期</label>
                                <input
                                    type="date"
                                    className="input"
                                    value={form.due_date}
                                    onChange={e => setForm({ ...form, due_date: e.target.value })}
                                    style={{ width: '100%' }}
                                />
                            </div>
                        </div>

                        {/* Decomposition toggle */}
                        <div style={{ 
                            padding: '16px', 
                            background: 'var(--bg-secondary)', 
                            borderRadius: '10px',
                            border: needDecomposition ? '2px solid var(--accent-primary)' : '2px solid transparent',
                        }}>
                            <label style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={needDecomposition}
                                    onChange={e => setNeedDecomposition(e.target.checked)}
                                    style={{ marginTop: '2px' }}
                                />
                                <div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 500, fontSize: '14px' }}>
                                        {Icons.split} 让数字员工拆解任务
                                    </div>
                                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                                        选择一个数字员工（AI）来分析任务，自动拆解成多个可执行的子任务，然后您可以将子任务分配给不同的人员
                                    </div>
                                </div>
                            </label>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                            <button className="btn btn-secondary" onClick={handleClose}>取消</button>
                            <button className="btn btn-primary" onClick={handleBasicNext}>
                                下一步 →
                            </button>
                        </div>
                    </div>
                )}

                {/* Step: Select Decomposer Agent */}
                {step === 'select_decomposer' && (
                    <div>
                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                            请选择一个数字员工来拆解任务。该数字员工会分析任务内容，并将其拆分为多个可执行的子任务。
                        </p>
                        
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '300px', overflowY: 'auto' }}>
                            {allAgents.length === 0 ? (
                                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                                    <div style={{ fontSize: '24px', marginBottom: '8px' }}>{Icons.bot}</div>
                                    <div>暂无可用的数字员工</div>
                                    <div style={{ fontSize: '12px', marginTop: '4px' }}>请先在"我的数字员工"中绑定数字员工</div>
                                </div>
                            ) : (
                                allAgents.map(agent => (
                                    <div
                                        key={agent.id}
                                        onClick={() => setSelectedDecomposer(agent.id)}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '12px',
                                            padding: '12px 16px',
                                            borderRadius: '10px',
                                            background: selectedDecomposer === agent.id ? 'var(--accent-subtle)' : 'var(--bg-secondary)',
                                            border: selectedDecomposer === agent.id ? '2px solid var(--accent-primary)' : '2px solid transparent',
                                            cursor: 'pointer',
                                            transition: 'all 0.15s',
                                        }}
                                    >
                                        <div style={{
                                            width: '40px', height: '40px', borderRadius: '50%',
                                            background: 'var(--accent-primary)',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            overflow: 'hidden',
                                        }}>
                                            {agent.avatar ? (
                                                <img src={agent.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                            ) : (
                                                <span style={{ color: 'white' }}>{Icons.bot}</span>
                                            )}
                                        </div>
                                        <div style={{ flex: 1 }}>
                                            <div style={{ fontWeight: 500, fontSize: '14px' }}>{agent.name}</div>
                                            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>数字员工</div>
                                        </div>
                                        {selectedDecomposer === agent.id && (
                                            <span style={{ color: 'var(--accent-primary)' }}>{Icons.check}</span>
                                        )}
                                    </div>
                                ))
                            )}
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border-subtle)' }}>
                            <button className="btn btn-secondary" onClick={() => setStep('basic')}>返回</button>
                            <button 
                                className="btn btn-primary" 
                                onClick={handleStartDecompose}
                                disabled={!selectedDecomposer || loading}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                            >
                                {Icons.split} 开始拆解任务
                            </button>
                        </div>
                    </div>
                )}

                {/* Step: Decomposing */}
                {step === 'decomposing' && (
                    <div style={{ textAlign: 'center', padding: '60px 20px' }}>
                        <div style={{ 
                            width: '60px', height: '60px', borderRadius: '50%',
                            background: 'var(--accent-subtle)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            margin: '0 auto 20px',
                            animation: 'pulse 2s infinite',
                        }}>
                            <span style={{ fontSize: '24px' }}>{Icons.bot}</span>
                        </div>
                        <div style={{ fontSize: '16px', fontWeight: 500, marginBottom: '8px' }}>
                            <strong style={{ color: 'var(--accent-primary)' }}>
                                {allAgents.find(a => a.id === selectedDecomposer)?.name || '数字员工'}
                            </strong> 正在分析任务...
                        </div>
                        <div style={{ fontSize: '13px', color: 'var(--text-tertiary)' }}>
                            正在调用大模型将「{form.title}」拆解为可执行的子任务
                        </div>
                    </div>
                )}

                {/* Step: Assign Subtasks */}
                {step === 'assign_subtasks' && (
                    <div>
                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                            <strong style={{ color: 'var(--accent-primary)' }}>{decomposerName || '数字员工'}</strong> 已将任务拆解为 {decomposedSubtasks.length} 个子任务。请为每个子任务选择负责人（可多选数字员工或团队成员）。
                        </p>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', maxHeight: '400px', overflowY: 'auto', position: 'relative' }}>
                            {decomposedSubtasks.map((subtask, idx) => (
                                <div 
                                    key={idx}
                                    style={{ 
                                        padding: '16px', 
                                        background: 'var(--bg-secondary)', 
                                        borderRadius: '10px',
                                        border: '1px solid var(--border-subtle)',
                                        position: 'relative',
                                        zIndex: 1,
                                    }}
                                >
                                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px', marginBottom: '12px' }}>
                                        <span style={{ 
                                            width: '24px', height: '24px', borderRadius: '50%',
                                            background: 'var(--accent-primary)', color: 'white',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            fontSize: '12px', fontWeight: 600, flexShrink: 0,
                                        }}>
                                            {idx + 1}
                                        </span>
                                        <div style={{ flex: 1 }}>
                                            <div style={{ fontWeight: 500, fontSize: '14px' }}>{subtask.title}</div>
                                            {subtask.description && (
                                                <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                                                    {subtask.description}
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* Assignee selection */}
                                    <div style={{ marginLeft: '34px' }}>
                                        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>
                                            选择负责人（可多选）:
                                        </div>
                                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                            {allAgents.map(agent => {
                                                const isSelected = subtask.assignees.some(a => a.type === 'agent' && a.id === agent.id);
                                                return (
                                                    <button
                                                        type="button"
                                                        key={`agent-${agent.id}`}
                                                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleSubtaskAssignee(idx, agent); }}
                                                        style={{
                                                            display: 'inline-flex', alignItems: 'center', gap: '4px',
                                                            padding: '6px 12px', borderRadius: '16px',
                                                            background: isSelected ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                                                            color: isSelected ? 'white' : 'var(--text-primary)',
                                                            border: isSelected ? '2px solid var(--accent-primary)' : '2px solid transparent',
                                                            cursor: 'pointer',
                                                            fontSize: '12px',
                                                            userSelect: 'none',
                                                            outline: 'none',
                                                        }}
                                                    >
                                                        {Icons.bot}
                                                        {agent.name}
                                                        {isSelected && <span style={{ marginLeft: '2px' }}>✓</span>}
                                                    </button>
                                                );
                                            })}
                                            {allMembers.map(member => {
                                                const isSelected = subtask.assignees.some(a => a.type === 'member' && a.id === member.id);
                                                return (
                                                    <button
                                                        type="button"
                                                        key={`member-${member.id}`}
                                                        onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleSubtaskAssignee(idx, member); }}
                                                        style={{
                                                            display: 'inline-flex', alignItems: 'center', gap: '4px',
                                                            padding: '6px 12px', borderRadius: '16px',
                                                            background: isSelected ? 'var(--accent-primary)' : 'var(--bg-tertiary)',
                                                            color: isSelected ? 'white' : 'var(--text-primary)',
                                                            border: isSelected ? '2px solid var(--accent-primary)' : '2px solid transparent',
                                                            cursor: 'pointer',
                                                            fontSize: '12px',
                                                            userSelect: 'none',
                                                            outline: 'none',
                                                        }}
                                                    >
                                                        {Icons.user}
                                                        {member.name}
                                                        {isSelected && <span style={{ marginLeft: '2px' }}>✓</span>}
                                                    </button>
                                                );
                                            })}
                                            {allAgents.length === 0 && allMembers.length === 0 && (
                                                <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', padding: '8px' }}>
                                                    暂无可分配的人员，请先绑定数字员工或添加团队成员
                                                </div>
                                            )}
                                        </div>
                                        {/* Show selected assignees summary */}
                                        {subtask.assignees.length > 0 && (
                                            <div style={{ marginTop: '8px', fontSize: '11px', color: 'var(--accent-primary)' }}>
                                                已选: {subtask.assignees.map(a => a.name).join(', ')}
                                            </div>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border-subtle)' }}>
                            <button className="btn btn-secondary" onClick={() => setStep('select_decomposer')}>返回</button>
                            <button 
                                className="btn btn-primary" 
                                onClick={handleFinalSubmit}
                                disabled={loading}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                            >
                                {loading ? '创建中...' : <>{Icons.send} 创建并分发任务</>}
                            </button>
                        </div>
                    </div>
                )}

                {/* Step: Direct Assign (no decomposition) */}
                {step === 'direct_assign' && (
                    <div>
                        <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                            选择任务的负责人。您可以选择多个数字员工或团队成员，任务将同时分配给所有选中的人。
                        </p>

                        {/* Agents section */}
                        {allAgents.length > 0 && (
                            <div style={{ marginBottom: '16px' }}>
                                <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    {Icons.bot} 数字员工
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                                    {allAgents.map(agent => {
                                        const isSelected = directAssignees.some(a => a.type === 'agent' && a.id === agent.id);
                                        return (
                                            <button
                                                key={agent.id}
                                                onClick={() => toggleDirectAssignee(agent)}
                                                style={{
                                                    display: 'flex', alignItems: 'center', gap: '8px',
                                                    padding: '8px 14px', borderRadius: '8px',
                                                    background: isSelected ? 'var(--accent-subtle)' : 'var(--bg-secondary)',
                                                    border: isSelected ? '2px solid var(--accent-primary)' : '2px solid var(--border-subtle)',
                                                    cursor: 'pointer', transition: 'all 0.15s',
                                                }}
                                            >
                                                <div style={{
                                                    width: '28px', height: '28px', borderRadius: '50%',
                                                    background: 'var(--accent-primary)',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    overflow: 'hidden',
                                                }}>
                                                    {agent.avatar ? (
                                                        <img src={agent.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                                    ) : (
                                                        <span style={{ color: 'white', fontSize: '12px' }}>{Icons.bot}</span>
                                                    )}
                                                </div>
                                                <span style={{ fontSize: '13px' }}>{agent.name}</span>
                                                {isSelected && <span style={{ color: 'var(--accent-primary)' }}>{Icons.check}</span>}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {/* Members section */}
                        {allMembers.length > 0 && (
                            <div>
                                <div style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    {Icons.user} 团队成员
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', maxHeight: '200px', overflowY: 'auto' }}>
                                    {allMembers.map(member => {
                                        const isSelected = directAssignees.some(a => a.type === 'member' && a.id === member.id);
                                        return (
                                            <button
                                                key={member.id}
                                                onClick={() => toggleDirectAssignee(member)}
                                                style={{
                                                    display: 'flex', alignItems: 'center', gap: '8px',
                                                    padding: '8px 14px', borderRadius: '8px',
                                                    background: isSelected ? 'var(--accent-subtle)' : 'var(--bg-secondary)',
                                                    border: isSelected ? '2px solid var(--accent-primary)' : '2px solid var(--border-subtle)',
                                                    cursor: 'pointer', transition: 'all 0.15s',
                                                }}
                                            >
                                                <div style={{
                                                    width: '28px', height: '28px', borderRadius: '50%',
                                                    background: 'var(--bg-tertiary)',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    overflow: 'hidden',
                                                }}>
                                                    {member.avatar ? (
                                                        <img src={member.avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                                                    ) : (
                                                        <span style={{ fontSize: '12px' }}>{Icons.user}</span>
                                                    )}
                                                </div>
                                                <span style={{ fontSize: '13px' }}>{member.name}</span>
                                                {isSelected && <span style={{ color: 'var(--accent-primary)' }}>{Icons.check}</span>}
                                            </button>
                                        );
                                    })}
                                </div>
                            </div>
                        )}

                        {allAgents.length === 0 && allMembers.length === 0 && (
                            <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                                暂无可分配的人员
                            </div>
                        )}

                        {/* Selected summary */}
                        {directAssignees.length > 0 && (
                            <div style={{ marginTop: '16px', padding: '12px', background: 'var(--bg-tertiary)', borderRadius: '8px' }}>
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px' }}>
                                    已选择 {directAssignees.length} 个负责人:
                                </div>
                                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                                    {directAssignees.map(a => (
                                        <span 
                                            key={`${a.type}-${a.id}`}
                                            style={{ 
                                                padding: '2px 8px', 
                                                borderRadius: '10px', 
                                                background: 'var(--accent-subtle)', 
                                                fontSize: '12px',
                                                display: 'flex', alignItems: 'center', gap: '4px',
                                            }}
                                        >
                                            {a.type === 'agent' ? Icons.bot : Icons.user}
                                            {a.name}
                                        </span>
                                    ))}
                                </div>
                            </div>
                        )}

                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px', paddingTop: '16px', borderTop: '1px solid var(--border-subtle)' }}>
                            <button className="btn btn-secondary" onClick={() => setStep('basic')}>返回</button>
                            <button 
                                className="btn btn-primary" 
                                onClick={handleFinalSubmit}
                                disabled={loading || directAssignees.length === 0}
                                style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                            >
                                {loading ? '创建中...' : <>{Icons.send} 创建任务</>}
                            </button>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

/* ────── Task Card ────── */

function TaskCard({ task, onClick }: { task: any; onClick: () => void }) {
    const status = statusLabels[task.status] || statusLabels.pending;

    return (
        <div
            onClick={onClick}
            style={{
                padding: '14px 16px',
                background: 'var(--bg-secondary)',
                borderRadius: '10px',
                border: '1px solid var(--border-subtle)',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
            }}
            onMouseEnter={e => {
                e.currentTarget.style.borderColor = 'var(--accent-primary)';
                e.currentTarget.style.transform = 'translateY(-1px)';
            }}
            onMouseLeave={e => {
                e.currentTarget.style.borderColor = 'var(--border-subtle)';
                e.currentTarget.style.transform = 'translateY(0)';
            }}
        >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '10px' }}>
                {/* Priority dot */}
                <span style={{
                    width: '8px', height: '8px', borderRadius: '50%',
                    background: priorityColors[task.priority] || priorityColors.medium,
                    marginTop: '6px', flexShrink: 0,
                }} />

                <div style={{ flex: 1, minWidth: 0 }}>
                    {/* Title */}
                    <div style={{ fontWeight: 500, fontSize: '14px', marginBottom: '4px' }}>{task.title}</div>

                    {/* Meta */}
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', fontSize: '12px', color: 'var(--text-tertiary)' }}>
                        {/* Status */}
                        <span style={{
                            padding: '2px 8px', borderRadius: '10px',
                            background: status.color + '20', color: status.color,
                            fontWeight: 500,
                        }}>
                            {status.label}
                        </span>

                        {/* Assignee */}
                        {task.assignee_name && (
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                {task.assignee_type === 'agent' ? Icons.bot : Icons.user}
                                {task.assignee_name}
                            </span>
                        )}

                        {/* Due date */}
                        {task.due_date && (
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                {Icons.clock}
                                {formatDate(task.due_date)}
                            </span>
                        )}

                        {/* Subtasks count */}
                        {task.subtasks_count > 0 && (
                            <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                                {Icons.split}
                                {task.subtasks_count} 子任务
                            </span>
                        )}
                    </div>

                    {/* Progress bar */}
                    {task.progress_percent > 0 && (
                        <div style={{ marginTop: '8px', height: '4px', background: 'var(--bg-tertiary)', borderRadius: '2px', overflow: 'hidden' }}>
                            <div style={{
                                height: '100%',
                                width: `${task.progress_percent}%`,
                                background: task.progress_percent >= 100 ? 'var(--success)' : 'var(--accent-primary)',
                                transition: 'width 0.3s',
                            }} />
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

/* ────── Task Detail Panel ────── */

function TaskDetailPanel({ task, onClose, onUpdate }: { task: any; onClose: () => void; onUpdate: () => void }) {
    const [newLog, setNewLog] = useState('');
    const [updating, setUpdating] = useState(false);
    const [reviewFeedback, setReviewFeedback] = useState('');
    const [showReviewPanel, setShowReviewPanel] = useState(false);
    const [dispatching, setDispatching] = useState(false);
    const status = statusLabels[task.status] || statusLabels.pending;

    // Check if task needs review (agent task with progress >= 90%)
    const needsReview = task.assignee_type === 'agent' && task.progress_percent >= 90 && task.status !== 'completed';
    // Check if task is being executed by an agent
    const isAgentExecuting = task.assignee_type === 'agent' && task.status === 'in_progress' && task.progress_percent < 90;
    // Check if task can be manually dispatched
    const canDispatch = (task.assignee_agent_id || task.assignee_member_id) && task.status === 'pending';

    const handleStatusChange = async (newStatus: string) => {
        setUpdating(true);
        try {
            await teamApi.updateTask(task.id, { status: newStatus });
            onUpdate();
        } catch (e) {
            console.error(e);
        }
        setUpdating(false);
    };

    const handleAddLog = async () => {
        if (!newLog.trim()) return;
        try {
            await teamApi.addLog(task.id, newLog);
            setNewLog('');
            onUpdate();
        } catch (e) {
            console.error(e);
        }
    };

    const handleReview = async (action: string) => {
        setUpdating(true);
        try {
            await teamApi.reviewTask(task.id, action, reviewFeedback || undefined);
            setReviewFeedback('');
            setShowReviewPanel(false);
            onUpdate();
        } catch (e) {
            console.error(e);
        }
        setUpdating(false);
    };

    const handleDispatch = async () => {
        setDispatching(true);
        try {
            await teamApi.dispatchTask(task.id);
            onUpdate();
        } catch (e) {
            console.error(e);
        }
        setDispatching(false);
    };

    return (
        <div style={{
            position: 'fixed', top: 0, right: 0, bottom: 0, width: '520px',
            background: 'var(--bg-primary)', borderLeft: '1px solid var(--border-subtle)',
            zIndex: 9999, display: 'flex', flexDirection: 'column',
            boxShadow: '-4px 0 24px rgba(0,0,0,0.15)',
        }}>
            {/* Header */}
            <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border-subtle)', display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{
                    width: '10px', height: '10px', borderRadius: '50%',
                    background: priorityColors[task.priority],
                }} />
                <h3 style={{ margin: 0, flex: 1, fontSize: '15px', fontWeight: 600 }}>{task.title}</h3>
                <button className="btn btn-ghost" onClick={onClose} style={{ padding: '4px 8px' }}>✕</button>
            </div>

            {/* Content */}
            <div style={{ flex: 1, overflowY: 'auto', padding: '20px' }}>
                {/* Execution status banner */}
                {isAgentExecuting && (
                    <div style={{
                        padding: '12px 16px', borderRadius: '10px', marginBottom: '16px',
                        background: 'linear-gradient(135deg, rgba(99,102,241,0.1), rgba(147,51,234,0.1))',
                        border: '1px solid rgba(99,102,241,0.3)',
                        display: 'flex', alignItems: 'center', gap: '10px',
                    }}>
                        <div style={{
                            width: '32px', height: '32px', borderRadius: '50%',
                            background: 'var(--accent-primary)',
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            animation: 'pulse 2s infinite',
                        }}>
                            <span style={{ color: 'white', fontSize: '14px' }}>{Icons.bot}</span>
                        </div>
                        <div style={{ flex: 1 }}>
                            <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--accent-primary)' }}>
                                数字员工正在执行任务...
                            </div>
                            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                                执行完成后将通知您检阅结果
                            </div>
                        </div>
                    </div>
                )}

                {/* Review needed banner */}
                {needsReview && !showReviewPanel && (
                    <div style={{
                        padding: '14px 16px', borderRadius: '10px', marginBottom: '16px',
                        background: 'linear-gradient(135deg, rgba(34,197,94,0.1), rgba(16,185,129,0.1))',
                        border: '1px solid rgba(34,197,94,0.3)',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '10px' }}>
                            <span style={{ fontSize: '18px' }}>✅</span>
                            <div style={{ flex: 1 }}>
                                <div style={{ fontSize: '13px', fontWeight: 500, color: 'var(--success)' }}>
                                    数字员工已完成执行，等待检阅
                                </div>
                                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '2px' }}>
                                    请查看执行结果并决定是否通过
                                </div>
                            </div>
                        </div>
                        <div style={{ display: 'flex', gap: '8px' }}>
                            <button
                                className="btn btn-primary"
                                onClick={() => setShowReviewPanel(true)}
                                style={{ fontSize: '12px', padding: '6px 14px' }}
                            >
                                开始检阅
                            </button>
                        </div>
                    </div>
                )}

                {/* Review panel */}
                {showReviewPanel && (
                    <div style={{
                        padding: '16px', borderRadius: '10px', marginBottom: '16px',
                        background: 'var(--bg-secondary)',
                        border: '2px solid var(--accent-primary)',
                    }}>
                        <div style={{ fontSize: '13px', fontWeight: 500, marginBottom: '12px' }}>检阅执行结果</div>
                        <textarea
                            className="input"
                            value={reviewFeedback}
                            onChange={e => setReviewFeedback(e.target.value)}
                            placeholder="输入检阅意见或修改建议（可选）..."
                            style={{ width: '100%', minHeight: '60px', fontSize: '12px', resize: 'vertical', marginBottom: '12px' }}
                        />
                        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                            <button
                                className="btn btn-primary"
                                onClick={() => handleReview('approve')}
                                disabled={updating}
                                style={{ fontSize: '12px', padding: '6px 14px', background: 'var(--success)' }}
                            >
                                ✅ 通过
                            </button>
                            <button
                                className="btn btn-secondary"
                                onClick={() => handleReview('revise')}
                                disabled={updating}
                                style={{ fontSize: '12px', padding: '6px 14px' }}
                            >
                                📝 通过（附修改意见）
                            </button>
                            <button
                                className="btn btn-secondary"
                                onClick={() => handleReview('reject')}
                                disabled={updating}
                                style={{ fontSize: '12px', padding: '6px 14px', borderColor: 'var(--error)', color: 'var(--error)' }}
                            >
                                ❌ 打回重做
                            </button>
                            <button
                                className="btn btn-ghost"
                                onClick={() => setShowReviewPanel(false)}
                                style={{ fontSize: '12px', padding: '6px 14px' }}
                            >
                                取消
                            </button>
                        </div>
                    </div>
                )}

                {/* Status & Actions */}
                <div style={{ marginBottom: '20px' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>状态</div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                        {['pending', 'in_progress', 'completed'].map(s => (
                            <button
                                key={s}
                                className={`btn ${task.status === s ? 'btn-primary' : 'btn-secondary'}`}
                                onClick={() => handleStatusChange(s)}
                                disabled={updating}
                                style={{ fontSize: '12px', padding: '6px 12px' }}
                            >
                                {statusLabels[s]?.label}
                            </button>
                        ))}
                        {canDispatch && (
                            <button
                                className="btn btn-secondary"
                                onClick={handleDispatch}
                                disabled={dispatching}
                                style={{ fontSize: '12px', padding: '6px 12px', display: 'flex', alignItems: 'center', gap: '4px' }}
                            >
                                {Icons.send} {dispatching ? '分发中...' : '手动分发'}
                            </button>
                        )}
                    </div>
                </div>

                {/* Description */}
                {task.description && (
                    <div style={{ marginBottom: '20px' }}>
                        <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>描述</div>
                        <div style={{ fontSize: '13px', lineHeight: '1.6', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap' }}>
                            {task.description}
                        </div>
                    </div>
                )}

                {/* Info */}
                <div style={{ marginBottom: '20px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={{ padding: '10px 12px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>负责人</div>
                        <div style={{ fontSize: '13px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            {task.assignee_type === 'agent' ? Icons.bot : Icons.user}
                            {task.assignee_name || '-'}
                        </div>
                    </div>
                    <div style={{ padding: '10px 12px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>截止日期</div>
                        <div style={{ fontSize: '13px' }}>{task.due_date ? formatDate(task.due_date) : '-'}</div>
                    </div>
                    <div style={{ padding: '10px 12px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>创建者</div>
                        <div style={{ fontSize: '13px' }}>{task.creator_name || '-'}</div>
                    </div>
                    <div style={{ padding: '10px 12px', background: 'var(--bg-secondary)', borderRadius: '8px' }}>
                        <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>进度</div>
                        <div style={{ fontSize: '13px' }}>{task.progress_percent}%</div>
                    </div>
                </div>

                {/* Progress bar */}
                {task.progress_percent > 0 && (
                    <div style={{ marginBottom: '20px' }}>
                        <div style={{
                            height: '6px', background: 'var(--bg-tertiary)', borderRadius: '3px', overflow: 'hidden',
                        }}>
                            <div style={{
                                height: '100%',
                                width: `${task.progress_percent}%`,
                                background: task.progress_percent >= 100 ? 'var(--success)' : task.progress_percent >= 90 ? '#f59e0b' : 'var(--accent-primary)',
                                transition: 'width 0.3s',
                            }} />
                        </div>
                        {task.progress_note && (
                            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                                {task.progress_note}
                            </div>
                        )}
                    </div>
                )}

                {/* Subtasks */}
                {task.subtasks && task.subtasks.length > 0 && (
                    <div style={{ marginBottom: '20px' }}>
                        <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            {Icons.split} 子任务 ({task.subtasks.length})
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                            {task.subtasks.map((st: any) => {
                                const stStatus = statusLabels[st.status] || statusLabels.pending;
                                return (
                                    <div key={st.id} style={{
                                        padding: '10px 12px', background: 'var(--bg-secondary)', borderRadius: '8px',
                                        border: '1px solid var(--border-subtle)',
                                    }}>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px' }}>
                                            <span style={{
                                                width: '8px', height: '8px', borderRadius: '50%',
                                                background: stStatus.color,
                                            }} />
                                            <span style={{ flex: 1, fontWeight: 500 }}>{st.title}</span>
                                            <span style={{
                                                padding: '2px 6px', borderRadius: '8px', fontSize: '10px',
                                                background: stStatus.color + '20', color: stStatus.color,
                                            }}>
                                                {stStatus.label}
                                            </span>
                                        </div>
                                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginTop: '4px', marginLeft: '16px' }}>
                                            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                                {st.assignee_type === 'agent' ? Icons.bot : Icons.user}
                                                {st.assignee_name || '未分配'}
                                            </span>
                                            {st.progress_percent > 0 && (
                                                <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                                                    {st.progress_percent}%
                                                </span>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                )}

                {/* Logs */}
                <div>
                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>进展记录</div>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                        <input
                            className="input"
                            value={newLog}
                            onChange={e => setNewLog(e.target.value)}
                            placeholder="添加进展记录..."
                            style={{ flex: 1, fontSize: '13px' }}
                            onKeyDown={e => e.key === 'Enter' && handleAddLog()}
                        />
                        <button className="btn btn-primary" onClick={handleAddLog} style={{ padding: '8px 12px' }}>添加</button>
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                        {(task.logs || []).map((log: any) => (
                            <div key={log.id} style={{
                                padding: '10px 12px', borderRadius: '6px',
                                background: log.created_by_agent_id ? 'linear-gradient(135deg, var(--bg-secondary), rgba(99,102,241,0.05))' : 'var(--bg-secondary)',
                                border: log.created_by_agent_id ? '1px solid rgba(99,102,241,0.15)' : 'none',
                            }}>
                                {log.created_by_agent_id && (
                                    <div style={{ fontSize: '10px', color: 'var(--accent-primary)', marginBottom: '4px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                        {Icons.bot} 数字员工
                                    </div>
                                )}
                                <div style={{ fontSize: '13px', marginBottom: '4px', whiteSpace: 'pre-wrap', lineHeight: '1.5' }}>{log.content}</div>
                                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                                    {log.created_at ? timeAgo(log.created_at) : '-'}
                                </div>
                            </div>
                        ))}
                        {(!task.logs || task.logs.length === 0) && (
                            <div style={{ textAlign: 'center', padding: '20px', color: 'var(--text-tertiary)', fontSize: '13px' }}>
                                暂无进展记录
                            </div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}

/* ────── Report Card ────── */

function ReportCard({ report }: { report: any }) {
    const [expanded, setExpanded] = useState(false);

    return (
        <div style={{
            padding: '16px',
            background: 'var(--bg-secondary)',
            borderRadius: '10px',
            border: '1px solid var(--border-subtle)',
        }}>
            {/* Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                <div style={{
                    width: '36px', height: '36px', borderRadius: '50%',
                    background: 'var(--accent-subtle)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: 'var(--accent-primary)',
                }}>
                    {report.agent_avatar ? (
                        <img src={report.agent_avatar} alt="" style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover' }} />
                    ) : (
                        Icons.bot
                    )}
                </div>
                <div style={{ flex: 1 }}>
                    <div style={{ fontWeight: 500, fontSize: '14px' }}>{report.agent_name || '数字员工'}</div>
                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                        {report.report_date ? new Date(report.report_date).toLocaleDateString('zh-CN') : '-'}
                        {report.report_status && (
                            <span style={{
                                marginLeft: '8px', padding: '1px 6px', borderRadius: '4px',
                                fontSize: '10px', fontWeight: 500,
                                background: report.report_status === 'published' ? '#22c55e20' : report.report_status === 'draft' ? '#eab30820' : '#6366f120',
                                color: report.report_status === 'published' ? '#22c55e' : report.report_status === 'draft' ? '#eab308' : '#6366f1',
                            }}>
                                {report.report_status === 'published' ? '已发布' : report.report_status === 'draft' ? '草稿' : report.report_status}
                            </span>
                        )}
                    </div>
                </div>
                <button
                    className="btn btn-ghost"
                    onClick={() => setExpanded(!expanded)}
                    style={{ fontSize: '12px' }}
                >
                    {expanded ? '收起' : '展开'}
                </button>
            </div>

            {/* Summary */}
            <div style={{ fontSize: '13px', color: 'var(--text-secondary)', lineHeight: '1.6' }}>
                {report.summary || '暂无工作总结'}
            </div>

            {/* Stats */}
            <div style={{ display: 'flex', gap: '16px', marginTop: '12px', paddingTop: '12px', borderTop: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-tertiary)' }}>
                    {Icons.check} <span style={{ color: 'var(--success)', fontWeight: 500 }}>{report.tasks_completed_count || 0}</span> 完成
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-tertiary)' }}>
                    {Icons.clock} <span style={{ color: 'var(--accent-primary)', fontWeight: 500 }}>{report.tasks_in_progress_count || 0}</span> 进行中
                </div>
                {report.confirmed_by_name && (
                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                        确认人：{report.confirmed_by_name}
                        {report.confirmed_at && ` · ${new Date(report.confirmed_at).toLocaleString('zh-CN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}`}
                    </div>
                )}
            </div>

            {/* Expanded details */}
            {expanded && (
                <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid var(--border-subtle)' }}>
                    {/* Completed tasks */}
                    {report.completed_tasks && report.completed_tasks.length > 0 && (
                        <div style={{ marginBottom: '12px' }}>
                            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '6px' }}>已完成任务</div>
                            {report.completed_tasks.map((t: any, i: number) => (
                                <div key={i} style={{ fontSize: '13px', padding: '4px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <span style={{ color: 'var(--success)' }}>{Icons.check}</span>
                                    {t.title}
                                </div>
                            ))}
                        </div>
                    )}

                    {/* In progress tasks */}
                    {report.in_progress_tasks && report.in_progress_tasks.length > 0 && (
                        <div style={{ marginBottom: '12px' }}>
                            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '6px' }}>进行中任务</div>
                            {report.in_progress_tasks.map((t: any, i: number) => (
                                <div key={i} style={{ fontSize: '13px', padding: '4px 0', display: 'flex', alignItems: 'center', gap: '6px' }}>
                                    <span style={{ color: 'var(--accent-primary)' }}>{Icons.clock}</span>
                                    {t.title}
                                </div>
                            ))}
                        </div>
                    )}

                    {/* Highlights */}
                    {report.highlights && report.highlights.length > 0 && (
                        <div>
                            <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '6px' }}>亮点</div>
                            {report.highlights.map((h: string, i: number) => (
                                <div key={i} style={{ fontSize: '13px', padding: '4px 8px', background: 'var(--bg-tertiary)', borderRadius: '4px', marginBottom: '4px' }}>
                                    ⭐ {h}
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/* ────── Main Component ────── */

export default function TeamDashboard() {
    const { t } = useTranslation();
    const navigate = useNavigate();
    const queryClient = useQueryClient();
    const { user } = useAuthStore();

    const [activeTab, setActiveTab] = useState<'tasks' | 'reports'>('tasks');
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
    const [taskFilter, setTaskFilter] = useState<'all' | 'created' | 'assigned'>('all');
    const [reportFilter, setReportFilter] = useState<'published' | 'all'>('published');

    // Fetch data
    const { data: stats } = useQuery({
        queryKey: ['team-stats'],
        queryFn: () => teamApi.getDashboardStats(),
    });

    const { data: tasks = [], refetch: refetchTasks } = useQuery({
        queryKey: ['team-tasks', taskFilter],
        queryFn: () => {
            const params: Record<string, string> = {};
            if (taskFilter === 'created') params.created_by_me = 'true';
            if (taskFilter === 'assigned') params.assigned_to_me = 'true';
            return teamApi.listTasks(params);
        },
    });

    const { data: selectedTask, refetch: refetchSelectedTask } = useQuery({
        queryKey: ['team-task', selectedTaskId],
        queryFn: () => selectedTaskId ? teamApi.getTask(selectedTaskId) : null,
        enabled: !!selectedTaskId,
        // Auto-refresh every 5s when agent is executing
        refetchInterval: (query) => {
            const d = query.state.data;
            return d?.status === 'in_progress' && d?.assignee_type === 'agent' ? 5000 : false;
        },
    });

    const { data: reports = [] } = useQuery({
        queryKey: ['team-reports', reportFilter],
        queryFn: () => {
            const params: Record<string, string> = {};
            if (reportFilter === 'published') params.report_status = 'published';
            return teamApi.listReports(params);
        },
        enabled: activeTab === 'reports',
    });

    const { data: members = [] } = useQuery({
        queryKey: ['org-members'],
        queryFn: () => teamApi.getOrgMembers(),
    });

    const { data: boundAgents = [] } = useQuery({
        queryKey: ['bound-agents'],
        queryFn: () => teamApi.getBoundAgents(),
    });

    return (
        <div>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
                <div>
                    <h1 style={{ fontSize: '20px', fontWeight: 600, margin: 0, marginBottom: '4px' }}>
                        团队协作中心
                    </h1>
                    <p style={{ fontSize: '13px', color: 'var(--text-tertiary)', margin: 0 }}>
                        管理团队任务、查看数字员工工作日报
                    </p>
                </div>
                <button
                    className="btn btn-primary"
                    onClick={() => setShowCreateModal(true)}
                    style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                    {Icons.plus} 创建任务
                </button>
            </div>

            {/* Stats Cards */}
            <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(4, 1fr)',
                gap: '12px',
                marginBottom: '24px',
            }}>
                <div style={{ padding: '16px', background: 'var(--bg-secondary)', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>待处理任务</div>
                    <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {stats?.tasks_by_status?.pending || 0}
                    </div>
                </div>
                <div style={{ padding: '16px', background: 'var(--bg-secondary)', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>进行中任务</div>
                    <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--accent-primary)' }}>
                        {stats?.tasks_by_status?.in_progress || 0}
                    </div>
                </div>
                <div style={{ padding: '16px', background: 'var(--bg-secondary)', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>已完成任务</div>
                    <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--success)' }}>
                        {stats?.tasks_by_status?.completed || 0}
                    </div>
                </div>
                <div style={{ padding: '16px', background: 'var(--bg-secondary)', borderRadius: '10px', border: '1px solid var(--border-subtle)' }}>
                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '4px' }}>绑定的数字员工</div>
                    <div style={{ fontSize: '24px', fontWeight: 600, color: 'var(--text-primary)' }}>
                        {stats?.bound_agents_count || 0}
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <div style={{ display: 'flex', gap: '4px', marginBottom: '16px', padding: '4px', background: 'var(--bg-secondary)', borderRadius: '8px', width: 'fit-content' }}>
                <button
                    className={`btn ${activeTab === 'tasks' ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setActiveTab('tasks')}
                    style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px' }}
                >
                    {Icons.tasks} 任务管理
                </button>
                <button
                    className={`btn ${activeTab === 'reports' ? 'btn-primary' : 'btn-ghost'}`}
                    onClick={() => setActiveTab('reports')}
                    style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 16px' }}
                >
                    {Icons.report} 工作日报
                </button>
            </div>

            {/* Content */}
            {activeTab === 'tasks' ? (
                <div>
                    {/* Task Filters */}
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                        {[
                            { key: 'all', label: '全部任务' },
                            { key: 'created', label: '我创建的' },
                            { key: 'assigned', label: '分配给我的' },
                        ].map(f => (
                            <button
                                key={f.key}
                                className={`btn ${taskFilter === f.key ? 'btn-secondary' : 'btn-ghost'}`}
                                onClick={() => setTaskFilter(f.key as any)}
                                style={{ fontSize: '12px', padding: '6px 12px' }}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>

                    {/* Task List */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                        {tasks.length === 0 ? (
                            <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-tertiary)' }}>
                                <div style={{ fontSize: '32px', marginBottom: '12px' }}>{Icons.tasks}</div>
                                <div style={{ fontSize: '14px', marginBottom: '8px' }}>暂无任务</div>
                                <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>
                                    {Icons.plus} 创建第一个任务
                                </button>
                            </div>
                        ) : (
                            tasks.map(task => (
                                <TaskCard
                                    key={task.id}
                                    task={task}
                                    onClick={() => setSelectedTaskId(task.id)}
                                />
                            ))
                        )}
                    </div>
                </div>
            ) : (
                <div>
                    {/* Report Filters */}
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
                        {[
                            { key: 'published', label: '已发布' },
                            { key: 'all', label: '全部' },
                        ].map(f => (
                            <button
                                key={f.key}
                                className={`btn ${reportFilter === f.key ? 'btn-secondary' : 'btn-ghost'}`}
                                onClick={() => setReportFilter(f.key as any)}
                                style={{ fontSize: '12px', padding: '6px 12px' }}
                            >
                                {f.label}
                            </button>
                        ))}
                    </div>

                    {/* Reports */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                        {reports.length === 0 ? (
                            <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-tertiary)' }}>
                                <div style={{ fontSize: '32px', marginBottom: '12px' }}>{Icons.report}</div>
                                <div style={{ fontSize: '14px' }}>暂无工作日报</div>
                                <div style={{ fontSize: '12px', marginTop: '4px' }}>
                                    {reportFilter === 'published'
                                        ? '数字员工的日报经绑定人确认后会出现在这里'
                                        : '数字员工的工作日报会在每日结束时自动生成'}
                                </div>
                            </div>
                        ) : (
                            reports.map(report => (
                                <ReportCard key={report.id} report={report} />
                            ))
                        )}
                    </div>
                </div>
            )}

            {/* Create Task Modal */}
            <CreateTaskModal
                isOpen={showCreateModal}
                onClose={() => setShowCreateModal(false)}
                onCreated={() => {
                    refetchTasks();
                    queryClient.invalidateQueries({ queryKey: ['team-stats'] });
                }}
                members={members}
                boundAgents={boundAgents}
            />

            {/* Task Detail Panel */}
            {selectedTask && (
                <>
                    <div
                        style={{ position: 'fixed', inset: 0, zIndex: 9998, background: 'rgba(0,0,0,0.3)' }}
                        onClick={() => setSelectedTaskId(null)}
                    />
                    <TaskDetailPanel
                        task={selectedTask}
                        onClose={() => setSelectedTaskId(null)}
                        onUpdate={() => {
                            refetchSelectedTask();
                            refetchTasks();
                            queryClient.invalidateQueries({ queryKey: ['team-stats'] });
                        }}
                    />
                </>
            )}
        </div>
    );
}
