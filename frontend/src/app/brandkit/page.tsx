'use client';
import { useEffect, useState } from 'react';
import AppShell, { btn, btnPri, card, input } from '@/components/AppShell';
import { api } from '@/lib/api';

interface Asset { id: string; kind: string; title: string; content: Record<string, string>; ai_quotable: boolean }

const KINDS: Record<string, string> = {
  company_intro: '公司简介', product: '产品', certification: '认证证书',
  case: '客户案例', faq: 'FAQ',
};

export default function BrandkitPage() {
  const [assets, setAssets] = useState<Asset[]>([]);
  const [kind, setKind] = useState('product');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [error, setError] = useState('');

  const load = () => api<Asset[]>('/api/brandkit').then(setAssets).catch(() => {});
  useEffect(() => { load(); }, []);

  async function add() {
    setError('');
    try {
      // 简易录入：每行一条 key: value
      const obj: Record<string, string> = {};
      content.split('\n').forEach((line) => {
        const idx = line.indexOf(':');
        if (idx > 0) obj[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
      });
      await api('/api/brandkit', {
        method: 'POST',
        body: JSON.stringify({ kind, title, content: obj, ai_quotable: true }),
      });
      setTitle(''); setContent(''); load();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <AppShell active="/brandkit/">
      <h1 style={{ fontSize: 19 }}>品牌资产库</h1>
      <p style={{ color: 'var(--muted)', fontSize: 13 }}>
        AI 写开发信<b>只会引用这里的事实</b>（MOQ、认证、交期…）——绝不编造。填得越实，信越可信。
      </p>
      <div style={{ ...card, marginBottom: 16 }}>
        <select value={kind} onChange={(e) => setKind(e.target.value)}
                style={{ ...input, width: 200 }}>
          {Object.entries(KINDS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <input style={input} placeholder="标题（如：LED Track Light 20W）"
               value={title} onChange={(e) => setTitle(e.target.value)} />
        <textarea style={{ ...input, minHeight: 80, fontFamily: 'inherit' }}
                  placeholder={'结构化内容，每行一条 key: value，例如\nmoq: 200 units\ncert: ETL\nlead_time: 25 days'}
                  value={content} onChange={(e) => setContent(e.target.value)} />
        {error && <p style={{ color: 'var(--hot)' }}>{error}</p>}
        <button style={btnPri} disabled={!title} onClick={add}>添加资产</button>
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
        {assets.map((a) => (
          <div key={a.id} style={card}>
            <div style={{ fontSize: 12, color: 'var(--accent)' }}>{KINDS[a.kind] ?? a.kind}</div>
            <b>{a.title}</b>
            <div style={{ color: 'var(--muted)', fontSize: 12, marginTop: 6 }}>
              {Object.entries(a.content).map(([k, v]) => <div key={k}>{k}: {String(v)}</div>)}
            </div>
            <button style={{ ...btn, marginTop: 10, padding: '3px 10px', fontSize: 12 }}
                    onClick={() => api(`/api/brandkit/${a.id}`, { method: 'DELETE' }).then(load)}>
              删除
            </button>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
