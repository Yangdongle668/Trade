'use client';
import { useState } from 'react';
import { api, setToken } from '@/lib/api';

interface TokenOut { access_token: string }

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [company, setCompany] = useState('');
  const [error, setError] = useState('');

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const body = mode === 'login'
        ? { email, password }
        : { email, password, company_name: company };
      const r = await api<TokenOut>(`/api/auth/${mode}`, {
        method: 'POST', body: JSON.stringify(body),
      });
      setToken(r.access_token);
      window.location.href = '/';
    } catch (err) {
      setError((err as Error).message);
    }
  }

  const input = {
    width: '100%', padding: '9px 12px', marginBottom: 10,
    border: '1px solid var(--line)', borderRadius: 8,
    background: 'var(--ground)', color: 'var(--ink)', font: 'inherit',
  } as const;

  return (
    <main style={{ maxWidth: 380, margin: '80px auto', padding: '0 24px' }}>
      <h1 style={{ fontSize: 20 }}>{mode === 'login' ? '登录' : '注册新团队'}</h1>
      <form onSubmit={submit} style={{
        background: 'var(--panel)', border: '1px solid var(--line)',
        borderRadius: 12, padding: 20,
      }}>
        {mode === 'register' && (
          <input style={input} placeholder="公司名称" value={company}
                 onChange={(e) => setCompany(e.target.value)} required />
        )}
        <input style={input} type="email" placeholder="邮箱" value={email}
               onChange={(e) => setEmail(e.target.value)} required />
        <input style={input} type="password" placeholder="密码（至少 8 位）" value={password}
               onChange={(e) => setPassword(e.target.value)} required minLength={8} />
        {error && <div style={{ color: 'var(--hot)', marginBottom: 10 }}>{error}</div>}
        <button type="submit" style={{
          width: '100%', padding: '9px 0', border: 0, borderRadius: 8,
          background: 'var(--accent)', color: 'var(--accent-ink)',
          font: 'inherit', fontWeight: 600, cursor: 'pointer',
        }}>
          {mode === 'login' ? '登录' : '创建团队并开始'}
        </button>
      </form>
      <p style={{ textAlign: 'center' }}>
        <button onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
                style={{ background: 'none', border: 0, color: 'var(--accent)',
                         cursor: 'pointer', font: 'inherit' }}>
          {mode === 'login' ? '没有账号？注册 →' : '已有账号？登录 →'}
        </button>
      </p>
    </main>
  );
}
