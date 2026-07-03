'use client';
import { useEffect, useState } from 'react';
import { api, clearToken, getToken } from '@/lib/api';

const NAV = [
  { href: '/', label: '📋 今日待办' },
  { href: '/campaigns/', label: '🚀 开发任务' },
  { href: '/brandkit/', label: '🧰 品牌资产库' },
];

interface Me { display_name: string }

export default function AppShell({ active, children }:
  { active: string; children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    if (!getToken()) { window.location.href = '/login/'; return; }
    api<Me>('/api/auth/me').then(setMe).catch(() => {});
  }, []);

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <nav style={{
        width: 200, flexShrink: 0, background: 'var(--panel)',
        borderRight: '1px solid var(--line)', padding: '20px 12px',
        display: 'flex', flexDirection: 'column', gap: 4,
      }}>
        <div style={{ fontWeight: 700, padding: '0 10px 16px' }}>远航开发助手</div>
        {NAV.map((n) => (
          <a key={n.href} href={n.href} style={{
            padding: '8px 12px', borderRadius: 8, textDecoration: 'none',
            color: active === n.href ? 'var(--accent)' : 'var(--muted)',
            background: active === n.href ? 'color-mix(in srgb, var(--accent) 12%, transparent)' : 'none',
            fontWeight: active === n.href ? 600 : 400,
          }}>{n.label}</a>
        ))}
        <div style={{ marginTop: 'auto', padding: '12px 10px', fontSize: 12,
                      color: 'var(--muted)', borderTop: '1px solid var(--line)' }}>
          {me?.display_name ?? '…'} ·{' '}
          <button onClick={() => { clearToken(); window.location.href = '/login/'; }}
                  style={{ background: 'none', border: 0, color: 'var(--accent)',
                           cursor: 'pointer', font: 'inherit', padding: 0 }}>
            退出
          </button>
        </div>
      </nav>
      <main style={{ flex: 1, padding: 24, maxWidth: 1100 }}>{children}</main>
    </div>
  );
}

export const card: React.CSSProperties = {
  background: 'var(--panel)', border: '1px solid var(--line)',
  borderRadius: 12, padding: '16px 20px',
};
export const btn: React.CSSProperties = {
  padding: '7px 14px', border: '1px solid var(--line)', borderRadius: 8,
  background: 'var(--panel)', color: 'var(--ink)', font: 'inherit',
  fontWeight: 550, cursor: 'pointer',
};
export const btnPri: React.CSSProperties = {
  ...btn, background: 'var(--accent)', borderColor: 'var(--accent)', color: 'var(--accent-ink)',
};
export const input: React.CSSProperties = {
  width: '100%', padding: '8px 12px', border: '1px solid var(--line)', borderRadius: 8,
  background: 'var(--ground)', color: 'var(--ink)', font: 'inherit', marginBottom: 10,
};
