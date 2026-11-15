import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import PreviewFrame from './PreviewFrame'
import { specificationRequest, type Bundle, type Specification } from '../api/specifications'

type Preview = { id: string; status: string; expires_at: string; error_code: string | null }
type Verification = { id: string; status: string; source_hash: string; report_hash: string | null; error_code: string | null; report: { browser_acceptance?: string; browser?: { screenshot_base64?: string } } | null }
const activeStatuses = ['queued', 'running', 'cancelling', 'recovering']
const serialize = (bundle: Bundle) => JSON.stringify(bundle, null, 2)

export default function SpecificationPage() {
  const { specId } = useParams()
  const [params] = useSearchParams()
  const linkedImplementation = params.get("implementation")
  const [spec, setSpec] = useState<Specification | null>(null)
  const [editor, setEditor] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [catalog, setCatalog] = useState<unknown>(null)
  const [implementation, setImplementation] = useState<{ id: string; source_hash: string; spec_version: number } | null>(null)
  const [previews, setPreviews] = useState<Preview[]>([])
  const [openPreview, setOpenPreview] = useState<string | null>(null)
  const [verifications, setVerifications] = useState<Verification[]>([])
  useEffect(() => {
    if (!implementation) return
    let active = true
    async function refresh() {
      try {
        const rows = await specificationRequest<Verification[]>(`/implementations/${implementation!.id}/verifications`)
        if (active) setVerifications(rows)
        const previews = await specificationRequest<Preview[]>(`/implementations/${implementation!.id}/previews`)
        if (active) setPreviews(previews)
      } catch (e) { if (active) setError(e instanceof Error ? e.message : '검증 조회 실패') }
    }
    void refresh()
    const timer = window.setInterval(() => void refresh(), 3000)
    return () => { active = false; window.clearInterval(timer) }
  }, [implementation])
  function install(value: Specification) { setSpec(value); setEditor(serialize(value.bundle)); setImplementation(null); setVerifications([]); setPreviews([]); setOpenPreview(null) }
  useEffect(() => {
    let active = true
    specificationRequest<Specification>(`/specs/${specId}`).then(value => {
      if (active) { setSpec(value); setEditor(serialize(value.bundle)); setImplementation(null); setVerifications([]); setPreviews([]); setOpenPreview(null) }
    }).catch(e => { if (active) setError(e.message) })
    return () => { active = false }
  }, [specId])
  useEffect(() => {
    if (!linkedImplementation || !spec) return
    let active = true
    specificationRequest<{ id: string; source_hash: string; spec_version: number }>(`/implementations/${linkedImplementation}`)
      .then(value => { if (active && value.spec_version === spec.bundle.spec_version) setImplementation(value) })
      .catch(e => { if (active) setError(e instanceof Error ? e.message : '후보 조회 실패') })
    return () => { active = false }
  }, [linkedImplementation, spec])
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
      <h2>생성기 연결</h2>
      <p>기준정보 등록·단건 조회와 spec-v0.3의 stock-ledger-v1 재고 정책을 지원합니다. 재고 정책은 단일 창고·품목의 초안·수정·확정·취소·조회와 소수 셋째 자리 수량, 음수 재고 금지, 원장·잔량 동시 반영을 명시적으로 승인해야 합니다.</p>
      <p>명세를 spec-v0.2로 보완하고 storage_bindings에 테이블·컬럼 ID, operation_bindings에 API의 insert/get 동작·조회 키와 key_format: url-safe-segment를 연결한 뒤 다시 승인하세요. 문자열 기본키는 영문·숫자·밑줄·하이픈만 지원합니다. 재고를 생성하려면 spec-v0.3에서 inventory 정책과 6개 재고 API 계약을 추가하세요. 기존 v0.1·v0.2 승인 해시는 유지됩니다.</p>
      <button disabled={busy} onClick={() => void perform(async () => {
        setCatalog(await specificationRequest(`/specs/${specId}/storage-catalog`))
      })}>승인 설계의 테이블·컬럼 확인</button>
      {catalog !== null && <details open><summary>승인 저장 구조</summary><pre style={{ overflow: 'auto', maxHeight: 400 }}>{JSON.stringify(catalog, null, 2)}</pre></details>}
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
      <h2>생성 소스</h2>
      <button disabled={busy || dirty || !latest || spec.status !== 'approved'} onClick={() => void perform(async () => {
        const source = await specificationRequest<{ id: string; source_hash: string; spec_version: number }>(`/specs/${specId}/implementations`, 'POST', {
          expected_version: spec.bundle.spec_version, spec_hash: spec.readiness.spec_hash,
        })
        setVerifications([]); setPreviews([]); setOpenPreview(null); setImplementation(source); setNotice('소스 묶음을 생성했습니다. 실행·업무 인수·채택은 별도 단계입니다.')
      })}>승인한 명세로 소스 생성·조회</button>
      {implementation && <div><p>명세 버전 {implementation.spec_version} · 소스 생성 완료</p>
        <p>SHA-256: <code style={{ overflowWrap: 'anywhere' }}>{implementation.source_hash}</code></p>
        <a href={`/api/v1/implementations/${implementation.id}/source`}>생성 소스 ZIP 내려받기</a>
        <p>별도 작업자가 격리 DB·HTTP 검증을 실행합니다. 통과해도 브라우저·업무 인수나 후보 채택을 의미하지 않습니다.</p>
        <button disabled={busy || dirty || !latest || verifications.some(v => activeStatuses.includes(v.status))} onClick={() => void perform(async () => {
          const job = await specificationRequest<Verification>(`/implementations/${implementation.id}/verifications`, 'POST', {
            expected_version: spec.bundle.spec_version, spec_hash: spec.readiness.spec_hash,
            source_hash: implementation.source_hash, request_key: crypto.randomUUID(),
          })
          setVerifications(rows => [job, ...rows.filter(row => row.id !== job.id)])
        })}>격리 검증 요청·재실행</button>
        {!verifications.length && <p>검증 이력이 없습니다.</p>}
        {verifications.map(job => <article key={job.id}>
          <p>검증 상태: {job.status} {job.error_code && `· ${job.error_code}`}</p>
          {activeStatuses.includes(job.status) && <button disabled={busy || job.status === 'cancelling'} onClick={() => void perform(async () => {
            const updated = await specificationRequest<Verification>(`/implementations/${implementation.id}/verifications/${job.id}/cancel`, 'POST')
            setVerifications(rows => rows.map(row => row.id === updated.id ? updated : row))
          })}>검증 취소</button>}
          <p>고정 화면 인수: {job.report?.browser_acceptance ?? 'not_run'}</p>
          {job.report?.browser?.screenshot_base64 && <details><summary>브라우저 검증 화면</summary><img alt="브라우저 검증 결과 화면" style={{ maxWidth: '100%' }} src={'data:image/png;base64,' + job.report.browser.screenshot_base64} /></details>}
          {job.report_hash && <p>결과 SHA-256: <code>{job.report_hash}</code></p>}
          {job.status === 'smoke_passed' && job.report?.browser_acceptance === 'passed' && <button disabled={busy || previews.some(p => !['closed', 'failed'].includes(p.status))} onClick={() => void perform(async () => {
            const preview = await specificationRequest<Preview>(`/implementations/${implementation.id}/previews`, 'POST', { verification_id: job.id, request_key: crypto.randomUUID() })
            setPreviews(rows => [preview, ...rows])
          })}>브라우저 검증 소스로 미리보기 준비</button>}
          {job.report !== null && <details><summary>검증 증거</summary><pre style={{ overflow: 'auto' }}>{JSON.stringify(job.report, null, 2)}</pre></details>}
        </article>)}
        {previews.map(preview => <article key={preview.id}>
          <p>미리보기: {preview.status} · 만료 {new Date(preview.expires_at).toLocaleString()} {preview.error_code}</p>
          <button disabled={preview.status !== 'ready' || Date.parse(preview.expires_at) <= Date.now()} onClick={() => setOpenPreview(preview.id)}>미리보기 열기</button>
          <button disabled={busy || ['closed', 'failed'].includes(preview.status)} onClick={() => void perform(async () => {
            const closed = await specificationRequest<Preview>(`/previews/${preview.id}/close`, 'POST')
            setPreviews(rows => rows.map(row => row.id === closed.id ? closed : row)); setOpenPreview(null)
          })}>미리보기 종료</button>
          {openPreview === preview.id && preview.status === 'ready' && Date.parse(preview.expires_at) > Date.now() && <PreviewFrame id={preview.id} />}
        </article>)}
      </div>}
    </>}
    {busy && <p role="status">처리 중입니다.</p>}
  </section>
}
