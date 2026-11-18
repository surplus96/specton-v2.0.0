import type { Bundle, Specification } from '../api/specifications'

export type TestPreparation = {
  format: 'specton-e2e-preparation-v1'; base_spec_hash: string; bundle: Bundle
  scope: { requirement_id: string; disposition: 'included' | 'deferred'; rationale: string }[]
  answer_proposals: { question_id: string; answer: string }[]
}
function stable(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(stable).join(',') + ']'
  if (value !== null && typeof value === 'object') return '{' + Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([k, v]) => JSON.stringify(k) + ':' + stable(v)).join(',') + '}'
  return JSON.stringify(value)
}
export function readPreparation(text: string, current: Specification): TestPreparation {
  if (text.length > 2_000_000) throw new Error('준비 파일은 2MB 이하만 불러올 수 있습니다.')
  const value = JSON.parse(text) as TestPreparation
  if (!value || value.format !== 'specton-e2e-preparation-v1' || !value.bundle || !Array.isArray(value.scope) || !Array.isArray(value.answer_proposals)) throw new Error('E2E 준비 파일 형식을 확인하세요.')
  if (value.base_spec_hash !== current.readiness.spec_hash) throw new Error('준비 파일의 기준 버전이 현재 명세와 다릅니다. 최신 명세로 다시 준비하세요.')
  for (const key of ['spec_id', 'spec_version', 'parent_spec_hash', 'baseline', 'template'] as const) {
    if (stable(value.bundle[key]) !== stable(current.bundle[key])) throw new Error('명세 ID·버전·승인 설계 출처를 바꿀 수 없습니다.')
  }
  const before = current.bundle
  const after = value.bundle
  if (!Array.isArray(after.requirements) || !Array.isArray(after.questions) || !Array.isArray(after.acceptance_cases)) throw new Error('명세의 요구·질문·인수 사례가 필요합니다.')
  const requirements = new Map(after.requirements.map(r => [r.id, r]))
  const scope = new Map(value.scope.map(r => [r.requirement_id, r]))
  if (requirements.size !== before.requirements.length || requirements.size !== after.requirements.length || scope.size !== requirements.size || scope.size !== value.scope.length) throw new Error('원본 요구와 포함·제외 범위를 모두 보존하세요.')
  for (const r of before.requirements) {
    const target = requirements.get(r.id), item = scope.get(r.id)
    if (!target || !item || !['included', 'deferred'].includes(item.disposition) || !item.rationale?.trim()) throw new Error('요구별 시험 범위와 사유를 확인하세요.')
    for (const key of ['text', 'legacy_id', 'kind', 'origin'] as const) if (target[key] !== r[key]) throw new Error('원본 요구 내용과 출처를 보존하세요.')
    if ((target.priority === "Won't") !== (item.disposition === 'deferred') || target.rationale !== item.rationale) throw new Error('명세의 제외 범위와 사유가 준비 파일과 다릅니다.')
  }
  const questions = new Map(after.questions.map(q => [q.id, q]))
  if (questions.size !== before.questions.length || questions.size !== after.questions.length) throw new Error('원본 질문을 보존하세요.')
  for (const q of before.questions) {
    const target = questions.get(q.id)
    if (!target || stable(q.req_ids) !== stable(target.req_ids) || q.question !== target.question || q.answer !== target.answer) throw new Error('기존 질문·답변은 그대로 유지하고 새 가정은 별도로 검토하세요.')
  }
  const answers = new Map(value.answer_proposals.map(a => [a.question_id, a.answer]))
  const pending = before.questions.filter(q => q.answer === null)
  if (answers.size !== pending.length || answers.size !== value.answer_proposals.length || pending.some(q => !answers.get(q.id)?.trim())) throw new Error('미답변 질문별 검토 가정을 확인하세요.')
  for (const test of before.acceptance_cases) {
    if (test.execution && stable(test) !== stable(after.acceptance_cases.find(c => c.id === test.id))) throw new Error('기존 실행 인수 사례·기대값을 덮어쓸 수 없습니다.')
  }
  return value
}
export function preparationDraft(preparation: TestPreparation, acceptAssumptions: boolean): Bundle {
  const bundle = structuredClone(preparation.bundle)
  if (acceptAssumptions) {
    const proposed = new Map(preparation.answer_proposals.map(a => [a.question_id, a.answer]))
    bundle.questions = bundle.questions.map(q => q.answer === null && proposed.has(q.id) ? { ...q, answer: proposed.get(q.id)! } : q)
  }
  return bundle
}
