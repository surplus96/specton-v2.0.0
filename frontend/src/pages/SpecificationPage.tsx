import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { specificationRequest, type Bundle, type Specification } from '../api/specifications'

const serialize = (bundle: Bundle) => JSON.stringify(bundle, null, 2)

export default function SpecificationPage() {
  const { specId } = useParams()
  const [spec, setSpec] = useState<Specification | null>(null)
  const [editor, setEditor] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  function install(value: Specification) { setSpec(value); setEditor(serialize(value.bundle)) }
  useEffect(() => {
    let active = true
    specificationRequest<Specification>(`/specs/${specId}`).then(value => {
      if (active) { setSpec(value); setEditor(serialize(value.bundle)) }
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [specId])
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError(''); setNotice('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : '처리 실패') }
    finally { setBusy(false) }
  }
  let draft: Bundle | null = null
  try { draft = JSON.parse(editor) as Bundle } catch { /* 서버가 계약 전체를 검증한다. */ }
  const dirty = spec !== null && editor !== serialize(spec.bundle)
  const latest = spec !== null && spec.bundle.spec_version === Math.max(...spec.versions)
  function answer(id: string, value: string) {
    if (!draft || !Array.isArray(draft.questions)) return
    setEditor(serialize({ ...draft, questions: draft.questions.map(q => q && q.id === id ? { ...q, answer: value.trim() ? value : null } : q) }))
  }
  return <section style={{ padding: '2rem', maxWidth: 1100 }}>
    <Link to="/projects">내 프로젝트</Link>
    <h1>실행 명세 검토</h1>
    <p>질문에 답하고 업무 역할·API·화면·규칙·인수 사례를 보완하세요. 명세 승인은 앱 생성과 별도입니다.</p>
    {error && <p role="alert">{error}</p>}
    {notice && <p role="status">{notice}</p>}
    {!spec ? <p>{error ? '명세를 조회하지 못했습니다.' : '명세를 불러오는 중입니다.'}</p> : <>
      <p>버전 {spec.bundle.spec_version} · {spec.status === 'approved' ? '승인됨' : spec.status === 'ready_for_review' ? '승인 검토 가능' : '보완 필요'}</p>
      <p>명세 해시: <code style={{ overflowWrap: 'anywhere' }}>{spec.readiness.spec_hash}</code></p>
      <label>저장 이력 <select value={spec.bundle.spec_version} disabled={busy || dirty} onChange={e => void perform(async () => {
        install(await specificationRequest<Specification>(`/specs/${specId}/versions/${e.target.value}`))
      })}>{spec.versions.map(v => <option key={v} value={v}>버전 {v}</option>)}</select></label>
      <button disabled={busy || dirty} onClick={() => void perform(async () => {
        install(await specificationRequest<Specification>(`/specs/${specId}`))
      })}>최신 버전 조회</button>
      {dirty && <p>저장하지 않은 변경이 있습니다. 먼저 저장하거나 변경을 되돌려 주세요.</p>}
      {!latest && <p>과거 버전은 읽기 전용입니다. 최신 버전에서 보완하세요.</p>}
      {spec.status === 'approved' && <p>승인한 내용은 보존됩니다. 보완하여 저장하면 새 버전이 생기며 다시 승인해야 합니다.</p>}
      <h2>저장된 버전의 보완 항목</h2>
      <ul>{spec.readiness.issues.map((issue, i) => <li key={i}>{issue.target}: {issue.message}</li>)}</ul>
      {!spec.readiness.issues.length && <p>계약 검사를 통과했습니다. 업무 의미와 인수 조건을 확인한 후 승인하세요.</p>}
      <h2>확인 질문</h2>
      {spec.bundle.questions.map(q => {
        const value = draft && Array.isArray(draft.questions) ? draft.questions.find(item => item && item.id === q.id)?.answer : q.answer
        return <div key={q.id} style={{ marginBlock: '1rem' }}>
          <p>연결 요구: {q.req_ids.map(id => spec.bundle.requirements.find(r => r.id === id)?.text ?? id).join(' / ')}</p>
          <label>{q.question}
          <textarea aria-label={`답변 ${q.id}`} rows={3} style={{ display: 'block', width: '100%' }}
            disabled={busy || !latest || !draft} value={typeof value === 'string' ? value : ''} onChange={e => answer(q.id, e.target.value)} />
        </label></div>
      })}
      <h2>실행 계약 편집</h2>
      <p>초안의 Must와 화면 필요 여부는 확인 전 기본값입니다. 제외하는 요구도 삭제하지 말고 우선순위와 사유를 남기세요. 출처·ID·버전은 유지하세요.</p>
      <label>명세 JSON <textarea spellCheck={false} rows={25} style={{ width: '100%', fontFamily: 'monospace' }}
        value={editor} disabled={busy || !latest} onChange={e => setEditor(e.target.value)} /></label>
      <button disabled={busy || !latest || !dirty || !draft} onClick={() => void perform(async () => {
        install(await specificationRequest<Specification>(`/specs/${specId}`, 'PATCH', {
          expected_version: spec.bundle.spec_version, spec_hash: spec.readiness.spec_hash, bundle: JSON.parse(editor),
        })); setNotice('새 버전을 저장했습니다. 보완 항목을 다시 확인하세요.')
      })}>새 버전 저장</button>
      <button disabled={busy || !dirty} onClick={() => { setEditor(serialize(spec.bundle)); setError('') }}>편집 되돌리기</button>
      <button disabled={busy || dirty || !latest || !spec.readiness.ready_for_review || spec.status === 'approved'} onClick={() => void perform(async () => {
        install(await specificationRequest<Specification>(`/specs/${specId}/approve`, 'POST', {
          expected_version: spec.bundle.spec_version, spec_hash: spec.readiness.spec_hash,
        })); setNotice('현재 명세 버전과 해시를 승인했습니다.')
      })}>이 버전의 실행 명세 승인</button>
    </>}
    {busy && <p role="status">처리 중입니다.</p>}
  </section>
}
