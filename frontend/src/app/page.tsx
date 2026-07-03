'use client';
import { useEffect, useState } from 'react';
import AppShell, { card } from '@/components/AppShell';
import { api, getToken } from '@/lib/api';

interface Me { display_name: string }
interface Campaign { id: string; name: string; status: string }

export default function TodayPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);

  useEffect(() => {
    if (!getToken()) return; // AppShell 会跳登录
    api<Me>('/api/auth/me').then(setMe).catch(() => {});
    api<Campaign[]>('/api/campaigns').then(setCampaigns).catch(() => {});
  }, []);

  return (
    <AppShell active="/">
      <h1 style={{ fontSize: 20 }}>{me ? `早上好，${me.display_name} ☀️` : '今日待办'}</h1>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={card}>
          <b>🔥 热线索</b>
          <p style={{ color: 'var(--muted)', margin: '6px 0 0' }}>
            暂无——客户回复后会第一时间出现在这里（M3 交付回复处理）。
          </p>
        </div>
        <div style={card}>
          <b>✍️ 待审批开发信</b>
          <p style={{ color: 'var(--muted)', margin: '6px 0 0' }}>
            暂无——序列引擎（M2）上线后，AI 拟好的信会在这里等你审批。
          </p>
        </div>
        <div style={card}>
          <b>📊 开发任务动态</b>
          {campaigns.length === 0 ? (
            <p style={{ color: 'var(--muted)', margin: '6px 0 0' }}>
              还没有任务。<a href="/campaigns/" style={{ color: 'var(--accent)' }}>去创建第一个 →</a>
            </p>
          ) : (
            <ul style={{ margin: '6px 0 0' }}>
              {campaigns.map((c) => (
                <li key={c.id}>
                  {c.name} — {c.status === 'dry_run' ? '预跑中' : c.status}{' '}
                  <a href={`/leads/?campaign=${c.id}`} style={{ color: 'var(--accent)' }}>看线索</a>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </AppShell>
  );
}
