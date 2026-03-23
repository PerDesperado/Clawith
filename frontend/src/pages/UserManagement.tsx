/**
 * User Management — admin page to create, view and manage users.
 * 
 * New Flow:
 * 1. Admin creates user -> sets username, password, org assignment
 * 2. User logs in -> must change password if must_change_password=true
 */
import { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';

interface UserInfo {
    id: string;
    username: string;
    email: string;
    display_name: string;
    role: string;
    is_active: boolean;
    quota_message_limit: number;
    quota_message_period: string;
    quota_messages_used: number;
    quota_max_agents: number;
    quota_agent_ttl_hours: number;
    agents_count: number;
    feishu_open_id?: string;
    created_at?: string;
    source?: string;
}

interface UserDetailInfo {
    id: string;
    username: string;
    email: string;
    display_name: string;
    avatar_url?: string;
    platform_role: string;
    is_active: boolean;
    must_change_password: boolean;
    org_member_id?: string;
    team_id?: string;
    team_name?: string;
    center_id?: string;
    center_name?: string;
    department_id?: string;
    department_name?: string;
    member_role?: string;
    title?: string;
    phone?: string;
    created_at?: string;
}

interface OrgTeam {
    id: string;
    name: string;
}

interface OrgCenter {
    id: string;
    name: string;
    teams: OrgTeam[];
}

interface OrgDepartment {
    id: string;
    name: string;
    centers: OrgCenter[];
}

const API_PREFIX = '/api';

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
    const token = localStorage.getItem('token');
    const res = await fetch(`${API_PREFIX}${url}`, {
        headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        ...options,
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Request failed' }));
        throw new Error(err.detail || `HTTP ${res.status}`);
    }
    if (res.status === 204) return undefined as T;
    return res.json();
}

const PERIOD_OPTIONS = [
    { value: 'permanent', label: 'Permanent' },
    { value: 'daily', label: 'Daily' },
    { value: 'weekly', label: 'Weekly' },
    { value: 'monthly', label: 'Monthly' },
];

const PLATFORM_ROLES = [
    { value: 'platform_admin', label: '平台管理员', labelEn: 'Platform Admin' },
    { value: 'org_admin', label: '组织管理员', labelEn: 'Org Admin' },
    { value: 'agent_admin', label: 'Agent管理员', labelEn: 'Agent Admin' },
    { value: 'member', label: '普通成员', labelEn: 'Member' },
];

const MEMBER_ROLES = [
    { value: 'platform_admin', label: '平台管理员', labelEn: 'Platform Admin' },
    { value: 'gm', label: 'GM', labelEn: 'GM' },
    { value: 'director', label: '总监', labelEn: 'Director' },
    { value: 'leader', label: '正组长', labelEn: 'Leader' },
    { value: 'deputy_leader', label: '副组长', labelEn: 'Deputy Leader' },
    { value: 'member', label: '组员', labelEn: 'Member' },
];

const PAGE_SIZE = 15;

export default function UserManagement() {
    const { t, i18n } = useTranslation();
    const isChinese = i18n.language?.startsWith('zh');

    const [users, setUsers] = useState<UserInfo[]>([]);
    const [loading, setLoading] = useState(true);
    const [editingUserId, setEditingUserId] = useState<string | null>(null);
    const [editForm, setEditForm] = useState({
        quota_message_limit: 50,
        quota_message_period: 'permanent',
        quota_max_agents: 2,
        quota_agent_ttl_hours: 48,
    });
    const [saving, setSaving] = useState(false);
    const [toast, setToast] = useState('');

    // Search, sort & pagination
    const [searchQuery, setSearchQuery] = useState('');
    const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');
    const [page, setPage] = useState(1);

    // Create user modal
    const [showCreateModal, setShowCreateModal] = useState(false);
    const [createForm, setCreateForm] = useState({
        username: '',
        email: '',
        display_name: '',
        password: '',
        team_id: '',
        member_role: 'member',
        platform_role: 'member',
        title: '',
        phone: '',
    });
    const [creating, setCreating] = useState(false);
    const [createdPassword, setCreatedPassword] = useState<string | null>(null);

    // Org structure for team selection
    const [orgStructure, setOrgStructure] = useState<OrgDepartment[]>([]);

    // Reset password modal
    const [resetPasswordUserId, setResetPasswordUserId] = useState<string | null>(null);
    const [newResetPassword, setNewResetPassword] = useState('');
    const [resetPasswordResult, setResetPasswordResult] = useState<string | null>(null);

    const loadUsers = async () => {
        setLoading(true);
        try {
            const tenantId = localStorage.getItem('current_tenant_id') || '';
            const data = await fetchJson<UserInfo[]>(`/users/${tenantId ? `?tenant_id=${tenantId}` : ''}`);
            setUsers(data);
        } catch (e) {
            console.error('Failed to load users', e);
        }
        setLoading(false);
    };

    const loadOrgStructure = async () => {
        try {
            const data = await fetchJson<OrgDepartment[]>('/user-management/org/teams');
            setOrgStructure(data);
        } catch (e) {
            console.error('Failed to load org structure', e);
        }
    };

    useEffect(() => {
        loadUsers();
        loadOrgStructure();
    }, []);

    const startEdit = (user: UserInfo) => {
        setEditingUserId(user.id);
        setEditForm({
            quota_message_limit: user.quota_message_limit,
            quota_message_period: user.quota_message_period,
            quota_max_agents: user.quota_max_agents,
            quota_agent_ttl_hours: user.quota_agent_ttl_hours,
        });
    };

    const handleSave = async () => {
        if (!editingUserId) return;
        setSaving(true);
        try {
            await fetchJson(`/users/${editingUserId}/quota`, {
                method: 'PATCH',
                body: JSON.stringify(editForm),
            });
            setToast(isChinese ? '✅ 配额已更新' : '✅ Quota updated');
            setTimeout(() => setToast(''), 2000);
            setEditingUserId(null);
            loadUsers();
        } catch (e: any) {
            setToast(`❌ ${e.message}`);
            setTimeout(() => setToast(''), 3000);
        }
        setSaving(false);
    };

    const handleCreateUser = async () => {
        if (!createForm.username || !createForm.email || !createForm.display_name) {
            setToast(isChinese ? '❌ 请填写必填字段' : '❌ Please fill required fields');
            setTimeout(() => setToast(''), 3000);
            return;
        }

        setCreating(true);
        try {
            const result = await fetchJson<{ user: UserDetailInfo; initial_password: string }>('/user-management/users', {
                method: 'POST',
                body: JSON.stringify({
                    username: createForm.username,
                    email: createForm.email,
                    display_name: createForm.display_name,
                    password: createForm.password || undefined,
                    team_id: createForm.team_id || undefined,
                    member_role: createForm.member_role,
                    platform_role: createForm.platform_role,
                    title: createForm.title,
                    phone: createForm.phone,
                }),
            });
            
            // Show the initial password
            setCreatedPassword(result.initial_password);
            setToast(isChinese ? '✅ 用户创建成功' : '✅ User created successfully');
            setTimeout(() => setToast(''), 3000);
            loadUsers();
        } catch (e: any) {
            setToast(`❌ ${e.message}`);
            setTimeout(() => setToast(''), 3000);
        }
        setCreating(false);
    };

    const handleResetPassword = async () => {
        if (!resetPasswordUserId) return;
        setCreating(true);
        try {
            const result = await fetchJson<{ new_password: string }>(`/user-management/users/${resetPasswordUserId}/reset-password`, {
                method: 'POST',
                body: JSON.stringify({ new_password: newResetPassword || undefined }),
            });
            setResetPasswordResult(result.new_password);
            setToast(isChinese ? '✅ 密码已重置' : '✅ Password reset');
            setTimeout(() => setToast(''), 2000);
        } catch (e: any) {
            setToast(`❌ ${e.message}`);
            setTimeout(() => setToast(''), 3000);
        }
        setCreating(false);
    };

    const closeCreateModal = () => {
        setShowCreateModal(false);
        setCreatedPassword(null);
        setCreateForm({
            username: '',
            email: '',
            display_name: '',
            password: '',
            team_id: '',
            member_role: 'member',
            platform_role: 'member',
            title: '',
            phone: '',
        });
    };

    const closeResetModal = () => {
        setResetPasswordUserId(null);
        setNewResetPassword('');
        setResetPasswordResult(null);
    };

    const periodLabel = (period: string) => {
        if (isChinese) {
            const map: Record<string, string> = { permanent: '永久', daily: '每天', weekly: '每周', monthly: '每月' };
            return map[period] || period;
        }
        return PERIOD_OPTIONS.find(p => p.value === period)?.label || period;
    };

    const formatDate = (iso?: string) => {
        if (!iso) return '-';
        const d = new Date(iso);
        return d.toLocaleString(isChinese ? 'zh-CN' : 'en-US', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    };

    // Flatten all org nodes for dropdown (supports variable depth hierarchy)
    const allTeams = useMemo(() => {
        const teams: { id: string; name: string; path: string }[] = [];
        for (const dept of orgStructure) {
            if (dept.centers.length === 0) {
                // Department with no centers - can be selected directly
                teams.push({
                    id: dept.id,
                    name: dept.name,
                    path: dept.name,
                });
            } else {
                for (const center of dept.centers) {
                    if (center.teams.length === 0) {
                        // Center with no teams - can be selected directly
                        teams.push({
                            id: center.id,
                            name: center.name,
                            path: `${dept.name} / ${center.name}`,
                        });
                    } else {
                        // Teams under center
                        for (const team of center.teams) {
                            teams.push({
                                id: team.id,
                                name: team.name,
                                path: `${dept.name} / ${center.name} / ${team.name}`,
                            });
                        }
                    }
                }
            }
        }
        return teams;
    }, [orgStructure]);

    // Search filter
    const filtered = searchQuery.trim()
        ? users.filter(u => {
            const q = searchQuery.toLowerCase();
            return (u.username?.toLowerCase().includes(q))
                || (u.display_name?.toLowerCase().includes(q))
                || (u.email?.toLowerCase().includes(q));
        })
        : users;

    // Sort
    const sorted = [...filtered].sort((a, b) => {
        const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
        const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
        return sortOrder === 'asc' ? ta - tb : tb - ta;
    });

    // Paginate
    const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE));
    const paged = sorted.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

    const toggleSort = () => {
        setSortOrder(o => o === 'asc' ? 'desc' : 'asc');
        setPage(1);
    };

    return (
        <div>
            {toast && (
                <div style={{
                    position: 'fixed', top: '20px', right: '20px', padding: '10px 20px',
                    borderRadius: '8px', background: toast.startsWith('✅') ? 'var(--success)' : 'var(--error)',
                    color: '#fff', fontSize: '13px', zIndex: 9999, transition: 'all 0.3s',
                }}>
                    {toast}
                </div>
            )}

            {/* Create User Button */}
            <div style={{ marginBottom: '16px', display: 'flex', gap: '12px', alignItems: 'center' }}>
                <button
                    className="btn btn-primary"
                    onClick={() => setShowCreateModal(true)}
                    style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
                >
                    ➕ {isChinese ? '创建用户' : 'Create User'}
                </button>
                <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                    {isChinese 
                        ? '创建用户后，初始密码将显示一次，用户首次登录需要修改密码'
                        : 'Initial password shown once after creation. User must change password on first login.'
                    }
                </span>
            </div>

            {loading ? (
                <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                    {t('common.loading')}...
                </div>
            ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                    {/* Search bar */}
                    <div style={{ position: 'relative', marginBottom: '4px' }}>
                        <input
                            className="form-input"
                            type="text"
                            placeholder={isChinese ? '搜索用户名、显示名或邮箱…' : 'Search username, name or email…'}
                            value={searchQuery}
                            onChange={e => { setSearchQuery(e.target.value); setPage(1); }}
                            style={{
                                width: '100%', maxWidth: '360px', fontSize: '13px',
                                padding: '8px 12px 8px 12px',
                                background: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)',
                                borderRadius: '8px',
                            }}
                        />
                        {searchQuery && (
                            <span style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginLeft: '12px' }}>
                                {isChinese ? `${filtered.length} / ${users.length} 位用户` : `${filtered.length} / ${users.length} users`}
                            </span>
                        )}
                    </div>

                    {/* Header */}
                    <div style={{
                        display: 'grid', gridTemplateColumns: '1.4fr 1.4fr 0.8fr 0.9fr 0.8fr 0.8fr 0.8fr 0.8fr 140px',
                        gap: '10px', padding: '10px 16px', fontSize: '11px', fontWeight: 600,
                        color: 'var(--text-tertiary)', textTransform: 'uppercase', letterSpacing: '0.05em',
                    }}>
                        <div>{t('enterprise.users.user', isChinese ? '用户' : 'User')}</div>
                        <div>{t('enterprise.users.email', 'Email')}</div>
                        {/* Created At with sort toggle */}
                        <div
                            style={{ cursor: 'pointer', userSelect: 'none', display: 'flex', alignItems: 'center', gap: '3px' }}
                            onClick={toggleSort}
                            title={isChinese ? '点击切换排序' : 'Click to toggle sort order'}
                        >
                            {isChinese ? '注册时间' : 'Joined'} {sortOrder === 'asc' ? '↑' : '↓'}
                        </div>
                        <div>{isChinese ? '来源' : 'Source'}</div>
                        <div>{t('enterprise.users.msgQuota', isChinese ? '消息配额' : 'Msg Quota')}</div>
                        <div>{t('enterprise.users.period', isChinese ? '周期' : 'Period')}</div>
                        <div>{t('enterprise.users.agents', isChinese ? '数字员工' : 'Agents')}</div>
                        <div>{t('enterprise.users.ttl', 'TTL')}</div>
                        <div></div>
                    </div>

                    {paged.map(user => (
                        <div key={user.id}>
                            <div className="card" style={{
                                display: 'grid', gridTemplateColumns: '1.4fr 1.4fr 0.8fr 0.9fr 0.8fr 0.8fr 0.8fr 0.8fr 140px',
                                gap: '10px', alignItems: 'center', padding: '12px 16px',
                            }}>
                                <div>
                                    <div style={{ fontWeight: 500, fontSize: '14px' }}>
                                        {user.display_name || user.username}
                                        {user.role === 'platform_admin' && (
                                            <span style={{ marginLeft: '6px', fontSize: '10px', background: 'var(--accent-color)', color: '#fff', borderRadius: '4px', padding: '1px 6px' }}>Admin</span>
                                        )}
                                        {!user.is_active && (
                                            <span style={{ marginLeft: '6px', fontSize: '10px', background: 'var(--error)', color: '#fff', borderRadius: '4px', padding: '1px 6px' }}>
                                                {isChinese ? '已禁用' : 'Disabled'}
                                            </span>
                                        )}
                                    </div>
                                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>@{user.username}</div>
                                </div>
                                <div style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{user.email}</div>
                                <div style={{ fontSize: '11px', color: 'var(--text-secondary)' }}>{formatDate(user.created_at)}</div>
                                <div>
                                    {user.source === 'feishu' ? (
                                        <span style={{ fontSize: '10px', background: 'rgba(58,132,255,0.12)', color: '#3a84ff', borderRadius: '4px', padding: '2px 7px', whiteSpace: 'nowrap' }}>
                                            飞书
                                        </span>
                                    ) : (
                                        <span style={{ fontSize: '10px', background: 'rgba(0,180,120,0.12)', color: 'var(--success)', borderRadius: '4px', padding: '2px 7px', whiteSpace: 'nowrap' }}>
                                            {isChinese ? '注册' : 'Reg'}
                                        </span>
                                    )}
                                </div>
                                <div>
                                    <span style={{ fontSize: '13px', fontWeight: 500 }}>{user.quota_messages_used}</span>
                                    <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}> / {user.quota_message_limit}</span>
                                </div>
                                <div>
                                    <span className="badge badge-info" style={{ fontSize: '10px' }}>{periodLabel(user.quota_message_period)}</span>
                                </div>
                                <div>
                                    <span style={{ fontSize: '13px', fontWeight: 500 }}>{user.agents_count}</span>
                                    <span style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}> / {user.quota_max_agents}</span>
                                </div>
                                <div style={{ fontSize: '12px' }}>{user.quota_agent_ttl_hours}h</div>
                                <div style={{ display: 'flex', gap: '4px' }}>
                                    <button
                                        className="btn btn-secondary"
                                        style={{ padding: '4px 8px', fontSize: '11px' }}
                                        onClick={() => editingUserId === user.id ? setEditingUserId(null) : startEdit(user)}
                                        title={isChinese ? '编辑配额' : 'Edit quota'}
                                    >
                                        ✏️
                                    </button>
                                    <button
                                        className="btn btn-secondary"
                                        style={{ padding: '4px 8px', fontSize: '11px' }}
                                        onClick={() => setResetPasswordUserId(user.id)}
                                        title={isChinese ? '重置密码' : 'Reset password'}
                                    >
                                        🔑
                                    </button>
                                </div>
                            </div>

                            {/* Inline edit form */}
                            {editingUserId === user.id && (
                                <div className="card" style={{
                                    marginTop: '4px', padding: '16px',
                                    background: 'var(--bg-secondary)',
                                    borderLeft: '3px solid var(--accent-color)',
                                }}>
                                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr 1fr', gap: '16px' }}>
                                        <div className="form-group">
                                            <label className="form-label" style={{ fontSize: '11px' }}>
                                                {t('enterprise.users.msgLimit', isChinese ? '消息限额' : 'Message Limit')}
                                            </label>
                                            <input
                                                className="form-input"
                                                type="number" min={0}
                                                value={editForm.quota_message_limit}
                                                onChange={e => setEditForm({ ...editForm, quota_message_limit: Number(e.target.value) })}
                                            />
                                        </div>
                                        <div className="form-group">
                                            <label className="form-label" style={{ fontSize: '11px' }}>
                                                {t('enterprise.users.period', isChinese ? '重置周期' : 'Period')}
                                            </label>
                                            <select
                                                className="form-input"
                                                value={editForm.quota_message_period}
                                                onChange={e => setEditForm({ ...editForm, quota_message_period: e.target.value })}
                                            >
                                                {PERIOD_OPTIONS.map(p => (
                                                    <option key={p.value} value={p.value}>{periodLabel(p.value)}</option>
                                                ))}
                                            </select>
                                        </div>
                                        <div className="form-group">
                                            <label className="form-label" style={{ fontSize: '11px' }}>
                                                {t('enterprise.users.maxAgents', isChinese ? '最多数字员工' : 'Max Agents')}
                                            </label>
                                            <input
                                                className="form-input"
                                                type="number" min={0}
                                                value={editForm.quota_max_agents}
                                                onChange={e => setEditForm({ ...editForm, quota_max_agents: Number(e.target.value) })}
                                            />
                                        </div>
                                        <div className="form-group">
                                            <label className="form-label" style={{ fontSize: '11px' }}>
                                                {t('enterprise.users.agentTTL', isChinese ? '员工存活时长(h)' : 'Agent TTL (hours)')}
                                            </label>
                                            <input
                                                className="form-input"
                                                type="number" min={1}
                                                value={editForm.quota_agent_ttl_hours}
                                                onChange={e => setEditForm({ ...editForm, quota_agent_ttl_hours: Number(e.target.value) })}
                                            />
                                        </div>
                                    </div>
                                    <div style={{ marginTop: '12px', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
                                        <button className="btn btn-secondary" onClick={() => setEditingUserId(null)}>
                                            {t('common.cancel')}
                                        </button>
                                        <button className="btn btn-primary" onClick={handleSave} disabled={saving}>
                                            {saving ? t('common.loading') : t('common.save', 'Save')}
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    ))}

                    {users.length === 0 && (
                        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--text-tertiary)' }}>
                            {t('common.noData')}
                        </div>
                    )}

                    {/* Pagination */}
                    {totalPages > 1 && (
                        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', gap: '8px', marginTop: '16px' }}>
                            <button
                                className="btn btn-secondary"
                                style={{ padding: '4px 10px', fontSize: '12px' }}
                                disabled={page <= 1}
                                onClick={() => setPage(p => p - 1)}
                            >
                                ‹ {isChinese ? '上一页' : 'Prev'}
                            </button>
                            {Array.from({ length: totalPages }, (_, i) => i + 1).map(p => (
                                <button
                                    key={p}
                                    className={`btn ${p === page ? 'btn-primary' : 'btn-secondary'}`}
                                    style={{ padding: '4px 10px', fontSize: '12px', minWidth: '32px' }}
                                    onClick={() => setPage(p)}
                                >
                                    {p}
                                </button>
                            ))}
                            <button
                                className="btn btn-secondary"
                                style={{ padding: '4px 10px', fontSize: '12px' }}
                                disabled={page >= totalPages}
                                onClick={() => setPage(p => p + 1)}
                            >
                                {isChinese ? '下一页' : 'Next'} ›
                            </button>
                        </div>
                    )}
                </div>
            )}

            {/* Create User Modal */}
            {showCreateModal && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                    background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    zIndex: 10000,
                }} onClick={closeCreateModal}>
                    <div className="card" style={{
                        width: '100%', maxWidth: '600px', maxHeight: '90vh', overflow: 'auto',
                        padding: '24px',
                    }} onClick={e => e.stopPropagation()}>
                        <h3 style={{ margin: '0 0 20px 0', fontSize: '18px' }}>
                            {isChinese ? '创建新用户' : 'Create New User'}
                        </h3>

                        {createdPassword ? (
                            // Show success with password
                            <div style={{ textAlign: 'center', padding: '20px' }}>
                                <div style={{ fontSize: '48px', marginBottom: '16px' }}>✅</div>
                                <h4 style={{ marginBottom: '16px' }}>
                                    {isChinese ? '用户创建成功！' : 'User Created Successfully!'}
                                </h4>
                                <div style={{
                                    background: 'var(--bg-secondary)',
                                    padding: '16px',
                                    borderRadius: '8px',
                                    marginBottom: '16px',
                                }}>
                                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>
                                        {isChinese ? '初始密码（仅显示一次）' : 'Initial Password (shown once)'}
                                    </div>
                                    <div style={{
                                        fontSize: '24px', fontFamily: 'monospace', fontWeight: 600,
                                        padding: '12px', background: 'var(--bg-primary)', borderRadius: '6px',
                                        userSelect: 'all',
                                    }}>
                                        {createdPassword}
                                    </div>
                                    <button
                                        className="btn btn-secondary"
                                        style={{ marginTop: '12px' }}
                                        onClick={() => {
                                            navigator.clipboard.writeText(createdPassword);
                                            setToast(isChinese ? '✅ 已复制' : '✅ Copied');
                                            setTimeout(() => setToast(''), 1500);
                                        }}
                                    >
                                        📋 {isChinese ? '复制密码' : 'Copy Password'}
                                    </button>
                                </div>
                                <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                                    {isChinese 
                                        ? '请将密码安全地发送给用户。用户首次登录时需要修改密码。'
                                        : 'Please securely share this password with the user. They will be required to change it on first login.'
                                    }
                                </p>
                                <button
                                    className="btn btn-primary"
                                    style={{ marginTop: '16px' }}
                                    onClick={closeCreateModal}
                                >
                                    {isChinese ? '完成' : 'Done'}
                                </button>
                            </div>
                        ) : (
                            // Create form
                            <>
                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                    <div className="form-group">
                                        <label className="form-label">
                                            {isChinese ? '用户名' : 'Username'} <span style={{ color: 'var(--error)' }}>*</span>
                                        </label>
                                        <input
                                            className="form-input"
                                            type="text"
                                            value={createForm.username}
                                            onChange={e => setCreateForm({ ...createForm, username: e.target.value })}
                                            placeholder={isChinese ? '登录用户名' : 'Login username'}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">
                                            {isChinese ? '显示名称' : 'Display Name'} <span style={{ color: 'var(--error)' }}>*</span>
                                        </label>
                                        <input
                                            className="form-input"
                                            type="text"
                                            value={createForm.display_name}
                                            onChange={e => setCreateForm({ ...createForm, display_name: e.target.value })}
                                            placeholder={isChinese ? '真实姓名或昵称' : 'Real name or nickname'}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">
                                            Email <span style={{ color: 'var(--error)' }}>*</span>
                                        </label>
                                        <input
                                            className="form-input"
                                            type="email"
                                            value={createForm.email}
                                            onChange={e => setCreateForm({ ...createForm, email: e.target.value })}
                                            placeholder="user@example.com"
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">
                                            {isChinese ? '初始密码' : 'Initial Password'}
                                            <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginLeft: '6px' }}>
                                                {isChinese ? '(留空自动生成)' : '(leave empty to auto-generate)'}
                                            </span>
                                        </label>
                                        <input
                                            className="form-input"
                                            type="text"
                                            value={createForm.password}
                                            onChange={e => setCreateForm({ ...createForm, password: e.target.value })}
                                            placeholder={isChinese ? '留空将自动生成' : 'Auto-generated if empty'}
                                        />
                                    </div>
                                </div>

                                <hr style={{ margin: '20px 0', border: 'none', borderTop: '1px solid var(--border-subtle)' }} />

                                <h4 style={{ fontSize: '14px', marginBottom: '12px', color: 'var(--text-secondary)' }}>
                                    {isChinese ? '组织架构' : 'Organization'}
                                </h4>

                                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
                                    <div className="form-group">
                                        <label className="form-label">
                                            {isChinese ? '所属组' : 'Team'}
                                        </label>
                                        <select
                                            className="form-input"
                                            value={createForm.team_id}
                                            onChange={e => setCreateForm({ ...createForm, team_id: e.target.value })}
                                        >
                                            <option value="">{isChinese ? '-- 未分配 --' : '-- Not assigned --'}</option>
                                            {allTeams.map(team => (
                                                <option key={team.id} value={team.id}>{team.path}</option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">
                                            {isChinese ? '组织角色' : 'Org Role'}
                                        </label>
                                        <select
                                            className="form-input"
                                            value={createForm.member_role}
                                            onChange={e => setCreateForm({ ...createForm, member_role: e.target.value })}
                                        >
                                            {MEMBER_ROLES.map(r => (
                                                <option key={r.value} value={r.value}>
                                                    {isChinese ? r.label : r.labelEn}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">
                                            {isChinese ? '平台角色' : 'Platform Role'}
                                        </label>
                                        <select
                                            className="form-input"
                                            value={createForm.platform_role}
                                            onChange={e => setCreateForm({ ...createForm, platform_role: e.target.value })}
                                        >
                                            {PLATFORM_ROLES.map(r => (
                                                <option key={r.value} value={r.value}>
                                                    {isChinese ? r.label : r.labelEn}
                                                </option>
                                            ))}
                                        </select>
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">
                                            {isChinese ? '职位' : 'Title'}
                                        </label>
                                        <input
                                            className="form-input"
                                            type="text"
                                            value={createForm.title}
                                            onChange={e => setCreateForm({ ...createForm, title: e.target.value })}
                                            placeholder={isChinese ? '如：高级工程师' : 'e.g., Senior Engineer'}
                                        />
                                    </div>
                                    <div className="form-group">
                                        <label className="form-label">
                                            {isChinese ? '手机号' : 'Phone'}
                                        </label>
                                        <input
                                            className="form-input"
                                            type="text"
                                            value={createForm.phone}
                                            onChange={e => setCreateForm({ ...createForm, phone: e.target.value })}
                                            placeholder="+86 ..."
                                        />
                                    </div>
                                </div>

                                <div style={{ marginTop: '24px', display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                                    <button className="btn btn-secondary" onClick={closeCreateModal}>
                                        {t('common.cancel')}
                                    </button>
                                    <button className="btn btn-primary" onClick={handleCreateUser} disabled={creating}>
                                        {creating ? t('common.loading') : (isChinese ? '创建用户' : 'Create User')}
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}

            {/* Reset Password Modal */}
            {resetPasswordUserId && (
                <div style={{
                    position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
                    background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                    zIndex: 10000,
                }} onClick={closeResetModal}>
                    <div className="card" style={{
                        width: '100%', maxWidth: '400px',
                        padding: '24px',
                    }} onClick={e => e.stopPropagation()}>
                        <h3 style={{ margin: '0 0 20px 0', fontSize: '18px' }}>
                            {isChinese ? '重置密码' : 'Reset Password'}
                        </h3>

                        {resetPasswordResult ? (
                            // Show new password
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: '48px', marginBottom: '16px' }}>🔑</div>
                                <div style={{
                                    background: 'var(--bg-secondary)',
                                    padding: '16px',
                                    borderRadius: '8px',
                                    marginBottom: '16px',
                                }}>
                                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', marginBottom: '8px' }}>
                                        {isChinese ? '新密码（仅显示一次）' : 'New Password (shown once)'}
                                    </div>
                                    <div style={{
                                        fontSize: '24px', fontFamily: 'monospace', fontWeight: 600,
                                        padding: '12px', background: 'var(--bg-primary)', borderRadius: '6px',
                                        userSelect: 'all',
                                    }}>
                                        {resetPasswordResult}
                                    </div>
                                    <button
                                        className="btn btn-secondary"
                                        style={{ marginTop: '12px' }}
                                        onClick={() => {
                                            navigator.clipboard.writeText(resetPasswordResult);
                                            setToast(isChinese ? '✅ 已复制' : '✅ Copied');
                                            setTimeout(() => setToast(''), 1500);
                                        }}
                                    >
                                        📋 {isChinese ? '复制密码' : 'Copy Password'}
                                    </button>
                                </div>
                                <p style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                                    {isChinese 
                                        ? '用户下次登录需要修改密码。'
                                        : 'User will be required to change password on next login.'
                                    }
                                </p>
                                <button
                                    className="btn btn-primary"
                                    style={{ marginTop: '16px' }}
                                    onClick={closeResetModal}
                                >
                                    {isChinese ? '完成' : 'Done'}
                                </button>
                            </div>
                        ) : (
                            <>
                                <div className="form-group">
                                    <label className="form-label">
                                        {isChinese ? '新密码' : 'New Password'}
                                        <span style={{ fontSize: '11px', color: 'var(--text-tertiary)', marginLeft: '6px' }}>
                                            {isChinese ? '(留空自动生成)' : '(leave empty to auto-generate)'}
                                        </span>
                                    </label>
                                    <input
                                        className="form-input"
                                        type="text"
                                        value={newResetPassword}
                                        onChange={e => setNewResetPassword(e.target.value)}
                                        placeholder={isChinese ? '留空将自动生成随机密码' : 'Auto-generated if empty'}
                                    />
                                </div>
                                <div style={{ marginTop: '20px', display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
                                    <button className="btn btn-secondary" onClick={closeResetModal}>
                                        {t('common.cancel')}
                                    </button>
                                    <button className="btn btn-primary" onClick={handleResetPassword} disabled={creating}>
                                        {creating ? t('common.loading') : (isChinese ? '重置密码' : 'Reset Password')}
                                    </button>
                                </div>
                            </>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}
