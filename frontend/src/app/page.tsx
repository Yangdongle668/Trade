'use client';
import { useCallback, useEffect, useState } from 'react';
import AppShell, { btn, btnPri, card, input } from '@/components/AppShell';
import { api, getToken } from '@/lib/api';

interface Me { display_name: string }
interface Campaign { id: string; name: string; status: string }
interface SendJob {
  id: string; step_no: number; scheduled_at: string; subject: string; body_text: string;
  company_name: string; domain: string; contact_name: string; fact_urls: string[];
}
interface HotThread {
  id: string; company_name: string; contact_name: string; last_snippet: string;
  classification: string; lead_status: string;
}

export default function TodayPage() {
  const [me, setMe] = useState<Me | null>(null);
  const [campaigns, setCampaigns] = useState<Campaign[]>([]);
  const [pending, setPending] = useState<SendJob[]>([]);
  const [hot, setHot] = useState<HotThread[]>([]);
  const [editing, setEditing] = useState<{ subject: string; body: string } | null>(null);

  const load = useCallback(() => {
    api<Campaign[]>('/api/campaigns').then(setCampaigns).catch(() => {});
    api<SendJob[]>('/api/sendjobs/pending').then(setPending).catch(() => {});
    api<HotThread[]>('/api/inbox')
      .then((ts) => setHot(ts.filter((t) => t.lead_status === 'hot')))
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (!getToken()) return;
    api<Me>('/api/auth/me').then(setMe).catch(() => {});
    load();
  }, [load]);

  const job = pending[0];

  async function approve() {
    if (!job) return;
    await api(`/api/sendjobs/${job.id}/approve`, {
      method: 'POST',
      body: JSON.stringify(editing
        ? { subject: editing.subject, body_text: editing.body }
        : { subject: job.subject, body_text: job.body_text }),
    });
    setEditing(null); load();
  }

  async function reject() {
    if (!job) return;
    const reason = window.prompt('拒绝原因（可选，会用于改进 AI 写作）') ?? '';
    await api(`/api/sendjobs/${job.id}/reject`, {
      method: 'POST', body: JSON.stringify({ reason }),
    });
    setEditing(null); load();
  }

  return (
    <AppShell active="/">
      <h1 style={{ fontSize: 20 }}>{me ? `早上好，${me.display_name} ☀️` : '今日待办'}</h1>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div style={{ ...card, borderLeft: '3px solid var(--hot)' }}>
          <b>🔥 热线索</b>
          <span style={{ color: 'var(--muted)', fontSize: 12 }}>（{hot.length} 条待处理）</span>
          {hot.length === 0 && (
            <p style={{ color: 'var(--muted)', margin: '6px 0 0' }}>
              暂无——客户回复后会第一时间出现在这里。
            </p>
          )}
          {hot.map((t) => (
            <div key={t.id} style={{ margin: '10px 0 0', padding: '10px 14px',
                                     background: 'var(--ground)', borderRadius: 8 }}>
              <b>{t.company_name}</b>
              <span style={{ color: 'var(--muted)', fontSize: 12 }}> · {t.contact_name}</span>
              <div style={{ color: 'var(--muted)', fontSize: 13, margin: '4px 0 8px' }}>
                “{t.last_snippet}”
              </div>
              <a href="/inbox/" style={{ color: 'var(--accent)', fontSize: 13 }}>
                去处理（AI 已可草拟回复）→
              </a>
            </div>
          ))}
        </div>

        <div style={card}>
          <b>✍️ 待审批开发信</b>
          <span style={{ color: 'var(--muted)', fontSize: 12 }}>（{pending.length} 封）</span>
          {!job && (
            <p style={{ color: 'var(--muted)', margin: '6px 0 0' }}>
              暂无待审批。序列 tick 每 5 分钟生成一批（逐封审批/抽检模式的任务）。
            </p>
          )}
          {job && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 12, color: 'var(--accent)', marginBottom: 6 }}>
                ✨ AI 草稿 · 第 {job.step_no + 1} 步 · 收件人 {job.contact_name} @ {job.company_name}
                （{job.domain}）· 计划 {new Date(job.scheduled_at).toLocaleString()}
              </div>
              {editing ? (<>
                <input style={input} value={editing.subject}
                       onChange={(e) => setEditing({ ...editing, subject: e.target.value })} />
                <textarea style={{ ...input, minHeight: 140 }}
                          value={editing.body}
                          onChange={(e) => setEditing({ ...editing, body: e.target.value })} />
              </>) : (<>
                <div style={{ fontWeight: 650 }}>{job.subject}</div>
                <pre style={{
                  whiteSpace: 'pre-wrap', font: 'inherit', background: 'var(--ground)',
                  borderRadius: 8, padding: '10px 14px', margin: '8px 0',
                }}>{job.body_text}</pre>
              </>)}
              {job.fact_urls.length > 0 && (
                <div style={{ fontSize: 12, color: 'var(--muted)', marginBottom: 10 }}>
                  依据事实：{job.fact_urls.map((u, i) => (
                    <a key={u} href={u} target="_blank" rel="noreferrer"
                       style={{ color: 'var(--accent)', marginRight: 8 }}>来源{i + 1} ↗</a>
                  ))}
                </div>
              )}
              <button style={btnPri} onClick={approve}>✓ 通过并排入发送</button>{' '}
              {editing
                ? <button style={btn} onClick={() => setEditing(null)}>放弃编辑</button>
                : <button style={btn}
                          onClick={() => setEditing({ subject: job.subject, body: job.body_text })}>
                    编辑</button>}{' '}
              <button style={{ ...btn, color: 'var(--hot)', borderColor: 'var(--hot)' }}
                      onClick={reject}>✕ 拒绝</button>
            </div>
          )}
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
                  {c.name} — {c.status === 'dry_run' ? '预跑中' : c.status === 'active' ? '运行中' : c.status}{' '}
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
