import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../stores';
import { reportsApi } from '../services/api';

// ─── Types for new hierarchy structure ───────────────────

interface AgentInfo {
    id: string;
    name: string;
    avatar_url?: string;
    status?: string;
}

interface TeamMember {
    org_member_id: string;
    name: string;
    title?: string;
    is_primary?: boolean;
    role: string;
    agent: AgentInfo | null;
}

interface Team {
    id: string;
    name: string;
    description?: string;
    leaders: TeamMember[];
    members: TeamMember[];
}

interface Center {
    id: string;
    name: string;
    description?: string;
    teams: Team[];
}

interface Department {
    id: string;
    name: string;
    description?: string;
    centers: Center[];
}

interface HierarchyResponse {
    departments: Department[];
    user_role: string;
    scope: string;
}

interface Report {
    id: string;
    agent_id: string;
    agent_name?: string;
    report_date: string;
    summary: string | null;
    completed_tasks: any[];
    in_progress_tasks: any[];
    tasks_completed_count: number;
    tasks_in_progress_count: number;
    highlights: string[];
    blockers: string[];
}

interface TeamReports {
    leader: {
        agent_id: string;
        agent_name: string;
        org_member_name?: string;
        report: Report | null;
    };
    members: {
        agent_id: string;
        agent_name: string;
        org_member_name?: string;
        report: Report | null;
    }[];
    report_date: string;
}

interface ConsolidatedReport {
    leader_agent_id: string;
    leader_name: string;
    leader_org_member_name?: string;
    report_date: string;
    consolidated_summary: string;
    statistics: {
        team_size: number;
        total_tasks_completed: number;
        total_tasks_in_progress: number;
        total_tokens_used: number;
    };
    member_summaries: {
        name: string;
        org_member_name?: string;
        summary: string;
        tasks_completed: number;
    }[];
}

// ─── Markdown renderer ───────────────────────────────────

function MarkdownContent({ content }: { content: string }) {
    const html = content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/^### (.*$)/gm, '<h4 style="margin:12px 0 4px;font-size:14px;color:var(--text-primary)">$1</h4>')
        .replace(/^## (.*$)/gm, '<h3 style="margin:16px 0 8px;font-size:15px;color:var(--text-primary)">$1</h3>')
        .replace(/^# (.*$)/gm, '<h2 style="margin:20px 0 10px;font-size:17px;color:var(--text-primary)">$1</h2>')
        .replace(/^- (.*$)/gm, '<div style="padding-left:16px;margin:4px 0">• $1</div>')
        .replace(/\n/g, '<br/>');
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
}

// ─── Main component ──────────────────────────────────────

export default function TeamReports() {
    const { i18n } = useTranslation();
    const isChinese = i18n.language?.startsWith('zh');
    
    const [hierarchy, setHierarchy] = useState<HierarchyResponse | null>(null);
    const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);
    const [selectedLeader, setSelectedLeader] = useState<TeamMember | null>(null);
    const [selectedDate, setSelectedDate] = useState(new Date().toISOString().split('T')[0]);
    const [teamReports, setTeamReports] = useState<TeamReports | null>(null);
    const [consolidatedReport, setConsolidatedReport] = useState<ConsolidatedReport | null>(null);
    const [loading, setLoading] = useState(false);
    const [activeTab, setActiveTab] = useState<'individual' | 'consolidated'>('individual');
    const [expandedDepts, setExpandedDepts] = useState<Set<string>>(new Set());
    const [expandedCenters, setExpandedCenters] = useState<Set<string>>(new Set());

    // Load hierarchy on mount
    useEffect(() => {
        loadHierarchy();
    }, []);

    // Load team reports when leader or date changes
    useEffect(() => {
        if (selectedLeader?.agent) {
            loadTeamReports();
        }
    }, [selectedLeader, selectedDate]);

    const loadHierarchy = async () => {
        try {
            const res = await reportsApi.getHierarchy();
            setHierarchy(res as HierarchyResponse);
            
            // Auto-expand first department and center, select first team
            const firstDept = res.departments?.[0];
            if (firstDept) {
                setExpandedDepts(new Set([firstDept.id]));
                const firstCenter = firstDept.centers?.[0];
                if (firstCenter) {
                    setExpandedCenters(new Set([firstCenter.id]));
                    const firstTeam = firstCenter.teams?.[0];
                    if (firstTeam) {
                        setSelectedTeam(firstTeam);
                        const firstLeader = firstTeam.leaders?.[0];
                        if (firstLeader) {
                            setSelectedLeader(firstLeader);
                        }
                    }
                }
            }
        } catch (err) {
            console.error('Failed to load hierarchy:', err);
        }
    };

    const loadTeamReports = async () => {
        if (!selectedLeader?.agent) return;
        setLoading(true);
        try {
            const [teamRes, consolidatedRes] = await Promise.all([
                reportsApi.getMyTeam(selectedLeader.agent.id, selectedDate),
                reportsApi.getConsolidated(selectedLeader.agent.id, selectedDate),
            ]);
            setTeamReports(teamRes);
            setConsolidatedReport(consolidatedRes);
        } catch (err) {
            console.error('Failed to load team reports:', err);
        } finally {
            setLoading(false);
        }
    };

    const generateReport = async (agentId: string) => {
        try {
            await reportsApi.generateForAgent(agentId, selectedDate);
            loadTeamReports();
        } catch (err) {
            console.error('Failed to generate report:', err);
        }
    };

    const toggleDept = (deptId: string) => {
        const newSet = new Set(expandedDepts);
        if (newSet.has(deptId)) {
            newSet.delete(deptId);
        } else {
            newSet.add(deptId);
        }
        setExpandedDepts(newSet);
    };

    const toggleCenter = (centerId: string) => {
        const newSet = new Set(expandedCenters);
        if (newSet.has(centerId)) {
            newSet.delete(centerId);
        } else {
            newSet.add(centerId);
        }
        setExpandedCenters(newSet);
    };

    // Role badge component
    const RoleBadge = ({ role, scope }: { role: string; scope: string }) => {
        const roleLabels: Record<string, { label: string; color: string }> = {
            platform_admin: { label: isChinese ? '超管' : 'Admin', color: '#ef4444' },
            gm: { label: 'GM', color: '#8b5cf6' },
            director: { label: isChinese ? '总监' : 'Director', color: '#3b82f6' },
            leader: { label: isChinese ? '组长' : 'Leader', color: '#f59e0b' },
            deputy_leader: { label: isChinese ? '副组长' : 'Deputy', color: '#f59e0b' },
            member: { label: isChinese ? '组员' : 'Member', color: '#6b7280' },
        };
        const info = roleLabels[role] || roleLabels.member;
        
        return (
            <span style={{
                fontSize: '10px',
                padding: '2px 6px',
                borderRadius: '4px',
                background: info.color + '20',
                color: info.color,
                fontWeight: 600,
            }}>
                {info.label}
            </span>
        );
    };

    return (
        <div style={{ display: 'flex', height: '100%', background: 'var(--bg-primary)' }}>
            {/* Left sidebar - Hierarchy */}
            <div style={{
                width: '300px',
                borderRight: '1px solid var(--border-subtle)',
                display: 'flex',
                flexDirection: 'column',
            }}>
                {/* Header */}
                <div style={{
                    padding: '20px',
                    borderBottom: '1px solid var(--border-subtle)',
                }}>
                    <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
                        📊 {isChinese ? '团队日报' : 'Team Reports'}
                    </h2>
                    <div style={{ marginTop: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ fontSize: '12px', color: 'var(--text-tertiary)' }}>
                            {isChinese ? '当前身份：' : 'Role: '}
                        </span>
                        <RoleBadge role={hierarchy?.user_role || 'member'} scope={hierarchy?.scope || 'self'} />
                    </div>
                </div>

                {/* Date picker */}
                <div style={{ padding: '12px 20px', borderBottom: '1px solid var(--border-subtle)' }}>
                    <label style={{ fontSize: '12px', color: 'var(--text-secondary)', marginBottom: '6px', display: 'block' }}>
                        {isChinese ? '选择日期' : 'Select Date'}
                    </label>
                    <input
                        type="date"
                        value={selectedDate}
                        onChange={(e) => setSelectedDate(e.target.value)}
                        style={{
                            width: '100%',
                            padding: '8px 12px',
                            borderRadius: '8px',
                            border: '1px solid var(--border-subtle)',
                            background: 'var(--bg-secondary)',
                            color: 'var(--text-primary)',
                            fontSize: '13px',
                        }}
                    />
                </div>

                {/* New three-level hierarchy */}
                <div style={{ flex: 1, overflowY: 'auto', padding: '12px' }}>
                    {hierarchy?.departments.map((dept) => (
                        <div key={dept.id} style={{ marginBottom: '8px' }}>
                            {/* Department header */}
                            <button
                                onClick={() => toggleDept(dept.id)}
                                style={{
                                    width: '100%',
                                    padding: '10px 12px',
                                    borderRadius: '8px',
                                    border: 'none',
                                    background: 'var(--bg-secondary)',
                                    cursor: 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '8px',
                                    textAlign: 'left',
                                }}
                            >
                                <span style={{ 
                                    fontSize: '12px', 
                                    transition: 'transform 0.2s',
                                    transform: expandedDepts.has(dept.id) ? 'rotate(90deg)' : 'rotate(0)',
                                }}>
                                    ▶
                                </span>
                                <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--text-primary)' }}>
                                    🏢 {dept.name}
                                </span>
                            </button>

                            {/* Centers */}
                            {expandedDepts.has(dept.id) && dept.centers.map((center) => (
                                <div key={center.id} style={{ marginLeft: '16px', marginTop: '4px' }}>
                                    {/* Center header */}
                                    <button
                                        onClick={() => toggleCenter(center.id)}
                                        style={{
                                            width: '100%',
                                            padding: '8px 12px',
                                            borderRadius: '6px',
                                            border: 'none',
                                            background: 'transparent',
                                            cursor: 'pointer',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '8px',
                                            textAlign: 'left',
                                        }}
                                    >
                                        <span style={{ 
                                            fontSize: '10px', 
                                            transition: 'transform 0.2s',
                                            transform: expandedCenters.has(center.id) ? 'rotate(90deg)' : 'rotate(0)',
                                        }}>
                                            ▶
                                        </span>
                                        <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                                            📁 {center.name}
                                        </span>
                                        <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                                            {center.teams.length} {isChinese ? '个组' : 'teams'}
                                        </span>
                                    </button>

                                    {/* Teams */}
                                    {expandedCenters.has(center.id) && center.teams.map((team) => (
                                        <div key={team.id} style={{ marginLeft: '16px', marginTop: '4px' }}>
                                            <button
                                                onClick={() => {
                                                    setSelectedTeam(team);
                                                    const leader = team.leaders?.[0];
                                                    if (leader) setSelectedLeader(leader);
                                                }}
                                                style={{
                                                    width: '100%',
                                                    padding: '10px 12px',
                                                    borderRadius: '8px',
                                                    border: 'none',
                                                    background: selectedTeam?.id === team.id
                                                        ? 'var(--accent-subtle)'
                                                        : 'transparent',
                                                    cursor: 'pointer',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    gap: '10px',
                                                    textAlign: 'left',
                                                    transition: 'background 0.15s',
                                                }}
                                            >
                                                <div style={{
                                                    width: '28px',
                                                    height: '28px',
                                                    borderRadius: '6px',
                                                    background: 'linear-gradient(135deg, #f59e0b, #d97706)',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'center',
                                                    fontSize: '12px',
                                                    color: '#fff',
                                                }}>
                                                    👥
                                                </div>
                                                <div style={{ flex: 1, minWidth: 0 }}>
                                                    <div style={{
                                                        fontSize: '13px',
                                                        fontWeight: 500,
                                                        color: 'var(--text-primary)',
                                                        overflow: 'hidden',
                                                        textOverflow: 'ellipsis',
                                                        whiteSpace: 'nowrap',
                                                    }}>
                                                        {team.name}
                                                    </div>
                                                    <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                                                        {team.leaders.length} {isChinese ? '组长' : 'leader(s)'} · {team.members.length} {isChinese ? '组员' : 'members'}
                                                    </div>
                                                </div>
                                            </button>

                                            {/* Show team members when selected */}
                                            {selectedTeam?.id === team.id && (
                                                <div style={{ marginLeft: '20px', marginTop: '4px' }}>
                                                    {/* Leaders */}
                                                    {team.leaders.map((leader) => (
                                                        <div
                                                            key={leader.org_member_id}
                                                            onClick={() => setSelectedLeader(leader)}
                                                            style={{
                                                                padding: '8px 12px',
                                                                fontSize: '12px',
                                                                color: selectedLeader?.org_member_id === leader.org_member_id 
                                                                    ? 'var(--accent)' 
                                                                    : 'var(--text-secondary)',
                                                                display: 'flex',
                                                                alignItems: 'center',
                                                                gap: '8px',
                                                                borderLeft: '2px solid var(--border-subtle)',
                                                                cursor: 'pointer',
                                                                background: selectedLeader?.org_member_id === leader.org_member_id 
                                                                    ? 'var(--accent-subtle)' 
                                                                    : 'transparent',
                                                                borderRadius: '0 4px 4px 0',
                                                            }}
                                                        >
                                                            <span style={{ fontSize: '14px' }}>
                                                                {leader.is_primary ? '👑' : '🎖️'}
                                                            </span>
                                                            <span>{leader.name}</span>
                                                            <span style={{ 
                                                                fontSize: '10px', 
                                                                color: 'var(--text-tertiary)',
                                                                background: '#f59e0b20',
                                                                padding: '1px 4px',
                                                                borderRadius: '3px',
                                                            }}>
                                                                {leader.is_primary 
                                                                    ? (isChinese ? '正组长' : 'Leader') 
                                                                    : (isChinese ? '副组长' : 'Deputy')}
                                                            </span>
                                                            {leader.agent && (
                                                                <span style={{ fontSize: '10px', color: 'var(--text-tertiary)', marginLeft: 'auto' }}>
                                                                    → {leader.agent.name}
                                                                </span>
                                                            )}
                                                        </div>
                                                    ))}
                                                    {/* Regular members */}
                                                    {team.members.map((member) => (
                                                        <div
                                                            key={member.org_member_id}
                                                            style={{
                                                                padding: '6px 12px',
                                                                fontSize: '11px',
                                                                color: 'var(--text-tertiary)',
                                                                display: 'flex',
                                                                alignItems: 'center',
                                                                gap: '6px',
                                                                borderLeft: '2px solid var(--border-subtle)',
                                                            }}
                                                        >
                                                            <span>👤</span>
                                                            <span>{member.name}</span>
                                                            {member.agent && (
                                                                <span style={{ marginLeft: 'auto' }}>
                                                                    → {member.agent.name}
                                                                </span>
                                                            )}
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            ))}
                        </div>
                    ))}

                    {!hierarchy?.departments.length && (
                        <div style={{
                            padding: '40px 20px',
                            textAlign: 'center',
                            color: 'var(--text-tertiary)',
                            fontSize: '13px',
                        }}>
                            <div style={{ fontSize: '32px', marginBottom: '12px' }}>🔒</div>
                            {hierarchy?.scope === 'self' ? (
                                <>
                                    <div>{isChinese ? '您只能查看自己的日报' : 'You can only view your own reports'}</div>
                                    <div style={{ fontSize: '11px', marginTop: '4px' }}>
                                        {isChinese ? '请联系组长查看团队日报' : 'Contact your leader for team reports'}
                                    </div>
                                </>
                            ) : (
                                <div>{isChinese ? '暂无可查看的组织数据' : 'No organization data available'}</div>
                            )}
                        </div>
                    )}
                </div>
            </div>

            {/* Main content */}
            <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
                {selectedTeam && selectedLeader ? (
                    <>
                        {/* Tabs */}
                        <div style={{
                            padding: '16px 24px',
                            borderBottom: '1px solid var(--border-subtle)',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '24px',
                        }}>
                            <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, flex: 1 }}>
                                👥 {selectedTeam.name}
                                <span style={{ 
                                    fontSize: '12px', 
                                    color: 'var(--text-tertiary)', 
                                    fontWeight: 400,
                                    marginLeft: '8px',
                                }}>
                                    {selectedLeader.name} ({selectedLeader.is_primary ? (isChinese ? '正组长' : 'Leader') : (isChinese ? '副组长' : 'Deputy')})
                                </span>
                            </h3>
                            <div style={{ display: 'flex', gap: '8px' }}>
                                <button
                                    onClick={() => setActiveTab('individual')}
                                    style={{
                                        padding: '8px 16px',
                                        borderRadius: '8px',
                                        border: 'none',
                                        background: activeTab === 'individual' ? 'var(--accent)' : 'var(--bg-secondary)',
                                        color: activeTab === 'individual' ? '#fff' : 'var(--text-secondary)',
                                        cursor: 'pointer',
                                        fontSize: '13px',
                                        fontWeight: 500,
                                    }}
                                >
                                    {isChinese ? '个人日报' : 'Individual Reports'}
                                </button>
                                <button
                                    onClick={() => setActiveTab('consolidated')}
                                    style={{
                                        padding: '8px 16px',
                                        borderRadius: '8px',
                                        border: 'none',
                                        background: activeTab === 'consolidated' ? 'var(--accent)' : 'var(--bg-secondary)',
                                        color: activeTab === 'consolidated' ? '#fff' : 'var(--text-secondary)',
                                        cursor: 'pointer',
                                        fontSize: '13px',
                                        fontWeight: 500,
                                    }}
                                >
                                    {isChinese ? '汇总报告' : 'Consolidated Report'}
                                </button>
                            </div>
                        </div>

                        {/* Content */}
                        <div style={{ flex: 1, overflowY: 'auto', padding: '24px' }}>
                            {loading ? (
                                <div style={{ textAlign: 'center', padding: '60px', color: 'var(--text-tertiary)' }}>
                                    {isChinese ? '加载中...' : 'Loading...'}
                                </div>
                            ) : activeTab === 'individual' ? (
                                /* Individual Reports Tab */
                                <div style={{ display: 'grid', gap: '20px' }}>
                                    {/* Leader's report */}
                                    {teamReports?.leader && (
                                        <ReportCard
                                            title={`${teamReports.leader.agent_name} (${isChinese ? '组长' : 'Leader'})`}
                                            report={teamReports.leader.report}
                                            agentId={teamReports.leader.agent_id}
                                            isLeader
                                            isChinese={isChinese}
                                            onGenerate={() => generateReport(teamReports.leader.agent_id)}
                                        />
                                    )}

                                    {/* Members' reports */}
                                    {teamReports?.members.map((member) => (
                                        <ReportCard
                                            key={member.agent_id}
                                            title={member.agent_name}
                                            report={member.report}
                                            agentId={member.agent_id}
                                            isChinese={isChinese}
                                            onGenerate={() => generateReport(member.agent_id)}
                                        />
                                    ))}

                                    {!teamReports?.members.length && !teamReports?.leader && (
                                        <div style={{
                                            textAlign: 'center',
                                            padding: '60px',
                                            color: 'var(--text-tertiary)',
                                        }}>
                                            {selectedLeader?.agent ? (
                                                <div>{isChinese ? '暂无团队数据' : 'No team data'}</div>
                                            ) : (
                                                <>
                                                    <div>{isChinese ? '该组长未绑定数字员工' : 'This leader has no linked agent'}</div>
                                                    <div style={{ fontSize: '12px', marginTop: '8px' }}>
                                                        {isChinese ? '请先在组织架构中绑定数字员工' : 'Please link an agent in org settings first'}
                                                    </div>
                                                </>
                                            )}
                                        </div>
                                    )}
                                </div>
                            ) : (
                                /* Consolidated Report Tab */
                                <div>
                                    {consolidatedReport ? (
                                        <div style={{
                                            background: 'var(--bg-secondary)',
                                            borderRadius: '12px',
                                            border: '1px solid var(--border-subtle)',
                                            overflow: 'hidden',
                                        }}>
                                            {/* Stats header */}
                                            <div style={{
                                                padding: '20px 24px',
                                                borderBottom: '1px solid var(--border-subtle)',
                                                display: 'grid',
                                                gridTemplateColumns: 'repeat(4, 1fr)',
                                                gap: '20px',
                                                background: 'linear-gradient(135deg, var(--accent-subtle), transparent)',
                                            }}>
                                                <StatBox
                                                    label={isChinese ? '团队人数' : 'Team Size'}
                                                    value={consolidatedReport.statistics.team_size}
                                                    icon="👥"
                                                />
                                                <StatBox
                                                    label={isChinese ? '完成任务' : 'Tasks Done'}
                                                    value={consolidatedReport.statistics.total_tasks_completed}
                                                    icon="✅"
                                                />
                                                <StatBox
                                                    label={isChinese ? '进行中' : 'In Progress'}
                                                    value={consolidatedReport.statistics.total_tasks_in_progress}
                                                    icon="🔄"
                                                />
                                                <StatBox
                                                    label={isChinese ? 'Token 消耗' : 'Tokens Used'}
                                                    value={consolidatedReport.statistics.total_tokens_used}
                                                    icon="⚡"
                                                />
                                            </div>

                                            {/* Consolidated summary */}
                                            <div style={{ padding: '24px' }}>
                                                <MarkdownContent content={consolidatedReport.consolidated_summary} />
                                            </div>

                                            {/* Action: Copy or Send to upper leader */}
                                            <div style={{
                                                padding: '16px 24px',
                                                borderTop: '1px solid var(--border-subtle)',
                                                display: 'flex',
                                                gap: '12px',
                                                justifyContent: 'flex-end',
                                            }}>
                                                <button
                                                    onClick={() => {
                                                        navigator.clipboard.writeText(consolidatedReport.consolidated_summary);
                                                        alert(isChinese ? '已复制到剪贴板' : 'Copied to clipboard');
                                                    }}
                                                    style={{
                                                        padding: '10px 20px',
                                                        borderRadius: '8px',
                                                        border: '1px solid var(--border-subtle)',
                                                        background: 'var(--bg-primary)',
                                                        color: 'var(--text-primary)',
                                                        cursor: 'pointer',
                                                        fontSize: '13px',
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        gap: '6px',
                                                    }}
                                                >
                                                    📋 {isChinese ? '复制汇总' : 'Copy Summary'}
                                                </button>
                                                <button
                                                    style={{
                                                        padding: '10px 20px',
                                                        borderRadius: '8px',
                                                        border: 'none',
                                                        background: 'var(--accent)',
                                                        color: '#fff',
                                                        cursor: 'pointer',
                                                        fontSize: '13px',
                                                        display: 'flex',
                                                        alignItems: 'center',
                                                        gap: '6px',
                                                    }}
                                                >
                                                    📤 {isChinese ? '发送给总监' : 'Send to Director'}
                                                </button>
                                            </div>
                                        </div>
                                    ) : (
                                        <div style={{
                                            textAlign: 'center',
                                            padding: '60px',
                                            color: 'var(--text-tertiary)',
                                        }}>
                                            {isChinese ? '暂无汇总数据' : 'No consolidated data'}
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </>
                ) : (
                    <div style={{
                        flex: 1,
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '16px',
                        color: 'var(--text-tertiary)',
                    }}>
                        <div style={{ fontSize: '48px' }}>📊</div>
                        <div style={{ fontSize: '15px' }}>
                            {isChinese ? '请从左侧选择一个组' : 'Select a team from the left panel'}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── Report Card Component ───────────────────────────────

function ReportCard({
    title,
    report,
    agentId,
    isLeader,
    isChinese,
    onGenerate,
}: {
    title: string;
    report: Report | null;
    agentId: string;
    isLeader?: boolean;
    isChinese: boolean;
    onGenerate: () => void;
}) {
    return (
        <div style={{
            background: 'var(--bg-secondary)',
            borderRadius: '12px',
            border: isLeader ? '2px solid var(--accent)' : '1px solid var(--border-subtle)',
            overflow: 'hidden',
        }}>
            {/* Header */}
            <div style={{
                padding: '16px 20px',
                borderBottom: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                background: isLeader ? 'var(--accent-subtle)' : 'transparent',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <span style={{ fontSize: '18px' }}>{isLeader ? '👑' : '👤'}</span>
                    <span style={{ fontWeight: 600, fontSize: '14px' }}>{title}</span>
                </div>
                {report && (
                    <div style={{
                        fontSize: '12px',
                        color: 'var(--text-tertiary)',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '12px',
                    }}>
                        <span>✅ {report.tasks_completed_count}</span>
                        <span>🔄 {report.tasks_in_progress_count}</span>
                    </div>
                )}
            </div>

            {/* Content */}
            <div style={{ padding: '20px' }}>
                {report ? (
                    <>
                        <div style={{ 
                            display: 'flex', 
                            justifyContent: 'space-between', 
                            alignItems: 'flex-start',
                            marginBottom: '12px',
                        }}>
                            <div style={{ fontSize: '14px', lineHeight: 1.6, color: 'var(--text-primary)', flex: 1, whiteSpace: 'pre-wrap' }}>
                                {report.summary || (isChinese ? '暂无摘要' : 'No summary')}
                            </div>
                            <button
                                onClick={onGenerate}
                                style={{
                                    padding: '4px 10px',
                                    borderRadius: '4px',
                                    border: '1px solid var(--border-subtle)',
                                    background: 'transparent',
                                    color: 'var(--text-tertiary)',
                                    cursor: 'pointer',
                                    fontSize: '11px',
                                    marginLeft: '12px',
                                    flexShrink: 0,
                                }}
                                title={isChinese ? '重新生成日报' : 'Regenerate Report'}
                            >
                                🔄 {isChinese ? '刷新' : 'Refresh'}
                            </button>
                        </div>

                        {/* Completed tasks */}
                        {report.completed_tasks?.length > 0 && (
                            <div style={{ marginTop: '16px' }}>
                                <div style={{
                                    fontSize: '12px',
                                    fontWeight: 600,
                                    color: 'var(--text-secondary)',
                                    marginBottom: '8px',
                                }}>
                                    ✅ {isChinese ? '完成的任务' : 'Completed Tasks'}
                                </div>
                                {report.completed_tasks.map((task: any, i: number) => (
                                    <div key={i} style={{
                                        fontSize: '13px',
                                        color: 'var(--text-secondary)',
                                        padding: '4px 0 4px 16px',
                                    }}>
                                        • {task.title}
                                    </div>
                                ))}
                            </div>
                        )}

                        {/* Highlights */}
                        {report.highlights?.length > 0 && (
                            <div style={{ marginTop: '16px' }}>
                                <div style={{
                                    fontSize: '12px',
                                    fontWeight: 600,
                                    color: '#22c55e',
                                    marginBottom: '8px',
                                }}>
                                    ⭐ {isChinese ? '亮点' : 'Highlights'}
                                </div>
                                {report.highlights.map((h: string, i: number) => (
                                    <div key={i} style={{
                                        fontSize: '13px',
                                        color: 'var(--text-secondary)',
                                        padding: '4px 0 4px 16px',
                                    }}>
                                        • {h}
                                    </div>
                                ))}
                            </div>
                        )}
                    </>
                ) : (
                    <div style={{
                        textAlign: 'center',
                        padding: '20px',
                        color: 'var(--text-tertiary)',
                    }}>
                        <div style={{ marginBottom: '12px' }}>
                            {isChinese ? '暂无日报' : 'No report for this date'}
                        </div>
                        <button
                            onClick={onGenerate}
                            style={{
                                padding: '8px 16px',
                                borderRadius: '6px',
                                border: '1px solid var(--accent)',
                                background: 'transparent',
                                color: 'var(--accent)',
                                cursor: 'pointer',
                                fontSize: '12px',
                            }}
                        >
                            {isChinese ? '生成日报' : 'Generate Report'}
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}

// ─── Stat Box Component ──────────────────────────────────

function StatBox({ label, value, icon }: { label: string; value: number; icon: string }) {
    return (
        <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: '24px', marginBottom: '4px' }}>{icon}</div>
            <div style={{ fontSize: '20px', fontWeight: 700, color: 'var(--text-primary)' }}>{value}</div>
            <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>{label}</div>
        </div>
    );
}
