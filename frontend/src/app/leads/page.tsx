'use client';
import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import AppShell, { btn, card } from '@/components/AppShell';
import { api } from '@/lib/api';

interface Lead {
  id: string; company_name: string; domain: string; country: string;
  score: number; score_reason: string; status: string;
}
interface LeadDetail extends Lead {
  city: string; source: string;
  facts: { text: string; source_url: string }[];
  contacts: { full_name: string; role_title: string;
              emails: { email: string; confidence: string; verify_status: string }[] }[];
}

const STATUS: Record<string, { label: string; color: string }> = {
  discovered: { label: '已发现', color: 'var(--muted)' },
  scored: { label: '已评分', color: 'var(--accent)' },
  ready: { label: '就绪', color: 'var(--good)' },
  incomplete: { label: '待补全', color: 'var(--muted)' },
  excluded: { label: '已排除', color: 'var(--muted)' },
  in_sequence: { label: '触达中', color: 'var(--accent)' },
  hot: { label: '🔥 热线索', color: 'var(--hot)' },
};

function LeadsInner() {
  const campaignId = useSearchParams().get('campaign');
  const [leads, setLeads] = useState<Lead[]>([]);
  const [detail, setDetail] = useState<LeadDetail | null>(null);

  const load = () => {
    if (campaignId) {
      api<Lead[]>(`/api/campaigns/${campaignId}/leads`).then(setLeads).catch(() => {});
    }
  };
  useEffect(load, [campaignId]);

  async function exclude(id: string) {
    await api(`/api/leads/${id}/exclude`, { method: 'POST' });
    setDetail(null); load();
  }

  return (
    <AppShell active="/campaigns/">
      <h1 style={{ fontSize: 19 }}>线索池</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13 }}>
        每个评分都可点开查看 AI 研判依据（含出处）。夜间批处理后新线索会出现在这里。
      </p>
      {!campaignId && <div style={card}>请从「开发任务」页选择一个任务查看线索。</div>}
      {campaignId && leads.length === 0 && (
        <div style={{ ...card, color: 'var(--muted)' }}>
          暂无线索——预跑通常在数分钟到数小时内产出第一批（取决于数据源配额）。
        </div>
      )}
      <div style={{ ...card, padding: 0, overflowX: 'auto' }}>
        {leads.length > 0 && (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr style={{ color: 'var(--muted)', fontSize: 12, textAlign: 'left' }}>
                {['公司', '匹配度', '国家', '状态', '理由', ''].map((h) => (
                  <th key={h} style={{ padding: '10px 14px', borderBottom: '1px solid var(--line)' }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {leads.map((l) => (
                <tr key={l.id} style={{ borderBottom: '1px solid var(--line)' }}>
                  <td style={{ padding: '10px 14px' }}>
                    <b>{l.company_name || l.domain}</b>
                    <div style={{ color: 'var(--muted)', fontSize: 12 }}>{l.domain}</div>
                  </td>
                  <td style={{ padding: '10px 14px', fontWeight: 650 }}>{l.score}</td>
                  <td style={{ padding: '10px 14px' }}>{l.country}</td>
                  <td style={{ padding: '10px 14px', color: STATUS[l.status]?.color }}>
                    {STATUS[l.status]?.label ?? l.status}
                  </td>
                  <td style={{ padding: '10px 14px', color: 'var(--muted)', maxWidth: 280 }}>
                    {l.score_reason}
                  </td>
                  <td style={{ padding: '10px 14px' }}>
                    <button style={{ ...btn, padding: '3px 10px', fontSize: 12 }}
                            onClick={() => api<LeadDetail>(`/api/leads/${l.id}`).then(setDetail)}>
                      详情
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {detail && (
        <div style={{ ...card, marginTop: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <h2 style={{ fontSize: 15, margin: 0, flex: 1 }}>
              {detail.company_name || detail.domain} — 研判档案（{detail.score} 分）
            </h2>
            <button style={btn} onClick={() => exclude(detail.id)}>排除</button>{' '}
            <button style={btn} onClick={() => setDetail(null)}>收起</button>
          </div>
          <p style={{ color: 'var(--muted)' }}>{detail.score_reason}</p>
          <h3 style={{ fontSize: 13, color: 'var(--muted)' }}>✨ 事实清单（每条带出处）</h3>
          <ul>
            {detail.facts.map((f, i) => (
              <li key={i} style={{ marginBottom: 6 }}>
                {f.text}{' '}
                <a href={f.source_url} target="_blank" rel="noreferrer"
                   style={{ color: 'var(--accent)', fontSize: 12 }}>来源 ↗</a>
              </li>
            ))}
            {detail.facts.length === 0 && <li style={{ color: 'var(--muted)' }}>暂无</li>}
          </ul>
          <h3 style={{ fontSize: 13, color: 'var(--muted)' }}>联系人与邮箱（置信度不足不会进入发送队列）</h3>
          <ul>
            {detail.contacts.map((c, i) => (
              <li key={i} style={{ marginBottom: 6 }}>
                <b>{c.full_name || '（公共邮箱）'}</b>
                {c.role_title && <span style={{ color: 'var(--muted)' }}> · {c.role_title}</span>}
                {c.emails.map((e) => (
                  <div key={e.email} style={{ fontSize: 12, color: 'var(--muted)' }}>
                    {e.email} — 置信度 {e.confidence}（{e.verify_status}）
                  </div>
                ))}
              </li>
            ))}
            {detail.contacts.length === 0 && <li style={{ color: 'var(--muted)' }}>暂无</li>}
          </ul>
        </div>
      )}
    </AppShell>
  );
}

export default function LeadsPage() {
  return <Suspense><LeadsInner /></Suspense>;
}
