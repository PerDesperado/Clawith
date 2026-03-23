import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '../stores';
import { authApi } from '../services/api';

// Change Password Modal for first-time login
function ChangePasswordModal({
    onSuccess,
    onClose,
    isChinese,
}: {
    onSuccess: () => void;
    onClose: () => void;
    isChinese: boolean;
}) {
    const [oldPassword, setOldPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [confirmPassword, setConfirmPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');

        if (newPassword !== confirmPassword) {
            setError(isChinese ? '两次输入的密码不一致' : 'Passwords do not match');
            return;
        }

        if (newPassword.length < 6) {
            setError(isChinese ? '新密码至少6个字符' : 'New password must be at least 6 characters');
            return;
        }

        setLoading(true);
        try {
            const token = localStorage.getItem('token');
            const res = await fetch('/api/auth/me/password', {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    ...(token ? { Authorization: `Bearer ${token}` } : {}),
                },
                body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
            });

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || 'Failed to change password');
            }

            onSuccess();
        } catch (err: any) {
            setError(err.message || (isChinese ? '修改密码失败' : 'Failed to change password'));
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center',
            zIndex: 10000,
        }}>
            <div style={{
                background: 'var(--bg-primary)',
                borderRadius: '16px',
                padding: '32px',
                width: '100%',
                maxWidth: '400px',
                boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
            }}>
                <div style={{ textAlign: 'center', marginBottom: '24px' }}>
                    <div style={{ fontSize: '48px', marginBottom: '12px' }}>🔐</div>
                    <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 600 }}>
                        {isChinese ? '请修改密码' : 'Change Your Password'}
                    </h2>
                    <p style={{ margin: '8px 0 0', fontSize: '14px', color: 'var(--text-secondary)' }}>
                        {isChinese 
                            ? '这是您首次登录，请设置一个新密码'
                            : 'This is your first login. Please set a new password.'
                        }
                    </p>
                </div>

                {error && (
                    <div style={{
                        background: 'rgba(255,80,80,0.1)',
                        border: '1px solid rgba(255,80,80,0.3)',
                        borderRadius: '8px',
                        padding: '10px 14px',
                        marginBottom: '16px',
                        color: '#ff5050',
                        fontSize: '13px',
                    }}>
                        ⚠ {error}
                    </div>
                )}

                <form onSubmit={handleSubmit}>
                    <div style={{ marginBottom: '16px' }}>
                        <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', fontWeight: 500 }}>
                            {isChinese ? '当前密码' : 'Current Password'}
                        </label>
                        <input
                            type="password"
                            value={oldPassword}
                            onChange={e => setOldPassword(e.target.value)}
                            required
                            placeholder={isChinese ? '输入管理员提供的初始密码' : 'Enter initial password from admin'}
                            style={{
                                width: '100%',
                                padding: '12px 14px',
                                borderRadius: '8px',
                                border: '1px solid var(--border-subtle)',
                                background: 'var(--bg-secondary)',
                                fontSize: '14px',
                            }}
                        />
                    </div>
                    <div style={{ marginBottom: '16px' }}>
                        <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', fontWeight: 500 }}>
                            {isChinese ? '新密码' : 'New Password'}
                        </label>
                        <input
                            type="password"
                            value={newPassword}
                            onChange={e => setNewPassword(e.target.value)}
                            required
                            minLength={6}
                            placeholder={isChinese ? '至少6个字符' : 'At least 6 characters'}
                            style={{
                                width: '100%',
                                padding: '12px 14px',
                                borderRadius: '8px',
                                border: '1px solid var(--border-subtle)',
                                background: 'var(--bg-secondary)',
                                fontSize: '14px',
                            }}
                        />
                    </div>
                    <div style={{ marginBottom: '24px' }}>
                        <label style={{ display: 'block', marginBottom: '6px', fontSize: '13px', fontWeight: 500 }}>
                            {isChinese ? '确认新密码' : 'Confirm New Password'}
                        </label>
                        <input
                            type="password"
                            value={confirmPassword}
                            onChange={e => setConfirmPassword(e.target.value)}
                            required
                            placeholder={isChinese ? '再次输入新密码' : 'Re-enter new password'}
                            style={{
                                width: '100%',
                                padding: '12px 14px',
                                borderRadius: '8px',
                                border: '1px solid var(--border-subtle)',
                                background: 'var(--bg-secondary)',
                                fontSize: '14px',
                            }}
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={loading}
                        style={{
                            width: '100%',
                            padding: '14px',
                            borderRadius: '10px',
                            border: 'none',
                            background: 'var(--accent-color)',
                            color: '#fff',
                            fontSize: '15px',
                            fontWeight: 600,
                            cursor: loading ? 'not-allowed' : 'pointer',
                            opacity: loading ? 0.7 : 1,
                        }}
                    >
                        {loading 
                            ? (isChinese ? '修改中...' : 'Changing...')
                            : (isChinese ? '确认修改密码' : 'Confirm Password Change')
                        }
                    </button>
                </form>
            </div>
        </div>
    );
}

export default function Login() {
    const { t, i18n } = useTranslation();
    const navigate = useNavigate();
    const setAuth = useAuthStore((s) => s.setAuth);
    const [isRegister, setIsRegister] = useState(false);
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    
    // Must change password modal
    const [showChangePassword, setShowChangePassword] = useState(false);
    const [pendingRedirect, setPendingRedirect] = useState<string | null>(null);

    const [form, setForm] = useState({
        username: '',
        password: '',
        email: '',
    });

    const isChinese = i18n.language?.startsWith('zh');

    // Login page always uses dark theme (hero panel is dark)
    useEffect(() => {
        document.documentElement.setAttribute('data-theme', 'dark');
    }, []);

    const toggleLang = () => {
        i18n.changeLanguage(i18n.language === 'zh' ? 'en' : 'zh');
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            let res;
            if (isRegister) {
                res = await authApi.register({
                    ...form,
                    display_name: form.username,
                });
            } else {
                res = await authApi.login({ username: form.username, password: form.password });
            }
            setAuth(res.user, res.access_token);
            
            // Check if user must change password
            if (res.must_change_password) {
                // Store the intended redirect
                setPendingRedirect(res.needs_company_setup ? '/setup-company' : '/');
                setShowChangePassword(true);
            } else if (res.needs_company_setup) {
                navigate('/setup-company');
            } else {
                navigate('/');
            }
        } catch (err: any) {
            const msg = err.message || '';
            // Server-returned error messages (e.g. disabled company, invalid credentials)
            if (msg && msg !== 'Failed to fetch' && !msg.includes('NetworkError') && !msg.includes('ERR_CONNECTION')) {
                // Translate known error messages
                if (msg.includes('company has been disabled')) {
                    setError(t('auth.companyDisabled', 'Your company has been disabled. Please contact the platform administrator.'));
                } else if (msg.includes('Invalid credentials')) {
                    setError(t('auth.invalidCredentials', 'Invalid username or password.'));
                } else if (msg.includes('Account is disabled')) {
                    setError(t('auth.accountDisabled', 'Your account has been disabled.'));
                } else if (msg.includes('500') || msg.includes('Internal Server Error')) {
                    setError(t('auth.serverStarting', 'Service is starting up or experiencing issues. Please try again in a few seconds.'));
                } else {
                    setError(msg);
                }
            } else {
                setError(t('auth.serverUnreachable', 'Unable to reach server. Please check if the service is running and try again.'));
            }
        } finally {
            setLoading(false);
        }
    };
    
    const handlePasswordChanged = () => {
        setShowChangePassword(false);
        navigate(pendingRedirect || '/');
    };

    return (
        <div className="login-page">
            {/* Change Password Modal */}
            {showChangePassword && (
                <ChangePasswordModal
                    onSuccess={handlePasswordChanged}
                    onClose={() => setShowChangePassword(false)}
                    isChinese={isChinese}
                />
            )}
            
            {/* ── Left: Branding Panel ── */}
            <div className="login-hero">
                <div className="login-hero-bg" />
                <div className="login-hero-content">
                    <div className="login-hero-badge">
                        <span className="login-hero-badge-dot" />
                        Open Source · Multi-Agent Collaboration
                    </div>
                    <h1 className="login-hero-title">
                        Clawith<br />
                        <span style={{ fontSize: '0.65em', fontWeight: 600, opacity: 0.85 }}>OpenClaw for Teams</span>
                    </h1>
                    <p className="login-hero-desc">
                        OpenClaw empowers individuals.<br />
                        Clawith scales it to frontier organizations.
                    </p>
                    <div className="login-hero-features">
                        <div className="login-hero-feature">
                            <span className="login-hero-feature-icon">🤖</span>
                            <div>
                                <div className="login-hero-feature-title">Multi-Agent Crew</div>
                                <div className="login-hero-feature-desc">Agents collaborate autonomously</div>
                            </div>
                        </div>
                        <div className="login-hero-feature">
                            <span className="login-hero-feature-icon">🧠</span>
                            <div>
                                <div className="login-hero-feature-title">Persistent Memory</div>
                                <div className="login-hero-feature-desc">Soul, memory, and self-evolution</div>
                            </div>
                        </div>
                        <div className="login-hero-feature">
                            <span className="login-hero-feature-icon">🏛️</span>
                            <div>
                                <div className="login-hero-feature-title">Agent Plaza</div>
                                <div className="login-hero-feature-desc">Social feed for inter-agent interaction</div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            {/* ── Right: Form Panel ── */}
            <div className="login-form-panel">
                {/* Language Switcher */}
                <div style={{
                    position: 'absolute', top: '16px', right: '16px',
                    cursor: 'pointer', fontSize: '13px', color: 'var(--text-secondary)',
                    display: 'flex', alignItems: 'center', gap: '4px',
                    padding: '6px 12px', borderRadius: '8px',
                    background: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)',
                    zIndex: 101,
                }} onClick={toggleLang}>
                    🌐 {i18n.language === 'zh' ? 'EN' : '中文'}
                </div>

                <div className="login-form-wrapper">
                    <div className="login-form-header">
                        <div className="login-form-logo"><img src="/logo-black.png" className="login-logo-img" alt="" style={{ width: 28, height: 28, marginRight: 8, verticalAlign: 'middle' }} />Clawith</div>
                        <h2 className="login-form-title">
                            {isRegister ? t('auth.register') : t('auth.login')}
                        </h2>
                        <p className="login-form-subtitle">
                            {isRegister ? t('auth.subtitleRegister') : t('auth.subtitleLogin')}
                        </p>
                    </div>

                    {error && (
                        <div className="login-error">
                            <span>⚠</span> {error}
                        </div>
                    )}

                    <form onSubmit={handleSubmit} className="login-form">
                        <div className="login-field">
                            <label>{t('auth.username')}</label>
                            <input
                                value={form.username}
                                onChange={(e) => setForm({ ...form, username: e.target.value })}
                                required
                                autoFocus
                                placeholder={t('auth.usernamePlaceholder')}
                            />
                        </div>

                        {isRegister && (
                            <div className="login-field">
                                <label>{t('auth.email')}</label>
                                <input
                                    type="email"
                                    value={form.email}
                                    onChange={(e) => setForm({ ...form, email: e.target.value })}
                                    required
                                    placeholder={t('auth.emailPlaceholder')}
                                />
                            </div>
                        )}

                        <div className="login-field">
                            <label>{t('auth.password')}</label>
                            <input
                                type="password"
                                value={form.password}
                                onChange={(e) => setForm({ ...form, password: e.target.value })}
                                required
                                placeholder={t('auth.passwordPlaceholder')}
                            />
                        </div>

                        <button className="login-submit" type="submit" disabled={loading}>
                            {loading ? (
                                <span className="login-spinner" />
                            ) : (
                                <>
                                    {isRegister ? t('auth.register') : t('auth.login')}
                                    <span style={{ marginLeft: '6px' }}>→</span>
                                </>
                            )}
                        </button>
                    </form>

                    <div className="login-switch">
                        {isRegister ? t('auth.hasAccount') : t('auth.noAccount')}{' '}
                        <a href="#" onClick={(e) => { e.preventDefault(); setIsRegister(!isRegister); setError(''); }}>
                            {isRegister ? t('auth.goLogin') : t('auth.goRegister')}
                        </a>
                    </div>
                </div>
            </div>
        </div>
    );
}
