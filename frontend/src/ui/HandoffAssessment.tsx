import { useEffect, useState } from 'react'
import { getHandoff } from '../api/client'
import type { HandoffReport } from '../api/types'
import Button from './Button'
import Notice from './Notice'

const status = { passed: '해당 검사 통과', blocked: '보완 필요', review_required: '검토 필요', not_run: '근거 미확인' }
const category: Record<string, string> = { normal: '정상', boundary: '경계', failure: '실패', concurrency: '동시 요청', security: '접근 통제', recovery: '복구' }

export default function HandoffAssessment({ path }: { path: string }) {
  const [report, setReport] = useState<HandoffReport | null>(null)
  const [error, setError] = useState('')
  const [requested, setRequested] = useState(0)
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!requested) return
    let active = true
    setBusy(true); setError(''); setReport(null)
    getHandoff(path).then(value => { if (active) setReport(value) })
      .catch(() => { if (active) setError('준비도 점검을 불러오지 못했습니다. 저장된 명세와 승인 설계 출처를 확인하고 다시 시도하세요.') })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [path, requested])
  function download() {
    if (!report) return
    const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url; link.download = `specton-handoff-${report.spec_id}-v${report.spec_version}.json`
    link.click(); window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <section className="extension-card" style={{ overflowWrap: 'anywhere' }} aria-label="수주·납품 준비도">
    <h2>수주·납품 준비도와 업무 계약</h2>
    <p>저장된 명세의 요구별 계약과 해당 버전 소스의 검증 근거를 확인합니다. 편집 중인 내용은 저장 후 점검하세요.</p>
    <Button disabled={busy} onClick={() => setRequested(v => v + 1)}>{busy ? '점검 중' : '수주·납품 준비도 점검'}</Button>
    {error && <Notice kind="error" title={error} />}
    {report && <>
      <p><strong>{report.conclusion === 'contract_work_required' ? '업무 계약 보완이 필요합니다.' : '기술 검토 후 고객 업무 인수가 필요합니다.'}</strong></p>
      <p>저장 버전 {report.spec_version} · 포함 {report.included_requirements}건 · 제외 {report.excluded_requirements}건 · 확장 표현 검토 {report.extension_hint_requirements}건</p>
      {!report.is_latest && <Notice kind="warning" title="과거 설계 또는 명세의 점검입니다. 최신 버전에서 다시 확인하세요." />}
      <p>{report.notice}</p>
      <ul>{report.gates.map(g => <li key={g.id}><strong>{g.name} · {status[g.status]}</strong><p>{g.detail}</p></li>)}</ul>
      <Button onClick={download}>점검·업무 계약 초안 JSON 내려받기</Button>
      <p>아래 항목은 구현 전에 확정할 계약 초안입니다. 포함/제외 사유를 검토하고, 지원하는 규칙은 실행 명세와 인수 사례에 반영하여 새 버전으로 저장·승인하세요. 미지원 동작은 생성기 확장이 필요합니다.</p>
      {report.contracts.map(c => <details key={c.requirement_id}>
        <summary>{c.requirement_id} · {c.scope === 'excluded' ? '제외 범위 검토' : '계약 보완'} · {c.text}</summary>
        <p>{c.priority} · {c.kind} · 범위 사유: {c.rationale}</p>
        <p>업무 연결 검토: {c.coverage_explanation}</p>
        <p>명시적 API 사례 {c.executable_case_ids.length}건 · 보완할 사례 유형: {c.missing_api_case_categories.map(v => category[v] ?? v).join(', ') || '분류상 누락 없음 — 내용 검토 필요'}</p>
        {c.topics.map(t => <section key={t.capability_id}>
          <h3>{t.name}</h3>
          {t.detection === 'text_hint' && <p>확인한 표현: {t.matched_expressions.join(', ')}. 실제 적용 여부를 검토하세요.</p>}
          <ol>{t.decisions_required.map(d => <li key={d}>{d}</li>)}</ol>
          <h4>인수 조건 초안 · 미실행</h4>
          <ul>{t.acceptance_outline.map((a, i) => <li key={i}><strong>{category[a.category]}</strong>: {a.given} → {a.when} → {a.expected}</li>)}</ul>
        </section>)}
        <details><summary>설계·실행 연결 ID</summary>
          <p>역할: {c.role_ids.join(', ') || '미연결'}</p><p>API: {c.api_ids.join(', ') || '미연결'}</p>
          <p>엔티티: {c.entity_ids.join(', ') || '미연결'}</p><p>테이블: {c.table_ids.join(', ') || '미연결'}</p>
          <p>미답변 질문: {c.unresolved_question_ids.join(', ') || '없음'}</p>
        </details>
      </details>)}
    </>}
  </section>
}
