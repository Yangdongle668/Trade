'use client';
import { useCallback, useEffect, useState } from 'react';
import AppShell, { btn, btnPri, card, input } from '@/components/AppShell';
import { api } from '@/lib/api';

interface ThreadItem {
  id: string; company_name: string; domain: string; contact_name: string;
  subject: string; last_snippet: string; last_at: string;
  classification: string; lead_status: string; lead_id: string;
}
interface ThreadDetail {
  id: string; company_name: string; contact_name: string; lead_status: string;
  messages: { direction: string; subject: string; body_text: string; at: string;
              classification: string }[];
}

const CLS: Record<string, string> = {
  interested: '🔥 感兴趣', question: '❓ 有疑问', later: '⏰ 以后再说',
  rejected: '✋ 拒绝', unsubscribe: '🚫 退订', auto_reply: '🤖 自动回复',
  referral: '↪️ 转介绍', unclassified: '❔ 待分拣',
};
const FILTERS = ['', 'interested', 'question', 'later', 'rejected', 'auto_reply', 'unclassified'];

export default function InboxPage() {
  const [threads, setThreads] = useState<ThreadItem[]>([]);
  const [filter, setFilter] = useState('');
  const [detail, setDetail] = useState<ThreadDetail | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api<ThreadItem[]>(`/api/inbox${filter ? `?classification=${filter}` : ''}`)
      .then(setThreads).catch(() => {});
  }, [filter]);
  useEffect(load, [load]);

  async function open(id: string) {
    setDraft('');
    setDetail(await api<ThreadDetail>(`/api/inbox/${id}`));
  }

  async function genDraft() {
    if (!detail) return;
    setBusy(true);
    try {
      const r = await api<{ body: string }>(`/api/inbox/${detail.id}/draft-reply`,
                                            { method: 'POST' });
      setDraft(r.body);
    } catch (e) { alert((e as Error).message); }
    setBusy(false);
  }

  async function send() {
    if (!detail || !draft) return;
    setBusy(true);
    try {
      await api(`/api/inbox/${detail.id}/send-reply`, {
        method: 'POST', body: JSON.stringify({ body: draft }),
      });
      setDraft(''); setDetail(null); load();
    } catch (e) { alert((e as Error).message); }
    setBusy(false);
  }

  return (
    <AppShell active="/inbox/">
      <h1 style={{ fontSize: 19 }}>收件箱</h1>
      <div style={{ marginBottom: 12 }}>
        {FILTERS.map((f) => (
          <button key={f} onClick={() => setFilter(f)} style={{
            ...btn, marginRight: 8, padding: '3px 12px', fontSize: 12,
            ...(filter === f ? { background: 'var(--accent)', color: 'var(--accent-ink)',
                                 borderColor: 'var(--accent)' } : {}),
          }}>{f === '' ? '全部' : CLS[f]}</button>
        ))}
      </div>

      {threads.length === 0 && (
        <div style={{ ...card, color: 'var(--muted)' }}>
          暂无回复。收件轮询每 3 分钟一次，客户回信会自动分类出现在这里，热线索置顶。
        </div>
      )}
      {threads.map((t) => (
        <div key={t.id} onClick={() => open(t.id)} style={{
          ...card, marginBottom: 10, cursor: 'pointer',
          borderLeft: t.lead_status === 'hot' ? '3px solid var(--hot)' : undefined,
        }}>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <b style={{ flex: 1 }}>{t.company_name}</b>
            <span style={{ fontSize: 12 }}>{CLS[t.classification] ?? t.classification}</span>
            <span style={{ fontSize: 12, color: 'var(--muted)' }}>
              {new Date(t.last_at).toLocaleString()}
            </span>
          </div>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginTop: 4 }}>
            {t.contact_name} · {t.last_snippet}
          </div>
        </div>
      ))}

      {detail && (
        <div style={{ ...card, marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <h2 style={{ fontSize: 15, margin: 0, flex: 1 }}>
              {detail.company_name} · {detail.contact_name}
            </h2>
            <button style={btn} onClick={() => setDetail(null)}>收起</button>
          </div>
          {detail.messages.map((m, i) => (
            <div key={i} style={{
              margin: '10px 0', padding: '10px 14px', borderRadius: 8,
              background: m.direction === 'in'
                ? 'color-mix(in srgb, var(--accent) 10%, transparent)' : 'var(--ground)',
            }}>
              <div style={{ fontSize: 11, color: 'var(--muted)', marginBottom: 4 }}>
                {m.direction === 'in' ? '客户' : '我'} · {new Date(m.at).toLocaleString()}
                {m.direction === 'in' && m.classification &&
                  ` · ${CLS[m.classification] ?? m.classification}`}
              </div>
              <pre style={{ whiteSpace: 'pre-wrap', font: 'inherit', margin: 0 }}>
                {m.body_text}
              </pre>
            </div>
          ))}
          <div style={{ borderTop: '1px dashed var(--accent)', paddingTop: 12, marginTop: 12 }}>
            <textarea style={{ ...input, minHeight: 100 }} value={draft}
                      placeholder="回信内容——点「AI 草拟」基于品牌资产库生成，或自己写"
                      onChange={(e) => setDraft(e.target.value)} />
            <button style={btn} disabled={busy} onClick={genDraft}>✨ AI 草拟</button>{' '}
            <button style={btnPri} disabled={busy || !draft} onClick={send}>
              确认发送（发出后热线索转为已交接）
            </button>
          </div>
        </div>
      )}
    </AppShell>
  );
}
