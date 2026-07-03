'use client';
import { useEffect, useState } from 'react';
import { api, getToken } from '@/lib/api';

interface Me { display_name: string; email: string; role: string }

export default function TodayPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [health, setHealth] = useState('检测中…');

  useEffect(() => {
    api<{ status: string }>('/api/health')
      .then((h) => setHealth(h.status === 'ok' ? '后端连接正常' : '后端异常'))
      .catch(() => setHealth('后端未启动'));
    if (getToken()) {
      api<Me>('/api/auth/me').then(setMe).catch(() => {});
    }
  }, []);

  return (
    <main style={{ maxWidth: 720, margin: '48px auto', padding: '0 24px' }}>
      <h1 style={{ fontSize: 22 }}>
        {me ? `早上好，${me.display_name} ☀️` : '远航开发助手'}
      </h1>
      <p style={{ color: 'var(--muted)' }}>
        今日待办工作台（M1 施工中）—— 热线索 · 待审批开发信 · 昨夜战报
      </p>
      <div style={{
        background: 'var(--panel)', border: '1px solid var(--line)',
        borderRadius: 12, padding: '16px 20px',
      }}>
        <div>系统状态：{health}</div>
        {!me && (
          <div style={{ marginTop: 8 }}>
            <a href="/login/" style={{ color: 'var(--accent)' }}>登录 / 注册 →</a>
          </div>
        )}
      </div>
    </main>
  );
}
