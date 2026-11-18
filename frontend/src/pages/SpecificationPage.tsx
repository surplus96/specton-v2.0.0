import TestPreparationImport from '../ui/TestPreparationImport'
import WorkflowStatus from '../ui/WorkflowStatus'
import ScopeAssessment from '../ui/ScopeAssessment'
import HandoffAssessment from '../ui/HandoffAssessment'
import ApiAcceptanceEditor from '../ui/ApiAcceptanceEditor'
import RequirementResults, { type RequirementEvidence } from '../ui/RequirementResults'
import Button from '../ui/Button'
import Notice from '../ui/Notice'
import { useEffect, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router'
import PreviewFrame from './PreviewFrame'
import { specificationRequest, type Bundle, type Specification } from '../api/specifications'

type Preview = { id: string; status: string; expires_at: string; error_code: string | null }
type Verification = { id: string; status: string; source_hash: string; report_hash: string | null; error_code: string | null; report: { requirements?: RequirementEvidence; browser_acceptance?: string; browser?: { screenshot_base64?: string } } | null }
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
  const [completionInstruction, setCompletionInstruction] = useState('')
  const [completionConsent, setCompletionConsent] = useState(false)
  const [completion, setCompletion] = useState<{ bundle: Bundle; readiness: Specification['readiness']; generation_ready: boolean; generation_issue: string | null } | null>(null)
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
  function install(value: Specification) { setCompletion(null); setSpec(value); setEditor(serialize(value.bundle)); setImplementation(null); setVerifications([]); setPreviews([]); setOpenPreview(null) }
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
  return <section className="screen extension-page">
    <Link to="/projects">내 프로젝트</Link>
    <header className="screen-head"><h1 className="hero">실행 명세 검토</h1></header>
    <div className="panel extension-content">
    <p>질문에 답하고 업무 역할·API·화면·규칙·인수 사례를 보완하세요. 명세 승인은 앱 생성과 별도입니다.</p>
    {error && <Notice kind="error" title={error} />}
    {notice && <Notice kind="success" title={notice} />}
    {!spec ? <p>{error ? '명세를 조회하지 못했습니다.' : '명세를 불러오는 중입니다.'}</p> : <>
      <p>버전 {spec.bundle.spec_version} · <WorkflowStatus state={spec.status} /></p>
      <p>명세 해시: <code style={{ overflowWrap: 'anywhere' }}>{spec.readiness.spec_hash}</code></p>
      <label>저장 이력 <select value={spec.bundle.spec_version} disabled={busy || dirty} onChange={e => void perform(async () => {
        install(await specificationRequest<Specification>(`/specs/${specId}/versions/${e.target.value}`))
      })}>{spec.versions.map(v => <option key={v} value={v}>버전 {v}</option>)}</select></label>
      <Button variant="secondary" type="button" disabled={busy || dirty} onClick={() => void perform(async () => {
        install(await specificationRequest<Specification>(`/specs/${specId}`))
      })}>최신 버전 조회</Button>
      {dirty && <p>저장하지 않은 변경이 있습니다. 먼저 저장하거나 변경을 되돌려 주세요.</p>}
      {!latest && <p>과거 버전은 읽기 전용입니다. 최신 버전에서 보완하세요.</p>}
      {spec.status === 'approved' && <p>승인한 내용은 보존됩니다. 보완하여 저장하면 새 버전이 생기며 다시 승인해야 합니다.</p>}
      <h2>승인 설계에서 시스템 구성</h2>
      <ScopeAssessment path={`/api/v1/specs/${specId}/scope?version=${spec.bundle.spec_version}`} />
      <HandoffAssessment key={`handoff:${specId}:${spec.bundle.spec_version}`} path={`/api/v1/specs/${specId}/handoff?version=${spec.bundle.spec_version}`} />
      <p>도메인 이름이나 업무별 기본값을 선택하지 않습니다. 승인된 테이블·관계·기능을 출처로 실행 명세를 구성합니다. 구현하지 못한 요구는 검토 항목으로 남습니다.</p>
      <Button disabled={busy || dirty || !latest} onClick={() => void perform(async () => {
        const result=await specificationRequest<{bundle:Bundle;readiness:Specification['readiness'];generation_ready:boolean;generation_issue:string|null}>(`/specs/${specId}/derive`,'POST',{expected_version:spec.bundle.spec_version,spec_hash:spec.readiness.spec_hash})
        setCompletion(result);setEditor(serialize(result.bundle));setNotice('승인 설계의 구조를 연결했습니다. 요구별 업무 동작을 검토한 후 저장하세요.')
      })}>승인 설계 구조 자동 연결</Button>
      {draft?.domain && <section><h3>요구별 구현 상태</h3><ul>{draft.domain.coverage.map(c=><li key={c.requirement_id}>{draft.requirements.find(r=>r.id===c.requirement_id)?.text} · <select aria-label={'구현 상태 '+c.requirement_id} value={c.status} disabled={busy||!latest} onChange={e=>{if(draft?.domain)setEditor(serialize({...draft,domain:{...draft.domain,coverage:draft.domain.coverage.map(row=>row.requirement_id===c.requirement_id?{...row,status:e.target.value as typeof c.status}:row)}}))}}><option value="needs_review">업무 연결 검토 필요</option><option value="mapped">실행 동작 연결 검토함</option><option value="unsupported">추가 구현 필요</option></select> · {c.explanation}</li>)}</ul></section>}
      <h2>승인 설계로 실행 명세 자동 작성</h2>
      {draft && <ApiAcceptanceEditor key={`${specId}:${spec.bundle.spec_version}`} bundle={draft} disabled={busy || !latest} onChange={value => setEditor(serialize(value))} />}
      <p>승인 설계의 요구·기능·DB 구조를 바탕으로 역할·화면·API·저장 연결과 인수 계획을 제안합니다. 결과는 편집기에만 반영되며, 저장과 승인은 직접 진행합니다. 미확정 업무 규칙의 답변은 자동으로 확정하지 않습니다.</p>
      <p>기존 실행 계약이 많은 명세는 화면 안내와 기능 설명의 변경안을 받아 보완합니다. API·명령·계산·인수 기대값은 유지하며, 새 실행 계약이 필요한 요청은 확인 질문으로 남깁니다.</p>
      <label>구현 범위·추가 지시<textarea rows={4} maxLength={12000} disabled={busy} value={completionInstruction} onChange={e => setCompletionInstruction(e.target.value)} placeholder="구현할 업무 범위와 이미 결정한 정책을 적어주세요. 제외할 요구가 있다면 이유를 명시하세요." /></label>
      <label><input type="checkbox" disabled={busy} checked={completionConsent} onChange={e => setCompletionConsent(e.target.checked)} />승인 설계·현재 명세·추가 지시를 외부 AI에 전송해 실행 명세를 작성하는 데 동의합니다.</label>
      <Button loading={busy} loadingText="처리 중" disabled={busy || dirty || !latest || !completionConsent} onClick={() => void perform(async () => {
        const result = await specificationRequest<{ bundle: Bundle; readiness: Specification['readiness']; generation_ready: boolean; generation_issue: string | null }>(`/specs/${specId}/complete`, 'POST', {
          expected_version: spec.bundle.spec_version, spec_hash: spec.readiness.spec_hash,
          instruction: completionInstruction, consent_external_analysis: true,
        })
        setCompletion(result); setEditor(serialize(result.bundle));
        setNotice('자동 작성안을 편집기에 반영했습니다. 범위·권한·질문과 계약을 검토한 뒤 새 버전으로 저장하세요.')
      })}>승인 설계에서 실행 명세 자동 작성</Button>
      {completion && <Notice kind={completion.generation_ready ? 'success' : 'warning'} title={completion.generation_ready ? '생성기 계약 검사 통과 · 사용자 승인 필요' : '추가 보완이 필요한 작성안'}>
        {completion.generation_issue}
        <ul>{completion.readiness.issues.map((issue, i) => <li key={i}>{issue.message}</li>)}</ul>
      </Notice>}
      {draft && <details open={completion !== null}><summary>편집 중인 기능·화면 구성</summary>
        <p>화면 {draft.screens?.length ?? 0}개 · API {draft.apis?.length ?? 0}개 · 저장 연결 {draft.storage_bindings?.length ?? 0}개</p>
        <ul>{draft.screens?.map(screen => <li key={screen.id}>{screen.name} · {screen.route} · API {screen.api_ids.join(', ')}</li>)}</ul>
        <ul>{draft.use_cases?.map(use => <li key={use.id}>{use.name} · {use.steps.join(' → ')}</li>)}</ul>
      </details>}
      <h2>저장된 버전의 보완 항목</h2>
      <ul>{spec.readiness.issues.map((issue, i) => <li key={i}>{issue.target}: {issue.message}</li>)}</ul>
      {!spec.readiness.issues.length && <p>계약 검사를 통과했습니다. 업무 의미와 인수 조건을 확인한 후 승인하세요.</p>}
      <h2>확인 질문</h2>
      {(draft?.questions ?? spec.bundle.questions).map(q => {
        const value = draft && Array.isArray(draft.questions) ? draft.questions.find(item => item && item.id === q.id)?.answer : q.answer
        return <div key={q.id} style={{ marginBlock: '1rem' }}>
          <p>연결 요구: {q.req_ids.map(id => spec.bundle.requirements.find(r => r.id === id)?.text ?? id).join(' / ')}</p>
          <label>{q.question}
          <textarea aria-label={`답변 ${q.id}`} rows={3} style={{ display: 'block', width: '100%' }}
            disabled={busy || !latest || !draft} value={typeof value === 'string' ? value : ''} onChange={e => answer(q.id, e.target.value)} />
        </label></div>
      })}
      <h2>생성기 연결</h2>
      <p>기본 생성기는 승인 테이블과 관계, 조건 검사·상태 전이를 사용하는 도메인 공통 실행 계약입니다. 최대 8개 레코드의 등록·수정을 하나의 트랜잭션으로 처리하고 실패하면 전체를 취소합니다. spec-v0.9에서는 단위·반올림·0분모 정책을 명시한 계산과 단일 테이블의 개수·합계·평균·최솟값·최댓값 집계를 지원합니다. 조인·그룹 집계·가변 일괄 변경·일정 실행·외부 전송은 추가 구현 대상입니다.</p>
      {!!draft?.domain?.commands?.length && <section><h3>함께 처리할 변경</h3><ul>{draft.domain.commands.map(command => <li key={command.api_id}>
        {draft.use_cases.find(use => use.id === draft.apis.find(api => api.id === command.api_id)?.use_case_id)?.name ?? command.api_id}
        {' · '}대상 {command.targets.length}개 · 변경 {command.writes.length}개 · 사전 조건 {command.before.length}개 · 사후 조건 {command.after.length}개
      </li>)}</ul><p>대상 키·역할·조건과 정상·경계·실패 인수 사례를 검토한 뒤 승인하세요. 승인한 명령은 생성된 고객 앱의 연결 화면에 표시됩니다.</p></section>}
      {!!draft?.domain?.calculations?.length && <section><h3>계산·집계 계약</h3><ul>{draft.domain.calculations.map(query => <li key={query.api_id}>
        {draft.use_cases.find(use => use.id === draft.apis.find(api => api.id === query.api_id)?.use_case_id)?.name ?? query.api_id}
        {' · '}집계 {query.aggregates.length}개 · 계산 {query.calculations.length}단계 · 최대 {query.max_rows.toLocaleString()}행
        <ul>{query.aggregates.map(measure => <li key={measure.id}>{measure.id}: {measure.operator} · 소수 {measure.result.scale}자리 · {measure.result.rounding} · 빈 결과 {measure.empty_policy}</li>)}</ul>
      </li>)}</ul><p>단위·기간 경계·빈 결과·0분모·반올림과 독립 기대값을 검토하세요. 집계 한도를 초과하면 일부 데이터의 결과를 반환하지 않습니다.</p></section>}
      <p>기준정보 등록·단건 조회, spec-v0.4의 목록 조회·수정과 stock-ledger-v1 재고 정책을 지원합니다. 재고 정책은 단일 창고·품목의 초안·수정·확정·취소·조회와 소수 셋째 자리 수량, 음수 재고 금지, 원장·잔량 동시 반영을 명시적으로 승인해야 합니다.</p>
      <p>명세를 spec-v0.2로 보완하고 storage_bindings에 테이블·컬럼 ID, operation_bindings에 API의 insert/get 동작·조회 키와 key_format: url-safe-segment를 연결한 뒤 다시 승인하세요. 문자열 기본키는 영문·숫자·밑줄·하이픈만 지원합니다. 재고를 생성하려면 spec-v0.3에서 inventory 정책과 6개 재고 API 계약을 추가하세요. 기존 v0.1·v0.2 승인 해시는 유지됩니다.</p>
      <Button variant="primary" type="button" disabled={busy} onClick={() => void perform(async () => {
        setCatalog(await specificationRequest(`/specs/${specId}/storage-catalog`))
      })}>승인 설계의 테이블·컬럼 확인</Button>
      {catalog !== null && <details open><summary>승인 저장 구조</summary><pre style={{ overflow: 'auto', maxHeight: 400 }}>{JSON.stringify(catalog, null, 2)}</pre></details>}
      <TestPreparationImport key={`preparation:${specId}:${spec.bundle.spec_version}`} spec={spec} disabled={busy || !latest || dirty} onApply={bundle => {
        setEditor(serialize(bundle)); setCompletion(null); setNotice('준비안을 편집기에 반영했습니다. 범위·기대값·질문을 확인한 뒤 새 버전으로 저장하세요.')
      }} />
      <h2>실행 계약 편집</h2>
      <p>초안의 Must와 화면 필요 여부는 확인 전 기본값입니다. 제외하는 요구도 삭제하지 말고 우선순위와 사유를 남기세요. 출처·ID·버전은 유지하세요.</p>
      <label>명세 JSON <textarea aria-label="명세 JSON" spellCheck={false} rows={25} style={{ width: '100%', fontFamily: 'monospace' }}
        value={editor} disabled={busy || !latest} onChange={e => setEditor(e.target.value)} /></label>
      <Button variant="primary" type="button" disabled={busy || !latest || !dirty || !draft} onClick={() => void perform(async () => {
        install(await specificationRequest<Specification>(`/specs/${specId}`, 'PATCH', {
          expected_version: spec.bundle.spec_version, spec_hash: spec.readiness.spec_hash, bundle: JSON.parse(editor),
        })); setNotice('새 버전을 저장했습니다. 보완 항목을 다시 확인하세요.')
      })}>새 버전 저장</Button>
      <Button variant="secondary" type="button" disabled={busy || !dirty} onClick={() => { setEditor(serialize(spec.bundle)); setCompletion(null); setError(''); setNotice('') }}>편집 되돌리기</Button>
      <Button variant="primary" type="button" disabled={busy || dirty || !latest || !spec.readiness.ready_for_review || spec.status === 'approved'} onClick={() => void perform(async () => {
        install(await specificationRequest<Specification>(`/specs/${specId}/approve`, 'POST', {
          expected_version: spec.bundle.spec_version, spec_hash: spec.readiness.spec_hash,
        })); setNotice('현재 명세 버전과 해시를 승인했습니다.')
      })}>이 버전의 실행 명세 승인</Button>
      <h2>후속 설계 산출물</h2>
      <p>승인된 실행 명세의 기능·화면·API와 추적표를 별도 버전으로 생성합니다. 업무 데모의 파생 테이블과 승인한 추가 필드는 ERD·DDL에 반영합니다. 새 버전은 빈 격리 DB에서 검증하며 기존 앱의 운영 데이터를 이관하지 않습니다. 기존 설계 버전은 보존됩니다.</p>
      {spec.status === 'approved' && !dirty && latest && <a className="btn btn--secondary" href={`/api/v1/specs/${specId}/design`}>승인 실행 설계 ZIP 내려받기</a>}
      <h2>생성 소스</h2>
      <Button variant="primary" type="button" disabled={busy || dirty || !latest || spec.status !== 'approved'} onClick={() => void perform(async () => {
        const source = await specificationRequest<{ id: string; source_hash: string; spec_version: number }>(`/specs/${specId}/implementations`, 'POST', {
          expected_version: spec.bundle.spec_version, spec_hash: spec.readiness.spec_hash,
        })
        setVerifications([]); setPreviews([]); setOpenPreview(null); setImplementation(source); setNotice('소스 묶음을 생성했습니다. 실행·업무 인수·채택은 별도 단계입니다.')
      })}>승인한 명세로 소스 생성·조회</Button>
      {implementation && <div><p>명세 버전 {implementation.spec_version} · 소스 생성 완료</p>
        <p>SHA-256: <code style={{ overflowWrap: 'anywhere' }}>{implementation.source_hash}</code></p>
        <a href={`/api/v1/implementations/${implementation.id}/source`}>생성 소스 ZIP 내려받기</a>
        <p>별도 작업자가 격리 DB·HTTP 검증을 실행합니다. 통과해도 브라우저·업무 인수나 후보 채택을 의미하지 않습니다.</p>
        <Button variant="secondary" type="button" disabled={busy || dirty || !latest || verifications.some(v => activeStatuses.includes(v.status))} onClick={() => void perform(async () => {
          const job = await specificationRequest<Verification>(`/implementations/${implementation.id}/verifications`, 'POST', {
            expected_version: spec.bundle.spec_version, spec_hash: spec.readiness.spec_hash,
            source_hash: implementation.source_hash, request_key: crypto.randomUUID(),
          })
          setVerifications(rows => [job, ...rows.filter(row => row.id !== job.id)])
        })}>격리 검증 요청·재실행</Button>
        {!verifications.length && <p>검증 이력이 없습니다.</p>}
        {verifications.map(job => <article className="panel extension-card" key={job.id}>
          <p>검증 상태: <WorkflowStatus state={job.status} /> {job.error_code && `· ${job.error_code}`}</p>
          {activeStatuses.includes(job.status) && <Button variant="secondary" type="button" disabled={busy || job.status === 'cancelling'} onClick={() => void perform(async () => {
            const updated = await specificationRequest<Verification>(`/implementations/${implementation.id}/verifications/${job.id}/cancel`, 'POST')
            setVerifications(rows => rows.map(row => row.id === updated.id ? updated : row))
          })}>검증 취소</Button>}
          <p>고정 화면 인수: <WorkflowStatus state={job.report?.browser_acceptance} /></p>
          <RequirementResults evidence={job.report?.requirements} />
          {job.report?.browser?.screenshot_base64 && <details><summary>브라우저 검증 화면</summary><img alt="브라우저 검증 결과 화면" style={{ maxWidth: '100%' }} src={'data:image/png;base64,' + job.report.browser.screenshot_base64} /></details>}
          {job.report_hash && <p>결과 SHA-256: <code>{job.report_hash}</code></p>}
          {job.status === 'smoke_passed' && job.report?.browser_acceptance === 'passed' && <Button variant="secondary" type="button" disabled={busy || previews.some(p => !['closed', 'failed'].includes(p.status))} onClick={() => void perform(async () => {
            const preview = await specificationRequest<Preview>(`/implementations/${implementation.id}/previews`, 'POST', { verification_id: job.id, request_key: crypto.randomUUID() })
            setPreviews(rows => [preview, ...rows])
          })}>브라우저 검증 소스로 미리보기 준비</Button>}
          {job.report !== null && <details><summary>검증 증거</summary><pre style={{ overflow: 'auto' }}>{JSON.stringify(job.report, null, 2)}</pre></details>}
        </article>)}
        {previews.map(preview => <article className="panel extension-card" key={preview.id}>
          <p>미리보기: <WorkflowStatus state={preview.status} /> · 만료 {new Date(preview.expires_at).toLocaleString()} {preview.error_code}</p>
          <Button variant="secondary" type="button" disabled={preview.status !== 'ready' || Date.parse(preview.expires_at) <= Date.now()} onClick={() => setOpenPreview(preview.id)}>미리보기 열기</Button>
          <Button variant="secondary" type="button" disabled={busy || ['closed', 'failed'].includes(preview.status)} onClick={() => void perform(async () => {
            const closed = await specificationRequest<Preview>(`/previews/${preview.id}/close`, 'POST')
            setPreviews(rows => rows.map(row => row.id === closed.id ? closed : row)); setOpenPreview(null)
          })}>미리보기 종료</Button>
          {openPreview === preview.id && preview.status === 'ready' && Date.parse(preview.expires_at) > Date.now() && <PreviewFrame id={preview.id} />}
        </article>)}
      </div>}
    </>}
    {busy && <Notice title="처리 중입니다." />}
    </div>
  </section>
}
