import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';

const API_BASE = 'http://localhost:8000/api/v1';
const styles = { app: { fontFamily: 'Georgia, Times New Roman, serif', minHeight: '100vh', background: 'linear-gradient(180deg, #f9f7f1 0%, #efe8d8 100%)', color: '#1f2937' }, wrap: { maxWidth: 1100, margin: '0 auto', padding: 24 }, title: { fontSize: 36, marginBottom: 8 }, tabs: { display: 'flex', gap: 8, marginBottom: 20 }, tab: { padding: '10px 14px', borderRadius: 10, border: '1px solid #c7bda8', background: '#fff8e8', cursor: 'pointer' }, tabActive: { background: '#1f2937', color: '#fff' }, card: { background: 'rgba(255,255,255,0.85)', border: '1px solid #ddd3c0', borderRadius: 14, padding: 16, boxShadow: '0 6px 24px rgba(0,0,0,0.05)', marginBottom: 14 }, row: { display: 'flex', gap: 12, flexWrap: 'wrap' }, input: { width: '100%', padding: 12, borderRadius: 10, border: '1px solid #c8bca3', fontSize: 16 }, select: { padding: 10, borderRadius: 10, border: '1px solid #c8bca3', background: '#fff' }, btn: { padding: '10px 16px', border: 0, borderRadius: 10, background: '#0f766e', color: '#fff', cursor: 'pointer', fontWeight: 700 }, metric: { flex: 1, minWidth: 180, background: '#fff', border: '1px solid #e1d8c7', borderRadius: 12, padding: 12 }, code: { background: '#111827', color: '#e5e7eb', borderRadius: 10, padding: 12, maxHeight: 220, overflow: 'auto', fontSize: 13 } };

function App() {
  const [tab, setTab] = useState('Ask');
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState('manual');
  const [provider, setProvider] = useState('groq');
  const [model, setModel] = useState('llama-3.1-8b-instant');
  const [models, setModels] = useState({ providers: [] });
  const [loading, setLoading] = useState(false);
  const [runId, setRunId] = useState('');
  const [events, setEvents] = useState([]);
  const [answer, setAnswer] = useState('');
  const [runs, setRuns] = useState([]);
  const [metrics, setMetrics] = useState(null);
  const [lsMetrics, setLsMetrics] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [sessionId, setSessionId] = useState('');

  useEffect(() => { init(); }, []);

  async function init() {
    const m = await fetch(`${API_BASE}/models`).then(r => r.json()); setModels(m);
    await refreshSessions(); await refreshRuns(); await refreshMetrics(); await refreshLangSmith();
  }

  const modelOptions = useMemo(() => (models.providers[0]?.models || ['llama-3.1-8b-instant','llama-3.3-70b-versatile']), [models]);
  useEffect(() => { if (modelOptions.length && !modelOptions.includes(model)) setModel(modelOptions[0]); }, [modelOptions, model]);

  async function refreshSessions() {
    const s = await fetch(`${API_BASE}/sessions`).then(r => r.json());
    setSessions(s);
    if (!sessionId && s.length) setSessionId(s[0].id);
  }

  async function createSession() {
    const title = `Chat ${sessions.length + 1}`;
    const s = await fetch(`${API_BASE}/sessions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ title }) }).then(r => r.json());
    await refreshSessions();
    setSessionId(s.id);
    setRuns([]); setEvents([]); setAnswer(''); setRunId('');
  }

  async function refreshRuns() {
    const url = sessionId ? `${API_BASE}/runs?session_id=${sessionId}` : `${API_BASE}/runs`;
    const r = await fetch(url); setRuns(await r.json());
  }

  async function refreshMetrics() { const r = await fetch(`${API_BASE}/metrics/summary`); setMetrics(await r.json()); }
  async function refreshLangSmith() { const r = await fetch(`${API_BASE}/metrics/langsmith`); setLsMetrics(await r.json()); }

  useEffect(() => { refreshRuns(); }, [sessionId]);

  async function onSubmit() {
    setLoading(true); setEvents([]); setAnswer('');
    try {
      const payload = { query, mode, provider: mode === 'manual' ? provider : null, model: mode === 'manual' ? model : null, session_id: sessionId || null };
      const data = await fetch(`${API_BASE}/query`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': `web-${Date.now()}` }, body: JSON.stringify(payload) }).then(r => r.json());
      if (!data.run_id) return;
      setRunId(data.run_id);
      await pollRun(data.run_id);
      await refreshRuns(); await refreshMetrics(); await refreshLangSmith();
    } finally { setLoading(false); }
  }

  async function pollRun(id) {
    if (!id) return;
    for (let i = 0; i < 15; i += 1) {
      const ev = await fetch(`${API_BASE}/runs/${id}/events`).then(r => r.text()); setEvents(ev.split('\n').filter(Boolean));
      const run = await fetch(`${API_BASE}/runs/${id}`).then(r => r.json());
      if (run.answer) { setAnswer(run.answer); return; }
      await new Promise(res => setTimeout(res, 800));
    }
  }

  return <div style={styles.app}><div style={styles.wrap}><h1 style={styles.title}>Research Browser</h1><p>Grounded answers with citations from live web evidence.</p>
    <div style={styles.card}><div style={{...styles.row, alignItems:'center'}}><b>Chat Session</b><select value={sessionId} onChange={e=>setSessionId(e.target.value)} style={styles.select}>{sessions.map(s=><option key={s.id} value={s.id}>{s.title}</option>)}</select><button style={styles.btn} onClick={createSession}>New Chat</button></div></div>
    <div style={styles.tabs}>{['Ask','Runs','Observability'].map(t=><button key={t} style={{...styles.tab,...(tab===t?styles.tabActive:{})}} onClick={()=>setTab(t)}>{t}</button>)}</div>
    {tab==='Ask' && <><div style={styles.card}><div style={{marginBottom:8,fontWeight:700}}>Ask a question</div><textarea rows={4} value={query} onChange={e=>setQuery(e.target.value)} placeholder="Ask anything you want researched..." style={styles.input} /><div style={{...styles.row,marginTop:12,alignItems:'center'}}><label>Mode</label><select value={mode} onChange={e=>setMode(e.target.value)} style={styles.select}><option value="manual">Manual</option><option value="auto">Auto-route</option></select><label>Provider</label><select disabled value={provider} style={styles.select}><option value='groq'>groq</option></select><label>Model</label><select disabled={mode!=='manual'} value={model} onChange={e=>setModel(e.target.value)} style={styles.select}>{modelOptions.map(m=><option key={m} value={m}>{m}</option>)}</select><button style={styles.btn} disabled={loading||!query.trim()} onClick={onSubmit}>{loading?'Running...':'Run Research'}</button></div></div><div style={styles.card}><b>Run ID:</b> {runId||'—'}</div><div style={styles.card}><b>Live Events</b><pre style={styles.code}>{events.join('\n')||'No events yet'}</pre></div><div style={styles.card}><b>Final Answer</b><pre style={styles.code}>{answer||'No answer yet'}</pre></div></>}
    {tab==='Runs' && <div style={styles.card}><div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><b>Run History</b><button style={styles.btn} onClick={refreshRuns}>Refresh</button></div><table style={{width:'100%',marginTop:12,borderCollapse:'collapse'}}><thead><tr><th align="left">Run ID</th><th align="left">Status</th><th align="left">Query</th><th align="left">Created</th></tr></thead><tbody>{runs.map(r=><tr key={r.run_id}><td>{r.run_id.slice(0,8)}...</td><td>{r.status}</td><td>{r.query}</td><td>{r.created_at}</td></tr>)}</tbody></table></div>}
    {tab==='Observability' && <><div style={styles.card}><b>Local Observability (DB)</b></div><div style={styles.row}><div style={styles.metric}><div>Total Runs</div><h3>{metrics?.total_runs??'—'}</h3></div><div style={styles.metric}><div>P50 Latency</div><h3>{metrics?.p50_latency_ms??'—'} ms</h3></div><div style={styles.metric}><div>P95 Latency</div><h3>{metrics?.p95_latency_ms??'—'} ms</h3></div><div style={styles.metric}><div>Avg Cost</div><h3>${metrics?.avg_cost_usd?.toFixed?.(6)??'—'}</h3></div></div><div style={{...styles.row,marginTop:12}}><div style={styles.metric}><div>Fallback Count</div><h3>{metrics?.fallback_count??'—'}</h3></div><div style={styles.metric}><div>Retry Count</div><h3>{metrics?.retry_count??'—'}</h3></div><div style={styles.metric}><div>Error Count</div><h3>{metrics?.error_count??'—'}</h3></div><div style={styles.metric}><div>Cache Hit Rate</div><h3>{metrics?.cache_hit_rate??'—'}</h3></div></div><div style={{...styles.card,marginTop:12}}><b>Model Usage Distribution</b><pre style={styles.code}>{JSON.stringify(metrics?.model_usage??[], null, 2)}</pre></div><div style={{...styles.card,marginTop:12}}><div style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}><b>LangSmith Tracing</b><button style={styles.btn} onClick={refreshLangSmith}>Refresh</button></div><div style={{marginTop:8}}>Enabled: <b>{String(lsMetrics?.enabled ?? false)}</b></div><div>Project: <b>{lsMetrics?.project ?? '—'}</b></div><div>Total Recent Runs: <b>{lsMetrics?.run_count ?? 0}</b></div>{lsMetrics?.error ? <div style={{color:'#b91c1c',marginTop:8}}>Error: {lsMetrics.error}</div> : null}<pre style={{...styles.code, marginTop:10}}>{JSON.stringify(lsMetrics?.recent_runs ?? [], null, 2)}</pre></div></>}
  </div></div>;
}

createRoot(document.getElementById('root')).render(<App />);
