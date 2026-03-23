import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
    ReactFlow,
    Background,
    Controls,
    MiniMap,
    useNodesState,
    useEdgesState,
    type Node,
    type Edge,
    MarkerType,
    Position,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';

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

interface DigitalEmployee {
    binding_id: string;
    agent_id: string;
    agent_name: string | null;
    agent_avatar: string | null;
    agent_status: string | null;
    user_id: string;
    user_name: string | null;
    org_role: string;  // "leader" | "member"
    is_active: boolean;
}

interface DeptWithAgents {
    id: string;
    name: string;
    parent_id: string | null;
    path: string;
    member_count: number;
    digital_employees: DigitalEmployee[];
}

// Custom node component for departments with digital employees
function DeptNodeComponent({ data }: { data: any }) {
    const isChinese = localStorage.getItem('i18nextLng')?.startsWith('zh');
    return (
        <div style={{
            padding: '12px 16px',
            borderRadius: '12px',
            background: data.isRoot ? 'linear-gradient(135deg, #6366f1, #8b5cf6)' : 'var(--bg-secondary)',
            border: `2px solid ${data.isRoot ? 'transparent' : 'var(--border-default)'}`,
            color: data.isRoot ? '#fff' : 'var(--text-primary)',
            minWidth: '180px',
            maxWidth: '240px',
            boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
            cursor: 'pointer',
            transition: 'all 0.2s',
        }}>
            <div style={{ fontWeight: 600, fontSize: '14px', marginBottom: '6px' }}>
                {data.label}
            </div>
            <div style={{ fontSize: '11px', opacity: 0.8, marginBottom: '8px' }}>
                👤 {data.memberCount} {isChinese ? '人' : 'members'}
            </div>
            {data.digitalEmployees && data.digitalEmployees.length > 0 && (
                <div style={{
                    borderTop: `1px solid ${data.isRoot ? 'rgba(255,255,255,0.3)' : 'var(--border-subtle)'}`,
                    paddingTop: '8px',
                    marginTop: '4px',
                }}>
                    <div style={{ fontSize: '10px', opacity: 0.7, marginBottom: '4px' }}>
                        🤖 {isChinese ? '数字员工' : 'Digital Employees'}
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        {data.digitalEmployees.slice(0, 4).map((de: DigitalEmployee) => (
                            <div
                                key={de.binding_id}
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '4px',
                                    padding: '2px 6px',
                                    borderRadius: '4px',
                                    background: data.isRoot ? 'rgba(255,255,255,0.2)' : 'var(--bg-tertiary)',
                                    fontSize: '10px',
                                    border: de.org_role === 'leader' ? '1px solid var(--accent)' : 'none',
                                }}
                                title={`${de.agent_name}${de.org_role === 'leader' ? ' (组长)' : ''} (${isChinese ? '绑定' : 'bound to'}: ${de.user_name})`}
                            >
                                {de.agent_avatar ? (
                                    <img src={de.agent_avatar} alt="" style={{ width: 14, height: 14, borderRadius: '50%' }} />
                                ) : (
                                    <span>🤖</span>
                                )}
                                <span style={{ maxWidth: '60px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                    {de.agent_name || 'Agent'}
                                </span>
                                <span style={{
                                    width: 6, height: 6, borderRadius: '50%',
                                    background: de.agent_status === 'running' ? '#22c55e' : de.agent_status === 'idle' ? '#eab308' : '#9ca3af',
                                }} />
                            </div>
                        ))}
                        {data.digitalEmployees.length > 4 && (
                            <div style={{ fontSize: '10px', opacity: 0.7 }}>
                                +{data.digitalEmployees.length - 4}
                            </div>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

const nodeTypes = { dept: DeptNodeComponent };

// Build tree from flat array
interface TreeNode extends DeptWithAgents {
    children: TreeNode[];
}

function buildTree(departments: DeptWithAgents[]): TreeNode[] {
    const map = new Map<string, TreeNode>();
    const roots: TreeNode[] = [];
    departments.forEach(d => map.set(d.id, { ...d, children: [] }));
    departments.forEach(d => {
        const node = map.get(d.id)!;
        if (d.parent_id && map.has(d.parent_id)) {
            map.get(d.parent_id)!.children.push(node);
        } else {
            roots.push(node);
        }
    });
    return roots;
}

// Layout tree nodes
function layoutTree(roots: TreeNode[]): { nodes: Node[]; edges: Edge[] } {
    const nodes: Node[] = [];
    const edges: Edge[] = [];
    const X_SPACING = 260;
    const Y_SPACING = 160;

    let xOffset = 0;

    function traverse(node: TreeNode, depth: number, parentId?: string): number {
        if (node.children.length === 0) {
            const x = xOffset;
            xOffset += X_SPACING;
            nodes.push({
                id: node.id,
                type: 'dept',
                position: { x, y: depth * Y_SPACING },
                data: {
                    label: node.name,
                    memberCount: node.member_count || 0,
                    isRoot: depth === 0,
                    digitalEmployees: node.digital_employees,
                },
                sourcePosition: Position.Bottom,
                targetPosition: Position.Top,
            });
            if (parentId) {
                edges.push({
                    id: `${parentId}-${node.id}`,
                    source: parentId,
                    target: node.id,
                    type: 'smoothstep',
                    markerEnd: { type: MarkerType.ArrowClosed },
                    style: { stroke: 'var(--border-default)', strokeWidth: 2 },
                });
            }
            return x;
        }

        const childXs: number[] = [];
        for (const child of node.children) {
            childXs.push(traverse(child, depth + 1, node.id));
        }
        const x = (childXs[0] + childXs[childXs.length - 1]) / 2;

        nodes.push({
            id: node.id,
            type: 'dept',
            position: { x, y: depth * Y_SPACING },
            data: {
                label: node.name,
                memberCount: node.member_count || 0,
                isRoot: depth === 0,
                digitalEmployees: node.digital_employees,
            },
            sourcePosition: Position.Bottom,
            targetPosition: Position.Top,
        });

        if (parentId) {
            edges.push({
                id: `${parentId}-${node.id}`,
                source: parentId,
                target: node.id,
                type: 'smoothstep',
                markerEnd: { type: MarkerType.ArrowClosed },
                style: { stroke: 'var(--border-default)', strokeWidth: 2 },
            });
        }

        return x;
    }

    for (const root of roots) {
        traverse(root, 0);
        xOffset += X_SPACING;
    }

    return { nodes, edges };
}

export default function OrgChart() {
    const { t } = useTranslation();
    const isChinese = localStorage.getItem('i18nextLng')?.startsWith('zh');
    const [departments, setDepartments] = useState<DeptWithAgents[]>([]);
    const [nodes, setNodes, onNodesChange] = useNodesState([]);
    const [edges, setEdges, onEdgesChange] = useEdgesState([]);
    const [loading, setLoading] = useState(true);
    const [selectedDept, setSelectedDept] = useState<DeptWithAgents | null>(null);

    const loadOrgChart = useCallback(async () => {
        setLoading(true);
        try {
            // Fetch org chart with digital employees from bindings API
            const data = await fetchJson<DeptWithAgents[]>('/bindings/org-chart');
            setDepartments(data);

            // Build tree and layout
            const tree = buildTree(data);
            const layout = layoutTree(tree);
            setNodes(layout.nodes);
            setEdges(layout.edges);
        } catch (e) {
            console.error('Failed to load org chart:', e);
            // Fallback: try loading from org departments directly
            try {
                const deptData = await fetchJson<any[]>('/org/departments');
                const flat: DeptWithAgents[] = [];
                function flatten(nodes: any[]) {
                    for (const n of nodes) {
                        flat.push({
                            id: n.id,
                            name: n.name,
                            parent_id: n.parent_id,
                            path: n.path || '',
                            member_count: n.member_count || 0,
                            digital_employees: [],
                        });
                        if (n.children) flatten(n.children);
                    }
                }
                flatten(deptData);
                setDepartments(flat);
                const tree = buildTree(flat);
                const layout = layoutTree(tree);
                setNodes(layout.nodes);
                setEdges(layout.edges);
            } catch (e2) {
                console.error('Failed to load departments:', e2);
            }
        }
        setLoading(false);
    }, [setNodes, setEdges]);

    useEffect(() => { loadOrgChart(); }, [loadOrgChart]);

    const handleNodeClick = useCallback((_event: any, node: Node) => {
        const dept = departments.find(d => d.id === node.id);
        setSelectedDept(dept || null);
    }, [departments]);

    const totalDigitalEmployees = departments.reduce((sum, d) => sum + d.digital_employees.length, 0);

    return (
        <div>
            <div className="page-header">
                <div>
                    <h1 className="page-title">{isChinese ? '组织架构' : 'Organization Chart'}</h1>
                    <p style={{ fontSize: '13px', color: 'var(--text-tertiary)', marginTop: '4px' }}>
                        {isChinese
                            ? '可视化查看组织架构及各部门的数字员工（数据从公司设置同步）'
                            : 'View organization structure and digital employees (synced from company settings)'}
                    </p>
                </div>
                <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
                    <div style={{ fontSize: '13px', color: 'var(--text-secondary)' }}>
                        <span style={{ marginRight: '16px' }}>🏢 {departments.length} {isChinese ? '部门' : 'Depts'}</span>
                        <span>🤖 {totalDigitalEmployees} {isChinese ? '数字员工' : 'Digital Employees'}</span>
                    </div>
                    <button className="btn btn-secondary" onClick={loadOrgChart} disabled={loading}>
                        {loading ? (isChinese ? '加载中...' : 'Loading...') : (isChinese ? '刷新' : 'Refresh')}
                    </button>
                </div>
            </div>

            <div style={{ display: 'flex', gap: '16px' }}>
                {/* Main chart */}
                <div className="card" style={{ flex: 1, height: '600px', padding: 0, overflow: 'hidden' }}>
                    {loading ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%' }}>
                            <div style={{ textAlign: 'center', color: 'var(--text-tertiary)' }}>
                                <div style={{ fontSize: '32px', marginBottom: '8px' }}>⏳</div>
                                <div>{isChinese ? '加载组织架构...' : 'Loading org chart...'}</div>
                            </div>
                        </div>
                    ) : departments.length === 0 ? (
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-tertiary)' }}>
                            <div style={{ textAlign: 'center' }}>
                                <div style={{ fontSize: '48px', marginBottom: '12px' }}>🏢</div>
                                <div>{isChinese ? '暂无组织架构数据' : 'No organization data'}</div>
                                <div style={{ fontSize: '12px', marginTop: '4px' }}>
                                    {isChinese
                                        ? '请在「公司设置 → 组织架构」中同步飞书通讯录'
                                        : 'Please sync from Feishu in Company Settings → Organization'}
                                </div>
                            </div>
                        </div>
                    ) : (
                        <ReactFlow
                            nodes={nodes}
                            edges={edges}
                            onNodesChange={onNodesChange}
                            onEdgesChange={onEdgesChange}
                            onNodeClick={handleNodeClick}
                            nodeTypes={nodeTypes}
                            fitView
                            fitViewOptions={{ padding: 0.3 }}
                            minZoom={0.2}
                            maxZoom={2}
                            attributionPosition="bottom-left"
                        >
                            <Background gap={20} size={1} />
                            <Controls />
                            <MiniMap
                                style={{ background: 'var(--bg-tertiary)' }}
                                maskColor="rgba(0,0,0,0.2)"
                            />
                        </ReactFlow>
                    )}
                </div>

                {/* Sidebar: selected department details */}
                {selectedDept && (
                    <div className="card" style={{ width: '300px', maxHeight: '600px', overflow: 'auto' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                            <h3 style={{ margin: 0, fontSize: '16px' }}>{selectedDept.name}</h3>
                            <button
                                className="btn btn-ghost"
                                style={{ padding: '4px 8px', fontSize: '12px' }}
                                onClick={() => setSelectedDept(null)}
                            >
                                ✕
                            </button>
                        </div>

                        <div style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '16px' }}>
                            👤 {selectedDept.member_count} {isChinese ? '名员工' : 'members'}
                        </div>

                        <div>
                            <h4 style={{ fontSize: '13px', fontWeight: 600, marginBottom: '8px' }}>
                                🤖 {isChinese ? '数字员工' : 'Digital Employees'} ({selectedDept.digital_employees.length})
                            </h4>
                            {selectedDept.digital_employees.length === 0 ? (
                                <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', padding: '12px', textAlign: 'center' }}>
                                    {isChinese ? '该部门暂无数字员工' : 'No digital employees in this department'}
                                </div>
                            ) : (
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                                    {selectedDept.digital_employees.map(de => (
                                        <div
                                            key={de.binding_id}
                                            style={{
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '10px',
                                                padding: '10px 12px',
                                                borderRadius: '8px',
                                                background: 'var(--bg-tertiary)',
                                                border: de.org_role === 'leader' ? '2px solid var(--accent)' : '1px solid var(--border-subtle)',
                                            }}
                                        >
                                            {de.agent_avatar ? (
                                                <img src={de.agent_avatar} alt="" style={{ width: 32, height: 32, borderRadius: '50%' }} />
                                            ) : (
                                                <div style={{
                                                    width: 32, height: 32, borderRadius: '50%',
                                                    background: 'var(--accent-primary)',
                                                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                                                    fontSize: '16px',
                                                }}>🤖</div>
                                            )}
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                                    <span style={{ fontWeight: 500, fontSize: '13px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                                                        {de.agent_name || 'Agent'}
                                                    </span>
                                                    {de.org_role === 'leader' && (
                                                        <span style={{
                                                            padding: '1px 6px', borderRadius: '4px', fontSize: '10px',
                                                            background: 'var(--accent)', color: 'white', fontWeight: 600,
                                                        }}>
                                                            {isChinese ? '组长' : 'Leader'}
                                                        </span>
                                                    )}
                                                </div>
                                                <div style={{ fontSize: '11px', color: 'var(--text-tertiary)' }}>
                                                    {isChinese ? '绑定' : 'Bound to'}: {de.user_name || '-'}
                                                </div>
                                            </div>
                                            <select
                                                value={de.org_role}
                                                onChange={async (e) => {
                                                    const newRole = e.target.value;
                                                    try {
                                                        await fetchJson(`/bindings/${de.binding_id}`, {
                                                            method: 'PATCH',
                                                            body: JSON.stringify({ org_role: newRole }),
                                                        });
                                                        loadOrgChart(); // Refresh
                                                    } catch (err: any) {
                                                        alert(err.message || 'Failed to update role');
                                                    }
                                                }}
                                                style={{
                                                    padding: '3px 6px', borderRadius: '4px', fontSize: '11px',
                                                    border: '1px solid var(--border-subtle)', background: 'var(--bg-secondary)',
                                                    cursor: 'pointer',
                                                }}
                                                title={isChinese ? '设置组织角色' : 'Set organization role'}
                                            >
                                                <option value="member">{isChinese ? '组员' : 'Member'}</option>
                                                <option value="leader">{isChinese ? '组长' : 'Leader'}</option>
                                            </select>
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
