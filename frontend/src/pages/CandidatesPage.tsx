import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { specificationRequest as api } from '../api/specifications'

type Candidate = { id: string; spec_version: number; design_version: number; source_hash: string; verification_status: string | null }
type Adoption = { id: string; sequence: number; implementation_id: string; rationale: string; created_at: string }
type Check = { status: string; name?: string; id?: string; api_id?: string; screen_id?: string; req_ids?: string[] }
type Comparison = {
  comparison_hash: string; current_adoption: Adoption | null; eligible: boolean; reasons: string[]
  latest_verification_id: string | null; latest_verification_status: string; ddl_changed: boolean
  unverified_acceptance_count: number; unverified_acceptance: { id: string; req_ids: string[]; tier: string }[]
  files: { path: string; change: string; before_hash: string | null; after_hash: string | null; diff: string | null; truncated: boolean }[]
  semantic: Record<string, { added: string[]; removed: string[]; modified: string[] } | boolean>
  verification: { checks: Check[]; browser_checks: Check[]; report_hash: string } | null
}
type Listing = { items: Candidate[]; current_adoption: Adoption | null }

export default function CandidatesPage() {
  const { projectId } = useParams()
  const root = '/projects/' + projectId
  const [listing, setListing] = useState<Listing>({ items: [], current_adoption: null })
  const [history, setHistory] = useState<Adoption[]>([])
  const [candidate, setCandidate] = useState('')
  const [base, setBase] = useState('')
  const [comparison, setComparison] = useState<Comparison | null>(null)
  const [rationale, setRationale] = useState('')
  const [ack, setAck] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  // Retain the same key/body for a network retry; a successful adoption clears it.
  const [pending, setPending] = useState<{ key: string; signature: string } | null>(null)
  useEffect(() => {
    let active = true
    Promise.all([api<Listing>(root + '/candidates'), api<{ history: Adoption[] }>(root + '/implementation-baseline')])
      .then(([list, audit]) => { if (active) { setListing(list); setHistory(audit.history); setCandidate(list.items[0]?.id ?? '') } })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : '조회 실패') })
    return () => { active = false }
  }, [root])
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : '처리 실패') }
    finally { setBusy(false) }
  }
  function reset() { setComparison(null); setAck(false); setPending(null) }
  return <section style={{ padding: '2rem', maxWidth: 1100 }}>
    <Link to="/projects">내 프로젝트</Link>
    <h1>검증 후보 비교·채택</h1>
    <p>변경 내용과 검증 근거를 검토하여 프로젝트의 구현 기준을 고정합니다. 채택은 서비스 배포를 실행하지 않습니다.</p>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    <p>현재 기준: {listing.current_adoption ? `#${listing.current_adoption.sequence} · ${listing.current_adoption.implementation_id}` : '아직 채택하지 않음'}</p>
    <label>후보 <select disabled={busy} value={candidate} onChange={e => { setCandidate(e.target.value); reset() }}>
      <option value="">후보 선택</option>
      {listing.items.map(c => <option key={c.id} value={c.id}>설계 {c.design_version} / 명세 {c.spec_version} · {c.id.slice(0, 8)} · {c.verification_status ?? '미검증'}</option>)}
    </select></label>{' '}
    <label>비교 기준 <select disabled={busy} value={base} onChange={e => { setBase(e.target.value); reset() }}>
      <option value="">현재 채택 기준 (최초 채택이면 빈 기준)</option>
      {listing.items.map(c => <option key={c.id} value={c.id}>{c.id.slice(0, 8)} · 명세 {c.spec_version}</option>)}
    </select></label>{' '}
    <button disabled={busy || !candidate} onClick={() => void perform(async () => {
      reset()
      setComparison(await api<Comparison>(root + '/candidates/' + candidate + '/comparison' + (base ? '?base_id=' + base : '')))
    })}>변경·검증 비교</button>
    {!listing.items.length && <p>실행 명세에서 구현 후보를 먼저 생성해 주세요.</p>}
    <p>최근 후보 100개와 채택 이력 50개를 표시합니다.</p>
    {comparison && <article>
      <h2>비교 결과</h2>
      <p>최근 검증: {comparison.latest_verification_status} · DDL 변경: {comparison.ddl_changed ? '있음' : '없음'}</p>
      {comparison.reasons.length > 0 && <ul>{comparison.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
      <table><caption>명세 변경</caption><thead><tr><th>구분</th><th>추가</th><th>삭제</th><th>수정</th></tr></thead>
        <tbody>{Object.entries(comparison.semantic).map(([name, value]) => typeof value === 'boolean'
          ? <tr key={name}><th>{name}</th><td colSpan={3}>{value ? '변경됨' : '동일'}</td></tr>
          : <tr key={name}><th>{name}</th><td>{value.added.join(', ') || '—'}</td><td>{value.removed.join(', ') || '—'}</td><td>{value.modified.join(', ') || '—'}</td></tr>)}</tbody>
      </table>
      <h3>소스 변경 ({comparison.files.length})</h3>
      {comparison.files.map(file => <details key={file.path}><summary>{file.path} · {file.change}</summary>
        <p style={{ overflowWrap: 'anywhere' }}>이전 SHA-256: {file.before_hash ?? '없음'}<br />이후 SHA-256: {file.after_hash ?? '없음'}</p>
        {file.truncated && <p>큰 변경은 일부만 표시합니다. 전체 소스를 내려받아 확인하세요.</p>}
        <pre style={{ overflow: 'auto', maxHeight: 400 }}>{file.diff ?? '텍스트 비교를 생략했습니다.'}</pre>
      </details>)}
      <p><a href={'/api/v1/implementations/' + candidate + '/source'}>후보 소스 내려받기</a></p>
      <h3>검증 범위</h3>
      {comparison.verification && <>
        <p style={{ overflowWrap: 'anywhere' }}>보고서 SHA-256: {comparison.verification.report_hash}</p>
        <details><summary>고정 API·브라우저 검증 항목</summary>
          <pre style={{ overflow: 'auto' }}>{JSON.stringify({ api: comparison.verification.checks, browser: comparison.verification.browser_checks }, null, 2)}</pre>
        </details>
      </>}
      <p>명세의 업무 인수 조건 {comparison.unverified_acceptance_count}건은 자동 판정하지 않았습니다. 고정 시나리오 통과만 확인되며 별도 업무 인수가 필요합니다.</p>
      <details><summary>미검증 인수 조건 (최대 100건)</summary><ul>{comparison.unverified_acceptance.map(c => <li key={c.id}>{c.id} · {c.tier} · {c.req_ids.join(', ')}</li>)}</ul></details>
      <form onSubmit={e => { e.preventDefault(); void perform(async () => {
        const body = { implementation_id: candidate, verification_id: comparison.latest_verification_id,
          expected_current_id: comparison.current_adoption?.id ?? null, comparison_hash: comparison.comparison_hash,
          rationale: rationale.trim(), acknowledge_unverified_acceptance: ack }
        const signature = JSON.stringify(body)
        const key = pending?.signature === signature ? pending.key : crypto.randomUUID()
        setPending({ key, signature })
        await api(root + '/adoptions', 'POST', { ...body, request_key: key })
        reset(); setRationale('')
        const [list, audit] = await Promise.all([api<Listing>(root + '/candidates'), api<{ history: Adoption[] }>(root + '/implementation-baseline')])
        setListing(list); setHistory(audit.history); setNotice('구현 기준을 채택하고 검토 이력을 기록했습니다.')
      }) }}>
        <p><label>채택 사유 (10~2,000자)<br /><textarea disabled={busy} required minLength={10} maxLength={2000} value={rationale} onChange={e => setRationale(e.target.value)} rows={3} style={{ width: '100%' }} /></label></p>
        <p><label><input type="checkbox" disabled={busy} checked={ack} onChange={e => setAck(e.target.checked)} />업무 인수 조건이 미검증임을 확인하고 구현 기준으로 채택합니다.</label></p>
        <button disabled={busy || !comparison.eligible || !ack || rationale.trim().length < 10}>검토한 후보 채택</button>
      </form>
    </article>}
    <h2>채택 이력</h2>
    <ol>{history.map(item => <li key={item.id}>#{item.sequence} · {item.implementation_id} · {new Date(item.created_at).toLocaleString()}<p>{item.rationale}</p></li>)}</ol>
    {busy && <p role="status">처리 중입니다.</p>}
  </section>
}
