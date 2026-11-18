import React, { useState } from 'react'
import { createRoot } from 'react-dom/client'
import contract from './contract.json'

type InventoryOperation = { id: string; action: string; path: string; method: string; request_fields: { name: string; data_type: string }[] }
const stock = (contract as unknown as { inventory: { operations: InventoryOperation[] } | null }).inventory
const actionNames: Record<string, string> = { insert: '등록', get: '단건 조회', list: '목록 조회', update: '수정', draft: '입출고 초안 작성', edit: '초안 수량 수정', confirm: '확정', cancel: '확정 취소', movement: '입출고 조회', balance: '재고 조회' }

function App() {
  const [token, setToken] = useState((window as unknown as { spectonPreview?: boolean }).spectonPreview ? 'preview' : '')
  const [screen, setScreen] = useState(contract.screens.find(s => s.route === window.location.pathname)?.id ?? contract.screens[0]?.id ?? '')
  const [values, setValues] = useState<Record<string, string>>({})
  const [result, setResult] = useState<unknown>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const selected = contract.screens.find(s => s.id === screen)
  const operations = contract.operations.filter(o => selected?.api_ids.includes(o.api_id))
  async function invoke(op: typeof contract.operations[number]) {
    setBusy(true); setError(''); setResult(null)
    try {
      let path = op.path
      const headers: Record<string, string> = { Authorization: `Bearer ${token}` }
      let body: string | undefined
      if (op.action === 'get') path = path.replace('{key}', encodeURIComponent(values[op.api_id + ':key'] ?? ''))
      else if (op.action !== 'list') {
        const data: Record<string, unknown> = {}
        for (const f of op.fields) {
          const value = values[op.api_id + ':' + f.name] ?? ''
          data[f.name] = !value && !f.required ? null : f.data_type === 'integer' ? Number(value) : f.data_type === 'boolean' ? value === 'true' : value
        }
        headers['Content-Type'] = 'application/json'
        headers['Idempotency-Key'] = crypto.randomUUID()
        if (op.action === 'update') path = path.replace('{key}', encodeURIComponent(String(data[op.key.name])))
        body = JSON.stringify(data)
      }
      const response = await fetch('/api' + path, { method: op.method, headers, body })
      const data: unknown = await response.json()
      if (!response.ok) throw new Error(JSON.stringify(data))
      setResult(data)
    } catch (e) { setError(e instanceof Error ? e.message : '요청 실패') }
    finally { setBusy(false) }
  }
  async function invokeStock(op: InventoryOperation) {
    setBusy(true); setError(''); setResult(null)
    try {
      let path = op.path.replace('{key}', encodeURIComponent(values[op.id + ':key'] ?? ''))
      const input: Record<string, string> = {}
      for (const f of op.request_fields) if (f.name !== 'key') input[f.name] = values[op.id + ':' + f.name] ?? ''
      if (op.method === 'GET' && Object.keys(input).length) path += '?' + new URLSearchParams(input)
      const headers: Record<string,string> = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }
      if (op.method !== 'GET') headers['Idempotency-Key'] = crypto.randomUUID()
      const response = await fetch('/api' + path, { method: op.method, headers, body: op.method === 'GET' ? undefined : JSON.stringify(input) })
      const data: unknown = await response.json()
      if (!response.ok) throw new Error(JSON.stringify(data))
      setResult(data)
    } catch (e) { setError(e instanceof Error ? e.message : '요청 실패') }
    finally { setBusy(false) }
  }
  return <main style={{ maxWidth: 900, margin: '2rem auto', fontFamily: 'sans-serif' }}>
    <h1>{stock ? '재고 업무 시스템' : '기준정보 업무 시스템'}</h1>
    {!(window as unknown as { spectonPreview?: boolean }).spectonPreview && <label>데모 접근 토큰 <input type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} /></label>}
    <p>토큰은 이 화면의 메모리에만 보관됩니다. 서버에서 역할을 확인합니다.</p>
    <nav>{contract.screens.map(s => <button data-screen={s.id} key={s.id} onClick={() => { setScreen(s.id); setResult(null); setError(''); if (!(window as unknown as { spectonPreview?: boolean }).spectonPreview) history.replaceState(null, '', s.route) }}>{s.name}</button>)}</nav>
    <h2>{selected?.name}</h2>
    {!result && !busy && !error && <p>{selected?.empty_state}</p>}
    {operations.map(op => <form data-api={op.api_id} key={op.api_id} onSubmit={e => { e.preventDefault(); void invoke(op) }}>
      <h3>{actionNames[op.action]}</h3>
      {op.action === 'get' ? <label>{op.key.name} <input required value={values[op.api_id + ':key'] ?? ''} onChange={e => setValues(v => ({ ...v, [op.api_id + ':key']: e.target.value }))} /></label> : op.action === 'list' ? <p>기본키 순서로 최대 100건을 조회합니다.</p> : op.fields.map(f => <label key={f.id} style={{ display: 'block' }}>{f.name} {f.data_type === 'boolean' ? <select aria-label={f.name} required={f.required} value={values[op.api_id + ':' + f.name] ?? ''} onChange={e => setValues(v => ({ ...v, [op.api_id + ':' + f.name]: e.target.value }))}><option value="">선택</option><option value="true">예</option><option value="false">아니오</option></select> : <input required={f.required} type={f.data_type === 'integer' ? 'number' : 'text'} step="1" maxLength={f.length ?? undefined} value={values[op.api_id + ':' + f.name] ?? ''} onChange={e => setValues(v => ({ ...v, [op.api_id + ':' + f.name]: e.target.value }))} />}</label>)}
      <button disabled={busy || !token}>{actionNames[op.action]}</button>
    </form>)}
    {stock?.operations.filter(op => selected?.api_ids.includes(op.id)).map(op => <form data-api={op.id} key={op.id} onSubmit={e => { e.preventDefault(); void invokeStock(op) }}>
      <h3>{actionNames[op.action]}</h3>
      {op.path.includes('{key}') && <label>입출고 ID <input required value={values[op.id + ':key'] ?? ''} onChange={e => setValues(v => ({ ...v, [op.id + ':key']: e.target.value }))} /></label>}
      {op.request_fields.filter(f => f.name !== 'key').map(f => <label key={f.name} style={{ display: 'block' }}>{f.name} {f.name === 'kind' ? <select aria-label={f.name} required value={values[op.id + ':kind'] ?? ''} onChange={e => setValues(v => ({ ...v, [op.id + ':kind']: e.target.value }))}><option value="">선택</option><option value="receive">입고</option><option value="issue">출고</option></select> : <input required inputMode={f.data_type === 'decimal' ? 'decimal' : 'text'} value={values[op.id + ':' + f.name] ?? ''} onChange={e => setValues(v => ({ ...v, [op.id + ':' + f.name]: e.target.value }))} />}</label>)}
      <button disabled={busy || !token}>{actionNames[op.action]}</button>
    </form>)}
    {busy && <p role="status">{selected?.loading_state}</p>}
    {error && <p role="alert">{selected?.error_state}: {error}</p>}
    {result !== null && <pre data-result>{JSON.stringify(result, null, 2)}</pre>}
  </main>
}
createRoot(document.getElementById('root')!).render(<React.StrictMode><App /></React.StrictMode>)
