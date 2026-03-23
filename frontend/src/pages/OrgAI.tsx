import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../stores';

interface ToolCall {
    name: string;
    args: any;
    result?: string;
}

interface Message {
    role: 'user' | 'assistant' | 'system';
    content: string;
    toolCalls?: ToolCall[];
    timestamp?: string;
}

const TOOL_LABELS: Record<string, string> = {
    query_team_status: '查询团队状态',
    query_person_work: '查询个人工作',
    get_org_overview: '获取组织概览',
    list_departments: '列出部门',
    search_members: '搜索成员',
    query_team_hierarchy: '查询团队层级',
    query_leader_summary: '查询组长汇总',
};

const EXAMPLE_QUESTIONS = [
    '公司目前有多少数字员工在运行？',
    '今天完成了多少任务？',
    '各部门的情况如何？',
    '搜索一下张三的工作情况',
];

function MarkdownContent({ content }: { content: string }) {
    // Simple markdown rendering
    const html = content
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/`(.*?)`/g, '<code style="background:var(--bg-tertiary);padding:1px 4px;border-radius:3px;font-size:12px">$1</code>')
        .replace(/^### (.*$)/gm, '<h4 style="margin:12px 0 4px;font-size:14px">$1</h4>')
        .replace(/^## (.*$)/gm, '<h3 style="margin:12px 0 6px;font-size:15px">$1</h3>')
        .replace(/^# (.*$)/gm, '<h2 style="margin:16px 0 8px;font-size:16px">$1</h2>')
        .replace(/^- (.*$)/gm, '<div style="padding-left:12px">• $1</div>')
        .replace(/\n/g, '<br/>');
    return <div dangerouslySetInnerHTML={{ __html: html }} />;
}

export default function OrgAI() {
    const { i18n } = useTranslation();
    const isChinese = i18n.language?.startsWith('zh');
    const token = useAuthStore((s) => s.token);
    const [messages, setMessages] = useState<Message[]>([]);
    const [input, setInput] = useState('');
    const [connected, setConnected] = useState(false);
    const [isWaiting, setIsWaiting] = useState(false);
    const wsRef = useRef<WebSocket | null>(null);
    const messagesEndRef = useRef<HTMLDivElement>(null);
    const pendingToolCalls = useRef<ToolCall[]>([]);

    // Connect WebSocket
    useEffect(() => {
        if (!token) return;
        const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const wsUrl = `${proto}://${window.location.host}/api/org-ai/ws?token=${token}`;
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => setConnected(true);
        ws.onclose = () => setConnected(false);
        ws.onerror = () => setConnected(false);

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                if (data.type === 'message') {
                    setMessages(prev => [...prev, {
                        role: data.role || 'assistant',
                        content: data.content,
                        toolCalls: pendingToolCalls.current.length > 0 ? [...pendingToolCalls.current] : undefined,
                        timestamp: new Date().toISOString(),
                    }]);
                    pendingToolCalls.current = [];
                    setIsWaiting(false);
                } else if (data.type === 'tool_call') {
                    pendingToolCalls.current.push({
                        name: data.name,
                        args: data.args,
                    });
                } else if (data.type === 'tool_result') {
                    const tc = pendingToolCalls.current.find(t => t.name === data.name && !t.result);
                    if (tc) tc.result = data.result;
                } else if (data.type === 'error') {
                    setMessages(prev => [...prev, {
                        role: 'system',
                        content: data.content,
                        timestamp: new Date().toISOString(),
                    }]);
                    setIsWaiting(false);
                }
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };

        return () => {
            ws.close();
        };
    }, [token]);

    // Auto-scroll
    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, [messages, isWaiting]);

    const sendMessage = (text?: string) => {
        const msg = (text || input).trim();
        if (!msg || !wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;
        setMessages(prev => [...prev, { role: 'user', content: msg, timestamp: new Date().toISOString() }]);
        wsRef.current.send(JSON.stringify({ content: msg }));
        setInput('');
        setIsWaiting(true);
        pendingToolCalls.current = [];
    };

    return (
        <div style={{ display: 'flex', flexDirection: 'column', height: '100%', maxHeight: '100vh' }}>
            {/* Header */}
            <div style={{
                padding: '16px 24px',
                borderBottom: '1px solid var(--border-subtle)',
                display: 'flex', alignItems: 'center', gap: '12px',
            }}>
                <div style={{
                    width: '36px', height: '36px', borderRadius: '10px',
                    background: 'linear-gradient(135deg, var(--accent), #7c3aed)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '18px', color: '#fff',
                }}>
                    🧠
                </div>
                <div>
                    <h2 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>
                        {isChinese ? '组织管理 AI' : 'Organization AI'}
                    </h2>
                    <div style={{ fontSize: '12px', color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <span style={{
                            width: '6px', height: '6px', borderRadius: '50%',
                            background: connected ? '#22c55e' : '#ef4444',
                        }} />
                        {connected
                            ? (isChinese ? '已连接 · 询问任何关于组织的问题' : 'Connected · Ask anything about your org')
                            : (isChinese ? '连接中...' : 'Connecting...')
                        }
                    </div>
                </div>
            </div>

            {/* Messages */}
            <div style={{
                flex: 1, overflowY: 'auto', padding: '24px',
                display: 'flex', flexDirection: 'column', gap: '16px',
            }}>
                {messages.length === 0 && (
                    <div style={{
                        display: 'flex', flexDirection: 'column', alignItems: 'center',
                        justifyContent: 'center', flex: 1, gap: '24px', padding: '40px',
                    }}>
                        <div style={{ fontSize: '48px' }}>🧠</div>
                        <div style={{ textAlign: 'center' }}>
                            <h3 style={{ margin: '0 0 8px', fontWeight: 600 }}>
                                {isChinese ? '组织管理 AI 助手' : 'Organization AI Assistant'}
                            </h3>
                            <p style={{ color: 'var(--text-tertiary)', fontSize: '13px', maxWidth: '400px' }}>
                                {isChinese
                                    ? '我可以帮您了解组织的运作情况。查询团队状态、个人工作进展、部门对比等。'
                                    : 'I can help you understand how your organization is running. Query team status, individual work, department comparisons, and more.'}
                            </p>
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', justifyContent: 'center', maxWidth: '500px' }}>
                            {EXAMPLE_QUESTIONS.map((q, i) => (
                                <button
                                    key={i}
                                    onClick={() => sendMessage(q)}
                                    style={{
                                        padding: '8px 16px', borderRadius: '20px',
                                        border: '1px solid var(--border-subtle)',
                                        background: 'var(--bg-secondary)',
                                        color: 'var(--text-primary)',
                                        cursor: 'pointer', fontSize: '13px',
                                        transition: 'all 0.15s',
                                    }}
                                    onMouseEnter={e => { e.currentTarget.style.borderColor = 'var(--accent)'; e.currentTarget.style.background = 'var(--accent-subtle)'; }}
                                    onMouseLeave={e => { e.currentTarget.style.borderColor = 'var(--border-subtle)'; e.currentTarget.style.background = 'var(--bg-secondary)'; }}
                                >
                                    {q}
                                </button>
                            ))}
                        </div>
                    </div>
                )}

                {messages.map((msg, i) => (
                    <div key={i} style={{
                        display: 'flex',
                        justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                    }}>
                        <div style={{
                            maxWidth: '80%',
                            padding: msg.role === 'system' ? '8px 16px' : '12px 16px',
                            borderRadius: '12px',
                            background: msg.role === 'user'
                                ? 'var(--accent)'
                                : msg.role === 'system'
                                    ? 'rgba(239, 68, 68, 0.1)'
                                    : 'var(--bg-secondary)',
                            color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
                            border: msg.role === 'assistant' ? '1px solid var(--border-subtle)' : 'none',
                            fontSize: '14px',
                            lineHeight: '1.6',
                        }}>
                            {/* Tool calls */}
                            {msg.toolCalls && msg.toolCalls.length > 0 && (
                                <div style={{ marginBottom: '8px', paddingBottom: '8px', borderBottom: '1px solid var(--border-subtle)' }}>
                                    {msg.toolCalls.map((tc, j) => (
                                        <div key={j} style={{
                                            fontSize: '11px', color: 'var(--text-tertiary)',
                                            display: 'flex', alignItems: 'center', gap: '4px',
                                            padding: '2px 0',
                                        }}>
                                            <span>🔧</span>
                                            <span>{TOOL_LABELS[tc.name] || tc.name}</span>
                                            {tc.args && Object.keys(tc.args).length > 0 && (
                                                <span style={{ opacity: 0.7 }}>({Object.values(tc.args).join(', ')})</span>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            )}
                            <MarkdownContent content={msg.content} />
                        </div>
                    </div>
                ))}

                {isWaiting && (
                    <div style={{ display: 'flex', justifyContent: 'flex-start' }}>
                        <div style={{
                            padding: '12px 16px', borderRadius: '12px',
                            background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)',
                            fontSize: '13px', color: 'var(--text-tertiary)',
                            display: 'flex', alignItems: 'center', gap: '8px',
                        }}>
                            <span className="typing-dots" style={{ display: 'flex', gap: '3px' }}>
                                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--text-tertiary)', animation: 'pulse 1.4s infinite', animationDelay: '0s' }} />
                                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--text-tertiary)', animation: 'pulse 1.4s infinite', animationDelay: '0.2s' }} />
                                <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--text-tertiary)', animation: 'pulse 1.4s infinite', animationDelay: '0.4s' }} />
                            </span>
                            {pendingToolCalls.current.length > 0
                                ? `正在 ${TOOL_LABELS[pendingToolCalls.current[pendingToolCalls.current.length - 1]?.name] || '查询'}...`
                                : (isChinese ? '正在思考...' : 'Thinking...')
                            }
                        </div>
                    </div>
                )}

                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div style={{
                padding: '16px 24px',
                borderTop: '1px solid var(--border-subtle)',
                background: 'var(--bg-primary)',
            }}>
                <div style={{
                    display: 'flex', gap: '8px', alignItems: 'flex-end',
                    maxWidth: '800px', margin: '0 auto',
                }}>
                    <textarea
                        value={input}
                        onChange={e => setInput(e.target.value)}
                        onKeyDown={e => {
                            if (e.key === 'Enter' && !e.shiftKey) {
                                e.preventDefault();
                                sendMessage();
                            }
                        }}
                        placeholder={isChinese ? '输入您的问题... (Enter 发送)' : 'Type your question... (Enter to send)'}
                        style={{
                            flex: 1,
                            padding: '10px 14px',
                            borderRadius: '10px',
                            border: '1px solid var(--border-subtle)',
                            background: 'var(--bg-secondary)',
                            color: 'var(--text-primary)',
                            fontSize: '14px',
                            resize: 'none',
                            minHeight: '44px',
                            maxHeight: '120px',
                            outline: 'none',
                            fontFamily: 'inherit',
                        }}
                        rows={1}
                        disabled={!connected || isWaiting}
                    />
                    <button
                        onClick={() => sendMessage()}
                        disabled={!connected || !input.trim() || isWaiting}
                        style={{
                            padding: '10px 20px',
                            borderRadius: '10px',
                            background: connected && input.trim() ? 'var(--accent)' : 'var(--bg-tertiary)',
                            color: connected && input.trim() ? '#fff' : 'var(--text-tertiary)',
                            border: 'none',
                            cursor: connected && input.trim() ? 'pointer' : 'not-allowed',
                            fontSize: '14px',
                            fontWeight: 500,
                            transition: 'all 0.15s',
                        }}
                    >
                        {isChinese ? '发送' : 'Send'}
                    </button>
                </div>
            </div>

            {/* Typing animation */}
            <style>{`
                @keyframes pulse {
                    0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
                    40% { opacity: 1; transform: scale(1); }
                }
            `}</style>
        </div>
    );
}
