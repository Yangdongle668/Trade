'use client';
import { useEffect, useState } from 'react';
import AppShell, { btn, btnPri, card, input } from '@/components/AppShell';
import { api } from '@/lib/api';

interface Campaign {
  id: string; name: string; status: string; automation_level: string; icp: {
    countries?: string[]; industry_keywords?: string[]; company_types?: string[]; freeform?: string;
  };
}

const COUNTRIES = ['US', 'GB', 'CA', 'AU', 'NZ'];
const STATUS_LABEL: Record<string, string> = {
  draft: '草稿', dry_run: '预跑中', active: '运行中', paused: '已暂停', archived: '已归档',
};
const AUTO_LABEL: Record<string, string> = {
  per_email: '逐封审批', sampling: '抽检模式', full_auto: '全自动',
};

export default function CampaignsPage() {
  const [list, setList] = useState<Campaign[]>([]);
  const [showWizard, setShowWizard] = useState(false);
  const [step, setStep] = useState(1);
  const [error, setError] = useState('');
  // 向导表单
  const [name, setName] = useState('');
  const [countries, setCountries] = useState<string[]>(['US']);
  const [keywords, setKeywords] = useState('');
  const [types, setTypes] = useState('distributor, wholesaler');
  const [freeform, setFreeform] = useState('');
  const [auto, setAuto] = useState('per_email');

  const load = () => api<Campaign[]>('/api/campaigns').then(setList).catch(() => {});
  useEffect(() => { load(); }, []);

  async function submit() {
    setError('');
    try {
      const c = await api<Campaign>('/api/campaigns', {
        method: 'POST',
        body: JSON.stringify({
          name,
          icp: {
            countries,
            industry_keywords: keywords.split(/[,，]/).map(s => s.trim()).filter(Boolean),
            company_types: types.split(/[,，]/).map(s => s.trim()).filter(Boolean),
            freeform,
          },
          automation_level: auto,
        }),
      });
      await api(`/api/campaigns/${c.id}/start-dry-run`, { method: 'POST' });
      setShowWizard(false); setStep(1); setName(''); setKeywords(''); setFreeform('');
      load();
    } catch (e) { setError((e as Error).message); }
  }

  return (
    <AppShell active="/campaigns/">
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
        <h1 style={{ fontSize: 19, margin: 0, flex: 1 }}>开发任务</h1>
        <button style={btnPri} onClick={() => setShowWizard(true)}>＋ 新建任务</button>
      </div>

      {showWizard && (
        <div style={{ ...card, marginBottom: 20 }}>
          <div style={{ color: 'var(--muted)', fontSize: 13, marginBottom: 12 }}>
            {['① 定目标', '② 定策略', '③ 确认并预跑'].map((s, i) => (
              <span key={s} style={{
                marginRight: 16,
                color: step === i + 1 ? 'var(--accent)' : 'var(--muted)',
                fontWeight: step === i + 1 ? 650 : 400,
              }}>{s}</span>
            ))}
          </div>

          {step === 1 && (<>
            <input style={input} placeholder="任务名称（如：北美 LED 轨道灯分销商）"
                   value={name} onChange={(e) => setName(e.target.value)} />
            <div style={{ marginBottom: 10 }}>
              {COUNTRIES.map((c) => (
                <label key={c} style={{ marginRight: 14 }}>
                  <input type="checkbox" checked={countries.includes(c)}
                         onChange={(e) => setCountries(e.target.checked
                           ? [...countries, c] : countries.filter((x) => x !== c))} /> {c}
                </label>
              ))}
            </div>
            <input style={input} placeholder="行业关键词（逗号分隔，如：led track lighting, commercial lighting）"
                   value={keywords} onChange={(e) => setKeywords(e.target.value)} />
            <input style={input} placeholder="公司类型（如：distributor, wholesaler, importer）"
                   value={types} onChange={(e) => setTypes(e.target.value)} />
            <textarea style={{ ...input, minHeight: 60 }}
                      placeholder="补充要求（自然语言，如：要有实体门店，不要纯电商）"
                      value={freeform} onChange={(e) => setFreeform(e.target.value)} />
            <button style={btnPri} disabled={!name || !keywords}
                    onClick={() => setStep(2)}>下一步 →</button>
          </>)}

          {step === 2 && (<>
            {Object.entries(AUTO_LABEL).map(([k, label]) => (
              <label key={k} style={{ display: 'block', marginBottom: 8 }}>
                <input type="radio" checked={auto === k} onChange={() => setAuto(k)} />{' '}
                <b>{label}</b>
                <span style={{ color: 'var(--muted)', fontSize: 12 }}>
                  {k === 'per_email' && ' — 每封信发送前需我确认（建议新任务前 2 周）'}
                  {k === 'sampling' && ' — AI 自主发送，随机 20% 进入审批流'}
                  {k === 'full_auto' && ' — 仅热线索与异常需要我处理'}
                </span>
              </label>
            ))}
            <p style={{ color: 'var(--muted)', fontSize: 12 }}>
              发送护栏（系统托管）：收件人时区工作日上午投递 · 单邮箱日限 20 封 · 回复即停
            </p>
            <button style={btn} onClick={() => setStep(1)}>← 上一步</button>{' '}
            <button style={btnPri} onClick={() => setStep(3)}>下一步 →</button>
          </>)}

          {step === 3 && (<>
            <p>任务「<b>{name}</b>」将开始<b>预跑</b>：AI 先挖掘一批样本线索供你校准，
              校准确认后才会开始真实触达。</p>
            <p style={{ color: 'var(--muted)', fontSize: 13 }}>
              目标市场 {countries.join(' / ')} · 关键词 {keywords} · {AUTO_LABEL[auto]}
            </p>
            {error && <p style={{ color: 'var(--hot)' }}>{error}</p>}
            <button style={btn} onClick={() => setStep(2)}>← 上一步</button>{' '}
            <button style={btnPri} onClick={submit}>启动预跑 🚀</button>{' '}
            <button style={btn} onClick={() => setShowWizard(false)}>取消</button>
          </>)}
        </div>
      )}

      {list.length === 0 && !showWizard && (
        <div style={{ ...card, color: 'var(--muted)' }}>
          还没有开发任务。点右上角「新建任务」，10 分钟后 AI 就开始为你找客户。
        </div>
      )}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
        {list.map((c) => (
          <div key={c.id} style={card}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
              <b style={{ flex: 1 }}>{c.name}</b>
              <span style={{ fontSize: 12, color: 'var(--good)' }}>{STATUS_LABEL[c.status] ?? c.status}</span>
            </div>
            <div style={{ color: 'var(--muted)', fontSize: 12, margin: '6px 0 10px' }}>
              {(c.icp.countries ?? []).join(' / ')} · {(c.icp.industry_keywords ?? []).join(', ')}
              {' · '}{AUTO_LABEL[c.automation_level]}
            </div>
            <a href={`/leads/?campaign=${c.id}`} style={{ color: 'var(--accent)' }}>查看线索 →</a>
          </div>
        ))}
      </div>
    </AppShell>
  );
}
