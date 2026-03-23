import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { opportunityApi } from '../services/api';

const STAGE_OPTIONS = [
    { value: 'initial_contact', label: '初步接触', color: '#6366f1' },
    { value: 'demand_confirmed', label: '需求确认', color: '#3b82f6' },
    { value: 'proposal', label: '方案报价', color: '#f59e0b' },
    { value: 'negotiation', label: '商务谈判', color: '#f97316' },
    { value: 'won', label: '赢单', color: '#10b981' },
    { value: 'lost', label: '输单', color: '#ef4444' },
];

const PRIORITY_OPTIONS = [
    { value: 'low', label: '低', color: '#6b7280' },
    { value: 'medium', label: '中', color: '#3b82f6' },
    { value: 'high', label: '高', color: '#f59e0b' },
    { value: 'urgent', label: '紧急', color: '#ef4444' },
];

const RISK_OPTIONS = [
    { value: 'none', label: '无', color: '#6b7280' },
    { value: 'low', label: '低', color: '#10b981' },
    { value: 'medium', label: '中', color: '#f59e0b' },
    { value: 'high', label: '高', color: '#ef4444' },
];

function StageBadge({ stage }: { stage: string }) {
    const opt = STAGE_OPTIONS.find(o => o.value === stage);
    return (
        <span style={{
            display: 'inline-block', padding: '2px 8px', borderRadius: '10px',
            fontSize: '11px', fontWeight: 500,
            background: `${opt?.color || '#6b7280'}20`,
            color: opt?.color || '#6b7280',
            border: `1px solid ${opt?.color || '#6b7280'}40`,
        }}>
            {opt?.label || stage}
        </span>
    );
}

function PriorityBadge({ priority }: { priority: string }) {
    const opt = PRIORITY_OPTIONS.find(o => o.value === priority);
    return (
        <span style={{
            display: 'inline-block', padding: '1px 6px', borderRadius: '8px',
            fontSize: '10px', fontWeight: 500,
            background: `${opt?.color || '#6b7280'}15`,
            color: opt?.color || '#6b7280',
        }}>
            {opt?.label || priority}
        </span>
    );
}

function RiskBadge({ risk }: { risk: string }) {
    if (!risk || risk === 'none') return null;
    const opt = RISK_OPTIONS.find(o => o.value === risk);
    return (
        <span style={{
            display: 'inline-block', padding: '1px 6px', borderRadius: '8px',
            fontSize: '10px', fontWeight: 500,
            background: `${opt?.color || '#6b7280'}15`,
            color: opt?.color || '#6b7280',
        }}>
            ⚠ {opt?.label || risk}
        </span>
    );
}

function StatCard({ label, value, sub, color }: { label: string; value: string | number; sub?: string; color?: string }) {
    return (
        <div style={{
            background: 'var(--bg-secondary)', borderRadius: '10px',
            padding: '16px 20px', border: '1px solid var(--border-subtle)',
            flex: '1 1 160px', minWidth: '140px',
        }}>
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginBottom: '6px' }}>{label}</div>
            <div style={{ fontSize: '22px', fontWeight: 700, color: color || 'var(--text-primary)' }}>{value}</div>
            {sub && <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginTop: '4px' }}>{sub}</div>}
        </div>
    );
}

// ─── Detail Modal ─────────────────────────────────────

function DetailModal({ opp, onClose, onUpdate }: { opp: any; onClose: () => void; onUpdate: () => void }) {
    const [editing, setEditing] = useState(false);
    const [form, setForm] = useState({ ...opp });
    const [saving, setSaving] = useState(false);
    const [logs, setLogs] = useState<any[]>([]);
    const [newNote, setNewNote] = useState('');

    useEffect(() => {
        opportunityApi.logs(opp.id).then(setLogs).catch(() => { });
    }, [opp.id]);

    const handleSave = async () => {
        setSaving(true);
        try {
            await opportunityApi.update(opp.id, form);
            onUpdate();
            setEditing(false);
        } catch { }
        setSaving(false);
    };

    const handleAddNote = async () => {
        if (!newNote.trim()) return;
        await opportunityApi.addLog(opp.id, newNote, 'note');
        setNewNote('');
        opportunityApi.logs(opp.id).then(setLogs).catch(() => { });
    };

    const fieldStyle: React.CSSProperties = { width: '100%', fontSize: '13px', padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-subtle)', background: 'var(--bg-primary)', color: 'var(--text-primary)' };
    const labelStyle: React.CSSProperties = { fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 500, marginBottom: '4px', display: 'block' };

    return (
        <div style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'flex-start', justifyContent: 'center', paddingTop: '5vh', overflowY: 'auto' }} onClick={onClose}>
            <div style={{ background: 'var(--bg-primary)', borderRadius: '12px', border: '1px solid var(--border-subtle)', width: '680px', maxHeight: '90vh', overflow: 'auto', padding: '24px', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }} onClick={e => e.stopPropagation()}>
                {/* Header */}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                        <h3 style={{ margin: 0, fontSize: '16px' }}>{opp.customer_name}</h3>
                        <StageBadge stage={editing ? form.stage : opp.stage} />
                        <PriorityBadge priority={editing ? form.priority : opp.priority} />
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                        {!editing ? (
                            <button className="btn btn-primary" onClick={() => setEditing(true)} style={{ fontSize: '12px', padding: '4px 12px' }}>编辑</button>
                        ) : (
                            <>
                                <button className="btn btn-ghost" onClick={() => { setEditing(false); setForm({ ...opp }); }} style={{ fontSize: '12px', padding: '4px 12px' }}>取消</button>
                                <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ fontSize: '12px', padding: '4px 12px' }}>{saving ? '...' : '保存'}</button>
                            </>
                        )}
                        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', fontSize: '18px', cursor: 'pointer', padding: '4px 8px' }}>×</button>
                    </div>
                </div>

                {/* Fields */}
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '20px' }}>
                    <div>
                        <label style={labelStyle}>客户名称</label>
                        {editing ? <input style={fieldStyle} value={form.customer_name || ''} onChange={e => setForm({ ...form, customer_name: e.target.value })} /> : <div style={{ fontSize: '13px' }}>{opp.customer_name}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>拜访日期</label>
                        {editing ? <input type="date" style={fieldStyle} value={form.visit_date?.slice(0, 10) || ''} onChange={e => setForm({ ...form, visit_date: e.target.value })} /> : <div style={{ fontSize: '13px' }}>{opp.visit_date?.slice(0, 10) || '-'}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>联系人</label>
                        {editing ? <input style={fieldStyle} value={form.contact_person || ''} onChange={e => setForm({ ...form, contact_person: e.target.value })} /> : <div style={{ fontSize: '13px' }}>{opp.contact_person || '-'}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>联系方式</label>
                        {editing ? <input style={fieldStyle} value={form.contact_info || ''} onChange={e => setForm({ ...form, contact_info: e.target.value })} /> : <div style={{ fontSize: '13px' }}>{opp.contact_info || '-'}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>项目规模</label>
                        {editing ? <input style={fieldStyle} value={form.project_scale || ''} onChange={e => setForm({ ...form, project_scale: e.target.value })} /> : <div style={{ fontSize: '13px' }}>{opp.project_scale || '-'}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>项目时长</label>
                        {editing ? <input style={fieldStyle} value={form.project_duration || ''} onChange={e => setForm({ ...form, project_duration: e.target.value })} /> : <div style={{ fontSize: '13px' }}>{opp.project_duration || '-'}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>预计金额 (万元)</label>
                        {editing ? <input type="number" style={fieldStyle} value={form.estimated_amount || ''} onChange={e => setForm({ ...form, estimated_amount: parseFloat(e.target.value) || null })} /> : <div style={{ fontSize: '13px' }}>{opp.estimated_amount != null ? `${opp.estimated_amount} 万` : '-'}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>赢单概率</label>
                        {editing ? <input type="number" style={fieldStyle} min={0} max={100} value={form.win_probability || ''} onChange={e => setForm({ ...form, win_probability: parseInt(e.target.value) || null })} /> : <div style={{ fontSize: '13px' }}>{opp.win_probability != null ? `${opp.win_probability}%` : '-'}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>阶段</label>
                        {editing ? (
                            <select style={fieldStyle} value={form.stage} onChange={e => setForm({ ...form, stage: e.target.value })}>
                                {STAGE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                            </select>
                        ) : <StageBadge stage={opp.stage} />}
                    </div>
                    <div>
                        <label style={labelStyle}>优先级</label>
                        {editing ? (
                            <select style={fieldStyle} value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}>
                                {PRIORITY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                            </select>
                        ) : <PriorityBadge priority={opp.priority} />}
                    </div>
                    <div>
                        <label style={labelStyle}>风险等级</label>
                        {editing ? (
                            <select style={fieldStyle} value={form.risk_flag || 'none'} onChange={e => setForm({ ...form, risk_flag: e.target.value })}>
                                {RISK_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                            </select>
                        ) : <RiskBadge risk={opp.risk_flag} />}
                    </div>
                </div>

                {/* Long text fields */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px' }}>
                    <div>
                        <label style={labelStyle}>讨论方案</label>
                        {editing ? <textarea style={{ ...fieldStyle, minHeight: '60px', resize: 'vertical' }} value={form.solution || ''} onChange={e => setForm({ ...form, solution: e.target.value })} /> : <div style={{ fontSize: '13px', whiteSpace: 'pre-wrap', lineHeight: '1.5', background: 'var(--bg-secondary)', padding: '8px 12px', borderRadius: '6px' }}>{opp.solution || '-'}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>拜访纪要</label>
                        {editing ? <textarea style={{ ...fieldStyle, minHeight: '80px', resize: 'vertical' }} value={form.visit_summary || ''} onChange={e => setForm({ ...form, visit_summary: e.target.value })} /> : <div style={{ fontSize: '13px', whiteSpace: 'pre-wrap', lineHeight: '1.5', background: 'var(--bg-secondary)', padding: '8px 12px', borderRadius: '6px' }}>{opp.visit_summary || '-'}</div>}
                    </div>
                    <div>
                        <label style={labelStyle}>下一步行动</label>
                        {editing ? <textarea style={{ ...fieldStyle, minHeight: '40px', resize: 'vertical' }} value={form.next_action || ''} onChange={e => setForm({ ...form, next_action: e.target.value })} /> : <div style={{ fontSize: '13px', whiteSpace: 'pre-wrap', lineHeight: '1.5', background: 'var(--bg-secondary)', padding: '8px 12px', borderRadius: '6px' }}>{opp.next_action || '-'}</div>}
                    </div>
                    {opp.risk_note && (
                        <div>
                            <label style={labelStyle}>风险说明</label>
                            {editing ? <textarea style={{ ...fieldStyle, minHeight: '40px', resize: 'vertical' }} value={form.risk_note || ''} onChange={e => setForm({ ...form, risk_note: e.target.value })} /> : <div style={{ fontSize: '13px', whiteSpace: 'pre-wrap', color: 'var(--warning)', background: 'var(--bg-secondary)', padding: '8px 12px', borderRadius: '6px' }}>{opp.risk_note}</div>}
                        </div>
                    )}
                </div>

                {/* Meta */}
                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)', display: 'flex', gap: '16px', marginBottom: '16px', flexWrap: 'wrap' }}>
                    {opp.created_by_agent_name && <span>录入: {opp.created_by_agent_name} (Agent)</span>}
                    {opp.created_by_user_name && <span>创建: {opp.created_by_user_name}</span>}
                    <span>创建于 {opp.created_at ? new Date(opp.created_at).toLocaleString() : '-'}</span>
                    <span>更新于 {opp.updated_at ? new Date(opp.updated_at).toLocaleString() : '-'}</span>
                </div>

                {/* Original input */}
                {opp.raw_input && (
                    <div style={{ marginBottom: '16px' }}>
                        <label style={labelStyle}>原始输入</label>
                        <div style={{ fontSize: '12px', whiteSpace: 'pre-wrap', lineHeight: '1.5', background: 'var(--bg-tertiary)', padding: '8px 12px', borderRadius: '6px', color: 'var(--text-secondary)', fontStyle: 'italic' }}>{opp.raw_input}</div>
                    </div>
                )}

                {/* Logs */}
                <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
                    <h4 style={{ margin: '0 0 12px', fontSize: '13px', fontWeight: 600 }}>跟进记录</h4>
                    <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                        <input style={{ ...fieldStyle, flex: 1 }} placeholder="添加备注..." value={newNote} onChange={e => setNewNote(e.target.value)} onKeyDown={e => e.key === 'Enter' && handleAddNote()} />
                        <button className="btn btn-primary" onClick={handleAddNote} style={{ fontSize: '12px', padding: '6px 12px', whiteSpace: 'nowrap' }}>添加</button>
                    </div>
                    {logs.length === 0 && <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>暂无记录</div>}
                    {logs.map((l: any) => (
                        <div key={l.id} style={{ padding: '8px 0', borderBottom: '1px solid var(--border-subtle)', fontSize: '12px' }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '2px' }}>
                                <span style={{ color: l.log_type === 'stage_change' ? 'var(--accent-primary)' : l.log_type === 'risk_alert' ? 'var(--warning)' : 'var(--text-secondary)', fontWeight: 500 }}>
                                    {l.log_type === 'stage_change' ? '📋' : l.log_type === 'risk_alert' ? '⚠️' : l.log_type === 'follow_up' ? '📞' : '📝'} {l.content}
                                </span>
                                <span style={{ color: 'var(--text-quaternary)', fontSize: '10px' }}>{l.created_at ? new Date(l.created_at).toLocaleString() : ''}</span>
                            </div>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}

// ─── Create Modal ─────────────────────────────────────

function CreateModal({ onClose, onCreated }: { onClose: () => void; onCreated: () => void }) {
    const [form, setForm] = useState<any>({ customer_name: '', stage: 'initial_contact', priority: 'medium' });
    const [saving, setSaving] = useState(false);

    const handleSave = async () => {
        if (!form.customer_name?.trim()) return;
        setSaving(true);
        try {
            await opportunityApi.create(form);
            onCreated();
            onClose();
        } catch { }
        setSaving(false);
    };

    const fieldStyle: React.CSSProperties = { width: '100%', fontSize: '13px', padding: '6px 10px', borderRadius: '6px', border: '1px solid var(--border-subtle)', background: 'var(--bg-primary)', color: 'var(--text-primary)', boxSizing: 'border-box' };
    const labelStyle: React.CSSProperties = { fontSize: '11px', color: 'var(--text-tertiary)', fontWeight: 500, marginBottom: '4px', display: 'block' };

    return (
        <div style={{ position: 'fixed', inset: 0, zIndex: 10000, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }} onClick={onClose}>
            <div style={{ background: 'var(--bg-primary)', borderRadius: '12px', border: '1px solid var(--border-subtle)', width: '520px', maxHeight: '80vh', overflow: 'auto', padding: '24px', boxShadow: '0 20px 60px rgba(0,0,0,0.3)' }} onClick={e => e.stopPropagation()}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                    <h3 style={{ margin: 0, fontSize: '16px' }}>新建商机</h3>
                    <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', fontSize: '18px', cursor: 'pointer' }}>×</button>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                    <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>客户名称 *</label><input style={fieldStyle} value={form.customer_name} onChange={e => setForm({ ...form, customer_name: e.target.value })} placeholder="客户公司名称" /></div>
                    <div><label style={labelStyle}>拜访日期</label><input type="date" style={fieldStyle} value={form.visit_date || ''} onChange={e => setForm({ ...form, visit_date: e.target.value })} /></div>
                    <div><label style={labelStyle}>联系人</label><input style={fieldStyle} value={form.contact_person || ''} onChange={e => setForm({ ...form, contact_person: e.target.value })} /></div>
                    <div><label style={labelStyle}>项目规模</label><input style={fieldStyle} value={form.project_scale || ''} onChange={e => setForm({ ...form, project_scale: e.target.value })} placeholder="如 1000~2000万" /></div>
                    <div><label style={labelStyle}>项目时长</label><input style={fieldStyle} value={form.project_duration || ''} onChange={e => setForm({ ...form, project_duration: e.target.value })} placeholder="如 6个月" /></div>
                    <div><label style={labelStyle}>阶段</label>
                        <select style={fieldStyle} value={form.stage} onChange={e => setForm({ ...form, stage: e.target.value })}>
                            {STAGE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                    </div>
                    <div><label style={labelStyle}>优先级</label>
                        <select style={fieldStyle} value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}>
                            {PRIORITY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                        </select>
                    </div>
                    <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>讨论方案</label><textarea style={{ ...fieldStyle, minHeight: '60px' }} value={form.solution || ''} onChange={e => setForm({ ...form, solution: e.target.value })} /></div>
                    <div style={{ gridColumn: '1 / -1' }}><label style={labelStyle}>拜访纪要</label><textarea style={{ ...fieldStyle, minHeight: '60px' }} value={form.visit_summary || ''} onChange={e => setForm({ ...form, visit_summary: e.target.value })} /></div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', marginTop: '20px' }}>
                    <button className="btn btn-ghost" onClick={onClose} style={{ fontSize: '12px', padding: '6px 16px' }}>取消</button>
                    <button className="btn btn-primary" onClick={handleSave} disabled={saving || !form.customer_name?.trim()} style={{ fontSize: '12px', padding: '6px 16px' }}>{saving ? '保存中...' : '创建'}</button>
                </div>
            </div>
        </div>
    );
}

// ─── Main Page ────────────────────────────────────────

export default function Opportunities() {
    const { i18n } = useTranslation();
    const isChinese = i18n.language?.startsWith('zh');

    const [items, setItems] = useState<any[]>([]);
    const [total, setTotal] = useState(0);
    const [loading, setLoading] = useState(true);
    const [stats, setStats] = useState<any>(null);

    // Filters
    const [search, setSearch] = useState('');
    const [stageFilter, setStageFilter] = useState('');
    const [priorityFilter, setPriorityFilter] = useState('');

    // Modals
    const [selectedOpp, setSelectedOpp] = useState<any>(null);
    const [showCreate, setShowCreate] = useState(false);

    const loadData = useCallback(async () => {
        setLoading(true);
        try {
            const params: Record<string, string> = {};
            if (search) params.search = search;
            if (stageFilter) params.stage = stageFilter;
            if (priorityFilter) params.priority = priorityFilter;
            const data = await opportunityApi.list(params);
            setItems(data.items);
            setTotal(data.total);
        } catch { }
        setLoading(false);
    }, [search, stageFilter, priorityFilter]);

    const loadStats = useCallback(async () => {
        try {
            const s = await opportunityApi.stats();
            setStats(s);
        } catch { }
    }, []);

    useEffect(() => { loadData(); loadStats(); }, [loadData, loadStats]);

    const handleDelete = async (id: string) => {
        if (!confirm('确定删除此商机？')) return;
        await opportunityApi.delete(id);
        loadData();
        loadStats();
    };

    return (
        <div style={{ padding: '24px 32px', maxWidth: '1400px', margin: '0 auto' }}>
            {/* Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
                <div>
                    <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 700 }}>💼 {isChinese ? '商机管理' : 'Opportunities'}</h2>
                    <p style={{ margin: '4px 0 0', fontSize: '13px', color: 'var(--text-tertiary)' }}>
                        {isChinese ? '所有数字员工共享的商机数据表，支持自动录入与人工管理' : 'Shared opportunity table for all digital employees'}
                    </p>
                </div>
                <button className="btn btn-primary" onClick={() => setShowCreate(true)} style={{ fontSize: '13px', padding: '8px 16px' }}>
                    + 新建商机
                </button>
            </div>

            {/* Stats Cards */}
            {stats && (
                <div style={{ display: 'flex', gap: '12px', marginBottom: '20px', flexWrap: 'wrap' }}>
                    <StatCard label="总商机数" value={stats.total} />
                    <StatCard label="进行中" value={(stats.total || 0) - (stats.by_stage?.won || 0) - (stats.by_stage?.lost || 0)} color="#3b82f6" />
                    <StatCard label="赢单" value={stats.by_stage?.won || 0} color="#10b981" />
                    <StatCard label="预计总金额" value={stats.total_estimated_amount ? `${(stats.total_estimated_amount / 10000).toFixed(0)}万` : '-'} color="#f59e0b" />
                    <StatCard label="高风险" value={stats.by_risk?.high || 0} color="#ef4444" />
                </div>
            )}

            {/* Filters */}
            <div style={{ display: 'flex', gap: '10px', marginBottom: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
                <div style={{ position: 'relative', flex: '1 1 200px', maxWidth: '300px' }}>
                    <input
                        placeholder={isChinese ? '搜索客户、方案...' : 'Search...'}
                        value={search}
                        onChange={e => setSearch(e.target.value)}
                        style={{
                            width: '100%', padding: '7px 12px', fontSize: '13px', borderRadius: '8px',
                            border: '1px solid var(--border-subtle)', background: 'var(--bg-secondary)',
                            color: 'var(--text-primary)', outline: 'none', boxSizing: 'border-box',
                        }}
                    />
                </div>
                <select
                    value={stageFilter}
                    onChange={e => setStageFilter(e.target.value)}
                    style={{
                        padding: '7px 10px', fontSize: '12px', borderRadius: '8px',
                        border: '1px solid var(--border-subtle)', background: 'var(--bg-secondary)',
                        color: 'var(--text-primary)', cursor: 'pointer',
                    }}
                >
                    <option value="">所有阶段</option>
                    {STAGE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                <select
                    value={priorityFilter}
                    onChange={e => setPriorityFilter(e.target.value)}
                    style={{
                        padding: '7px 10px', fontSize: '12px', borderRadius: '8px',
                        border: '1px solid var(--border-subtle)', background: 'var(--bg-secondary)',
                        color: 'var(--text-primary)', cursor: 'pointer',
                    }}
                >
                    <option value="">所有优先级</option>
                    {PRIORITY_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                </select>
                <div style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>共 {total} 条</div>
            </div>

            {/* Table */}
            <div style={{ background: 'var(--bg-secondary)', borderRadius: '10px', border: '1px solid var(--border-subtle)', overflow: 'hidden' }}>
                <div style={{ overflowX: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                        <thead>
                            <tr style={{ borderBottom: '1px solid var(--border-subtle)' }}>
                                {['客户名称', '拜访日期', '方案', '项目规模', '阶段', '优先级', '风险', '录入方', '操作'].map(h => (
                                    <th key={h} style={{
                                        padding: '10px 14px', textAlign: 'left', fontSize: '11px',
                                        fontWeight: 600, color: 'var(--text-tertiary)', whiteSpace: 'nowrap',
                                        background: 'var(--bg-tertiary)',
                                    }}>{h}</th>
                                ))}
                            </tr>
                        </thead>
                        <tbody>
                            {loading && (
                                <tr><td colSpan={9} style={{ padding: '40px', textAlign: 'center', color: 'var(--text-tertiary)' }}>加载中...</td></tr>
                            )}
                            {!loading && items.length === 0 && (
                                <tr><td colSpan={9} style={{ padding: '40px', textAlign: 'center', color: 'var(--text-tertiary)' }}>
                                    暂无商机数据。数字员工通过消息自动录入，或点击右上角手动创建。
                                </td></tr>
                            )}
                            {items.map((opp: any) => (
                                <tr
                                    key={opp.id}
                                    style={{ borderBottom: '1px solid var(--border-subtle)', cursor: 'pointer', transition: 'background 0.1s' }}
                                    onClick={() => setSelectedOpp(opp)}
                                    onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-tertiary)')}
                                    onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
                                >
                                    <td style={{ padding: '10px 14px', fontWeight: 500 }}>{opp.customer_name}</td>
                                    <td style={{ padding: '10px 14px', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{opp.visit_date?.slice(0, 10) || '-'}</td>
                                    <td style={{ padding: '10px 14px', maxWidth: '200px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{opp.solution || '-'}</td>
                                    <td style={{ padding: '10px 14px', whiteSpace: 'nowrap', color: 'var(--text-secondary)' }}>{opp.project_scale || '-'}</td>
                                    <td style={{ padding: '10px 14px' }}><StageBadge stage={opp.stage} /></td>
                                    <td style={{ padding: '10px 14px' }}><PriorityBadge priority={opp.priority} /></td>
                                    <td style={{ padding: '10px 14px' }}><RiskBadge risk={opp.risk_flag} /></td>
                                    <td style={{ padding: '10px 14px', fontSize: '11px', color: 'var(--text-tertiary)', whiteSpace: 'nowrap' }}>
                                        {opp.created_by_agent_name || opp.created_by_user_name || '-'}
                                    </td>
                                    <td style={{ padding: '10px 14px' }} onClick={e => e.stopPropagation()}>
                                        <button
                                            onClick={() => handleDelete(opp.id)}
                                            style={{ background: 'none', border: 'none', color: 'var(--text-tertiary)', cursor: 'pointer', fontSize: '12px', padding: '2px 6px' }}
                                            title="删除"
                                        >🗑</button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Modals */}
            {selectedOpp && (
                <DetailModal
                    opp={selectedOpp}
                    onClose={() => setSelectedOpp(null)}
                    onUpdate={() => { loadData(); loadStats(); setSelectedOpp(null); }}
                />
            )}
            {showCreate && (
                <CreateModal
                    onClose={() => setShowCreate(false)}
                    onCreated={() => { loadData(); loadStats(); }}
                />
            )}
        </div>
    );
}
