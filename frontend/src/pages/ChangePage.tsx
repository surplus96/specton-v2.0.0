import FeedbackAcceptanceReview from '../ui/FeedbackAcceptanceReview'
import { acceptancePayload, type AcceptanceDraft, type AcceptanceReview } from '../ui/feedbackAcceptance'
import WorkflowStatus from '../ui/WorkflowStatus'
import Button from '../ui/Button'
import Notice from '../ui/Notice'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { specificationRequest as api, type Bundle, type Specification } from '../api/specifications'

type Suggestion = { section: string; object_id: string; field: string; value_json: string; rationale: string }
type Analysis = { summary: string; quotes: string[]; requests: string[]; questions: string[]; unsupported: string[]; suggestions: Suggestion[]; acceptance_review?: { required_case_ids: string[]; pending_case_ids: string[]; reviews: AcceptanceReview[]; expectation_changes: unknown[] } }
type Change = { id: string; project_id: string; title: string; quote: string; instruction: string; state: string; version: number; spec_id: string; spec_version: number;
  analysis: Analysis | null; proposal_hash: string | null; implementation_id: string | null; baseline_stale: boolean;
  verification: { status: string; browser_acceptance: string | null } | null;
  events: { action: string; note: string; created_at: string }[] }
const fields: Record<string, string[]> = { domain_commands: ['before','after','writes','calculations'], domain_calculations: ['filters','windows','max_rows','aggregates','calculations'], domain_operations: ['guards','transition'], commerce: ['cutoff_hour','expiry_days','return_warning_percent','product_note_enabled'], screens: ['name', 'actor_roles', 'empty_state', 'loading_state', 'error_state'], apis: ['actor_roles'], use_cases: ['actor_roles', 'name'], requirements: ['text', 'rationale'] }
const sectionNames: Record<string, string> = { domain_commands: '다중 레코드 명령', domain_calculations: '계산·집계 조회', domain_operations: '도메인 실행 규칙', commerce: '업무 규칙·저장 구조', screens: '화면', apis: 'API', use_cases: '기능', requirements: '요구사항' }
const fieldNames: Record<string, string> = { before: '실행 전 조건', after: '실행 후 조건', writes: '저장 값', calculations: '계산 단계', filters: '조회 조건', windows: '날짜 경계', max_rows: '최대 조회 건수', aggregates: '집계 정책', guards: '조건 검사', transition: '상태 전이', cutoff_hour: '주문 마감 시각', expiry_days: '유통기한 알림 일수', return_warning_percent: '반품 경고 비율', product_note_enabled: '상품 비고란 추가', name: '이름', actor_roles: '허용 역할', empty_state: '빈 화면 안내', loading_state: '로딩 안내', error_state: '오류 안내', text: '요구 내용', rationale: '사유' }

export default function ChangePage() {
  const { changeId } = useParams()
  const root = '/changes/' + changeId
  const [change, setChange] = useState<Change | null>(null)
  const [bundle, setBundle] = useState<Bundle | null>(null)
  const [draft, setDraft] = useState<Analysis | null>(null)
  const [acceptance, setAcceptance] = useState<AcceptanceDraft[]>([])
  const [acceptanceDirty, setAcceptanceDirty] = useState(false)
  const [consent, setConsent] = useState(false)
  const [ack, setAck] = useState(false)
  const [note, setNote] = useState('')
  const [clarification, setClarification] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [reviews, setReviews] = useState<{ version: number; payload_hash: string; created_at: string; payload: { analysis?: Analysis } }[]>([])
  const [enabled, setEnabled] = useState(false)
  function install(row: Change) {
    setChange(row); setAck(false); setClarification(row.instruction)
    const value = row.analysis
    setAcceptanceDirty(false)
    setAcceptance((value?.acceptance_review?.required_case_ids ?? []).map(case_id => {
      const review = value?.acceptance_review?.reviews.find(r => r.case_id === case_id)
      return { case_id, reason: review?.reason ?? '', replacements: JSON.stringify(review?.replacements ?? [], null, 2), confirmed: !!review }
    }))
    setDraft(value ? { summary: value.summary, quotes: value.quotes, requests: value.requests, questions: value.questions, unsupported: value.unsupported, suggestions: value.suggestions }
      : { summary: row.title, quotes: [row.quote], requests: [row.title], questions: [], unsupported: [], suggestions: [] })
  }
  useEffect(() => {
    let active = true
    async function load() {
      try {
        const [row, status] = await Promise.all([api<Change>(root), api<{ analysis_enabled: boolean }>('/integrations/gmail')])
        const spec = await api<Specification>('/specs/' + row.spec_id + '/versions/' + row.spec_version)
        if (active) { install(row); setBundle(spec.bundle); setEnabled(status.analysis_enabled) }
      } catch (e) { if (active) setError(e instanceof Error ? e.message : '조회 실패') }
    }
    void load()
    return () => { active = false }
  }, [root])
  useEffect(() => {
    if (change?.state !== 'analysing' && change?.state !== 'validating') return
    let active = true
    const timer = setInterval(() => {
      api<Change>(root).then(row => { if (active) { if (row.state !== change.state) install(row); else setChange(row) } })
        .catch(e => { if (active) setError(e instanceof Error ? e.message : '조회 실패') })
    }, 3000)
    return () => { active = false; clearInterval(timer) }
  }, [root, change?.state])
  async function perform(action: () => Promise<void>) {
    setBusy(true); setError('')
    try { await action() } catch (e) { setError(e instanceof Error ? e.message : '처리 실패') }
    finally { setBusy(false) }
  }
  const saved = change?.analysis
  const dirty = acceptanceDirty || !!saved && JSON.stringify(draft) !== JSON.stringify({
    summary: saved.summary, quotes: saved.quotes, requests: saved.requests,
    questions: saved.questions, unsupported: saved.unsupported, suggestions: saved.suggestions,
  })
  const editable = change && ['received', 'needs_input', 'failed', 'awaiting_decision'].includes(change.state)
  function objects(section: string): { id: string; name?: string; text?: string; path?: string }[] {
    if (section === 'domain_commands') return bundle?.domain?.commands?.map(o => ({id:o.api_id,name:'명령'})) ?? []
    if (section === 'domain_calculations') return bundle?.domain?.calculations?.map(o => ({id:o.api_id,name:'집계'})) ?? []
    if (section === 'domain_operations') return bundle?.domain?.operations.map(o=>({id:o.api_id,name:o.action+' · '+o.table_id}))??[]
    if (section === 'commerce') return bundle?.commerce ? [{id:bundle.commerce.profile,name:'기본 업무 정책'}] : []
    if (!bundle) return []
    return bundle[section as 'screens' | 'apis' | 'use_cases' | 'requirements']
  }
  function original(section: string, id: string, field: string): string {
    const group = section === 'domain_commands' ? bundle?.domain?.commands : section === 'domain_calculations' ? bundle?.domain?.calculations : section === 'domain_operations' ? bundle?.domain?.operations : undefined
    const object = group?.find(o => o.api_id === id)
    return JSON.stringify(object ? (object as unknown as Record<string, unknown>)[field] : '', null, 2)
  }
  function update(index: number, value: Partial<Suggestion>) {
    setAcceptance(a => a.map(r => ({ ...r, confirmed: false }))); setAcceptanceDirty(true)
    if (draft) setDraft({ ...draft, suggestions: draft.suggestions.map((s, i) => i === index ? { ...s, ...value } : s) })
  }
  return <section className="screen extension-page">
    <Link to="/feedback">고객 메일</Link>
    <header className="screen-head"><h1 className="hero">{change?.title ?? '변경 요청'}</h1></header>
    <div className="panel extension-content">
    {error && <Notice kind="error" title={error} />}
    {!change && !error && <Notice title="변경 요청을 불러오는 중입니다." />}
    {change && <>
      <p>상태: <WorkflowStatus state={change.state} /> · 검토 버전 {change.version}</p>
      {change.baseline_stale && change.state !== 'applied' && <Notice kind="warning" title="현재 채택 기준이 바뀌었습니다." >최신 기준에서 변경 요청을 다시 등록하세요.</Notice>}
      <blockquote style={{ whiteSpace: 'pre-wrap' }}>{change.quote}</blockquote>
      {change.instruction && <p>검토 설명: {change.instruction}</p>}
      <p>승인 후 반영 범위: 기존 화면·권한·기록 조건과 명령·계산·집계 정책. 명령의 대상·쓰기 컬럼·조건 개수와 집계의 테이블·필터 출처는 보존합니다. 새 API·DB 구조와 새로운 업무 동작은 추가 설계가 필요합니다.</p>
      {editable && <p><label><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} />선택 원문·추가 설명·승인 명세를 외부 AI에 전송해 분석하는 데 동의합니다.</label>{' '}
        <Button variant="primary" type="button" disabled={busy || !enabled || !consent || change.baseline_stale} onClick={() => void perform(async () => {
          await api(root + '/analyse', 'POST', { expected_version: change.version, consent_external_analysis: true })
          install(await api<Change>(root))
        })}>에이전트 영향 분석</Button>{!enabled && ' 서버에서 외부 분석 설정을 활성화해야 합니다.'}</p>}
      {editable && <details><summary>추가 질문에 답변·검토 설명 보완</summary>
        <p>답변을 저장하면 이전 변경안과 승인 해시를 초기화합니다. 다시 분석하거나 변경안을 작성하세요.</p>
        <textarea aria-label="추가 질문 답변·검토 설명" maxLength={4000} rows={4} style={{ width: '100%' }} value={clarification} onChange={e => setClarification(e.target.value)} />
        <Button variant="primary" type="button" disabled={busy || !clarification.trim() || change.baseline_stale} onClick={() => void perform(async () => install(await api<Change>(root + '/clarification', 'PATCH', { expected_version: change.version, instruction: clarification })))}>답변 저장</Button>
      </details>}
      {draft && <article className="panel extension-card">
        <h2>변경안 검토</h2>
        <p>영향을 완전히 추적하지 못한 부분은 별도 확인이 필요하며, 생성 앱 전체 고정 시나리오를 다시 검증합니다. 업무 인수 조건은 자동 완료되지 않습니다.</p>
        <label>분석 요약 <textarea disabled={!editable || busy} value={draft.summary} onChange={e => setDraft({ ...draft, summary: e.target.value })} style={{ width: '100%' }} /></label>
        <ul>{draft.requests.map((r, i) => <li key={i}>{r}</li>)}</ul>
        <p>추가 질문: {draft.questions.join(' / ') || '없음'}</p>
        <p>추가 설계 필요: {draft.unsupported.join(' / ') || '없음'}</p>
        {draft.suggestions.map((s, i) => <fieldset key={i} disabled={!editable || busy} style={{ margin: '1rem 0' }}>
          <legend>변경 {i + 1}</legend>
          <label>구분 <select value={s.section} onChange={e => update(i, { section: e.target.value, object_id: objects(e.target.value)[0]?.id ?? '', field: fields[e.target.value][0], value_json: original(e.target.value, objects(e.target.value)[0]?.id ?? '', fields[e.target.value][0]) })}>{Object.keys(fields).map(k => <option key={k} value={k}>{sectionNames[k]}</option>)}</select></label>{' '}
          <label>대상 <select value={s.object_id} onChange={e => update(i, { object_id: e.target.value, value_json: original(s.section, e.target.value, s.field) })}>{objects(s.section).map(o => <option key={o.id} value={o.id}>{o.name ?? o.path ?? o.text ?? o.id} · {o.id}</option>)}</select></label>{' '}
          <label>변경 항목 <select value={s.field} onChange={e => update(i, { field: e.target.value, value_json: s.section.startsWith('domain_') ? original(s.section, s.object_id, e.target.value) : e.target.value === 'actor_roles' ? '[]' : e.target.value === 'product_note_enabled' ? 'true' : s.section === 'commerce' ? '17' : '""' })}>{fields[s.section]?.map(k => <option key={k} value={k}>{fieldNames[k]}</option>)}</select></label>
          {s.field === 'actor_roles' ? <p>{bundle?.roles.map(role => {
            let selected: string[] = []
            try { selected = JSON.parse(s.value_json) as string[] } catch { /* Server validates. */ }
            return <label key={role.id}><input type="checkbox" checked={selected.includes(role.id)} onChange={e => update(i, { value_json: JSON.stringify(e.target.checked ? [...selected, role.id] : selected.filter(v => v !== role.id)) })} />{role.name} </label>
          })}</p> : s.section.startsWith('domain_') ? <p><label>실행 규칙 JSON<textarea rows={6} value={s.value_json} onChange={e=>update(i,{value_json:e.target.value})}/></label></p> : s.section === 'commerce' ? <p><label>수정할 값 {s.field === 'product_note_enabled' ? <select aria-label="수정할 값" value={s.value_json} onChange={e=>update(i,{value_json:e.target.value})}><option value="true">추가</option><option value="false">제외</option></select> : <input type="number" min={s.field==='expiry_days'?1:0} max={s.field==='cutoff_hour'?23:s.field==='expiry_days'?365:100} value={s.value_json} onChange={e=>update(i,{value_json:e.target.value})}/>}</label><span>새 파생 설계와 빈 격리 DB에서 검증합니다.</span></p> : <p><label>수정할 내용 <input value={(() => { try { return String(JSON.parse(s.value_json)) } catch { return s.value_json } })()} onChange={e => update(i, { value_json: JSON.stringify(e.target.value) })} /></label></p>}
          {s.section.startsWith('domain_') && <details><summary>기존 계약 값</summary><pre style={{whiteSpace:'pre-wrap'}}>{original(s.section, s.object_id, s.field)}</pre></details>}
          <p><label>변경 사유 <input value={s.rationale} onChange={e => update(i, { rationale: e.target.value })} /></label></p>
          <Button variant="danger" type="button" onClick={() => setDraft({ ...draft, suggestions: draft.suggestions.filter((_, n) => n !== i) })}>이 변경 제외</Button>
        </fieldset>)}
        <FeedbackAcceptanceReview bundle={bundle} draft={acceptance} disabled={!editable || busy} onChange={value => { setAcceptance(value); setAcceptanceDirty(true) }} />
        {!!saved?.acceptance_review?.expectation_changes.length && <details><summary>저장된 기대값 변경 전·후</summary><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(saved.acceptance_review.expectation_changes, null, 2)}</pre></details>}
        {editable && <>
          <Button variant="secondary" type="button" disabled={busy} onClick={() => setDraft({ ...draft, suggestions: [...draft.suggestions, { section: 'screens', object_id: bundle?.screens[0]?.id ?? '', field: 'name', value_json: '""', rationale: '' }] })}>변경 항목 추가</Button>{' '}
          <Button variant="primary" type="button" disabled={busy || change.baseline_stale} onClick={() => void perform(async () => install(await api<Change>(root + '/proposal', 'PUT', { expected_version: change.version, analysis: draft, acceptance_reviews: acceptancePayload(acceptance) })))}>검토한 변경안 저장</Button>
          <p>수정한 내용은 저장한 후 승인하세요. 첫 저장 후 명령·계산 인수 검토 목록이 표시됩니다. 미해결 질문·지원 밖 변경·미검토 인수 사례가 있으면 승인이 차단됩니다.</p>
        </>}
      </article>}
      {change.state === 'awaiting_decision' && <>
        <h2>변경안 승인</h2>
        <p>승인은 저장된 변경안과 그 실행 명세에 적용됩니다. 입력 중인 수정은 먼저 저장하세요.</p>
        <label>검토 사유 <textarea minLength={10} maxLength={2000} value={note} onChange={e => setNote(e.target.value)} style={{ width: '100%' }} /></label>
        <p><label><input type="checkbox" checked={ack} onChange={e => setAck(e.target.checked)} />저장된 변경안을 검토했으며 업무 인수가 별도 필요함을 확인했습니다.</label></p>
        {(['approve', 'reject'] as const).map(decision => <Button variant={decision === 'approve' ? 'primary' : 'danger'} type="button" key={decision} disabled={busy || dirty || !ack || note.trim().length < 10 || change.baseline_stale} onClick={() => void perform(async () => install(await api<Change>(root + '/decide', 'POST', { expected_version: change.version, target_hash: change.proposal_hash, decision, note, acknowledge_unverified_acceptance: true })))}>{decision === 'approve' ? '변경안·실행 명세 승인' : '변경안 반려'}</Button>)}
      </>}
      {change.state === 'approved' && <Button variant="primary" type="button" disabled={busy || change.baseline_stale} onClick={() => void perform(async () => install(await api<Change>(root + '/implement', 'POST', { expected_version: change.version })))}>승인 변경으로 후보 생성·검증 요청</Button>}
      {change.implementation_id && <article className="panel extension-card">
        <h2>수정 후보 검증</h2>
        <p>검증: <WorkflowStatus state={change.verification?.status ?? 'queued'} /> · 브라우저: <WorkflowStatus state={change.verification?.browser_acceptance} /></p>
        <p><Link to={'/specifications/' + change.spec_id + '?implementation=' + change.implementation_id}>검증 상세·격리 미리보기</Link>{' · '}<Link to={'/projects/' + change.project_id + '/candidates'}>기존 후보와 비교·채택</Link></p>
      </article>}
      <details><summary>이전 변경안 검토 기록</summary>
        <Button variant="secondary" type="button" disabled={busy} onClick={() => void perform(async () => setReviews(await api(root + '/reviews')))}>검토 기록 조회</Button>
        {reviews.map(r => <article className="panel extension-card" key={r.version}><h3>검토 버전 {r.version}</h3><p>{new Date(r.created_at).toLocaleString()}</p>
          <p>{r.payload.analysis?.summary ?? '원문 삭제로 내용이 제거됐습니다.'}</p>
          {r.payload.analysis?.acceptance_review && <details><summary>인수 검토·기대값 변경 이력</summary><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(r.payload.analysis.acceptance_review, null, 2)}</pre></details>}
          <ul>{r.payload.analysis?.suggestions.map((s, i) => <li key={i}>{sectionNames[s.section]} · {s.object_id} · {fieldNames[s.field]} → {s.value_json} · {s.rationale}</li>)}</ul>
        </article>)}
      </details>
      <h2>처리 이력</h2><ol>{change.events.map((e, i) => <li key={i}>{e.action} · {new Date(e.created_at).toLocaleString()}<p>{e.note}</p></li>)}</ol>
      <Button variant="secondary" type="button" disabled={busy} onClick={() => void perform(async () => install(await api<Change>(root)))}>상태 새로고침</Button>
    </>}
    {busy && <Notice title="처리 중입니다." />}
    </div>
  </section>
}
