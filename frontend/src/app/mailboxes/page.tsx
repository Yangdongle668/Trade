'use client';
import { useEffect, useState } from 'react';
import AppShell, { btnPri, card, input } from '@/components/AppShell';
import { api } from '@/lib/api';

interface Mailbox {
  id: string; email: string; channel: string; health: string;
  warmup_day: number; daily_limit: number; sent_today: number;
}

const HEALTH: Record<string, { label: string; color: string }> = {
  warming: { label: '预热中', color: 'var(--muted)' },
  healthy: { label: '健康', color: 'var(--good)' },
  throttled: { label: '已降速', color: 'var(--hot)' },
  paused: { label: '已熔断', color: 'var(--hot)' },
};
const PRESET_LABEL: Record<string, string> = {
  aliyun: '阿里企业邮箱', tencent: '腾讯企业邮箱', zoho: 'Zoho Mail',
  netease: '网易企业邮箱', gmail_app_password: 'Gmail（应用专用密码）',
  outlook_app_password: 'Outlook（应用密码）',
};

export default function MailboxesPage() {
  const [list, setList] = useState<Mailbox[]>([]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [preset, setPreset] = useState('aliyun');
  const [error, setError] = useState('');

  const load = () => api<Mailbox[]>('/api/mailboxes').then(setList).catch(() => {});
  useEffect(() => { load(); }, []);

  async function add() {
    setError('');
    try {
      await api('/api/mailboxes/smtp', {
        method: 'POST',
        body: JSON.stringify({ email, password, preset }),
      });
      setEmail(''); setPassword(''); load();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <AppShell active="/mailboxes/">
      <h1 style={{ fontSize: 19 }}>发信邮箱</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13 }}>
        <b>强烈建议使用独立发信域名的邮箱</b>（不要用公司主域名群发）。
        新邮箱自动进入 21 天预热（日发 5→20 封渐进），这是对你发信信誉的保护。
      </p>

      {list.map((m) => (
        <div key={m.id} style={{ ...card, marginBottom: 12, display: 'flex',
                                  alignItems: 'center', gap: 14 }}>
          <span style={{ width: 9, height: 9, borderRadius: '50%', flexShrink: 0,
                         background: HEALTH[m.health]?.color }} />
          <div style={{ flex: 1 }}>
            <b>{m.email}</b>
            <div style={{ fontSize: 12, color: 'var(--muted)' }}>
              {m.channel === 'smtp_imap' ? 'SMTP/IMAP' : m.channel}
              {m.health === 'warming' && ` · 预热第 ${m.warmup_day}/21 天`}
              {` · 今日 ${m.sent_today}/${m.daily_limit} 封`}
            </div>
          </div>
          <span style={{ color: HEALTH[m.health]?.color, fontSize: 13, fontWeight: 600 }}>
            {HEALTH[m.health]?.label ?? m.health}
          </span>
        </div>
      ))}

      {list.length === 0 && (
        <div style={{ ...card, marginBottom: 12 }}>
          <b>接入你的发信邮箱</b>
          <div style={{ marginTop: 10 }}>
            <select value={preset} onChange={(e) => setPreset(e.target.value)}
                    style={{ ...input, width: 260 }}>
              {Object.entries(PRESET_LABEL).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
            <input style={input} type="email" placeholder="邮箱地址"
                   value={email} onChange={(e) => setEmail(e.target.value)} />
            <input style={input} type="password" placeholder="授权码 / 应用专用密码（不是登录密码）"
                   value={password} onChange={(e) => setPassword(e.target.value)} />
            <p style={{ color: 'var(--muted)', fontSize: 12 }}>
              授权码在邮箱服务商后台生成（如阿里企业邮箱：设置 → 安全 → 客户端授权码）。
              凭据加密存储，仅用于代你发送已审批的开发信。
            </p>
            {error && <p style={{ color: 'var(--hot)' }}>{error}</p>}
            <button style={btnPri} disabled={!email || !password} onClick={add}>
              接入并开始预热
            </button>
          </div>
        </div>
      )}
    </AppShell>
  );
}
