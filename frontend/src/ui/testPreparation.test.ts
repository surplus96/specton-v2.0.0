import { describe, expect, it } from 'vitest'
import type { Specification } from '../api/specifications'
import { readPreparation, preparationDraft, type TestPreparation } from './testPreparation'

function fixture() {
  const current = {
    bundle: { spec_id: 'synthetic-spec', spec_version: 1, parent_spec_hash: null,
      baseline: { project_id: 'test', model_hash: 'approved-model' }, template: 'generic',
      requirements: [{ id: 'REQ-test', legacy_id: 'REQ-01', kind: 'FR', origin: 'design', text: '명시한 수량을 조회한다.', priority: 'Must', rationale: '초기 제안' }],
      questions: [{ id: 'QUESTION-test', req_ids: ['REQ-test'], question: '시험 범위를 확인하세요.', answer: null }],
      acceptance_cases: [{ id: 'TC-existing', execution: { steps: [{ expect: { total: '12.00' } }] } }],
    }, readiness: { spec_hash: 'base-hash' },
  } as unknown as Specification
  const packet = { format: 'specton-e2e-preparation-v1', base_spec_hash: 'base-hash', bundle: structuredClone(current.bundle),
    scope: [{ requirement_id: 'REQ-test', disposition: 'included', rationale: '단일 수량 조회 시험' }],
    answer_proposals: [{ question_id: 'QUESTION-test', answer: '고정 합성 자료로 단일 조회를 시험합니다.' }],
  } as TestPreparation
  packet.bundle.requirements[0].rationale = packet.scope[0].rationale
  return { current, packet }
}

describe('E2E preparation import', () => {
  it('leaves answers pending until the owner explicitly accepts proposed assumptions', () => {
    const { current, packet } = fixture()
    const checked = readPreparation(JSON.stringify(packet), current)
    expect(preparationDraft(checked, false).questions[0].answer).toBeNull()
    expect(preparationDraft(checked, true).questions[0].answer).toContain('고정 합성')
    expect(packet.bundle.questions[0].answer).toBeNull()
    expect(current.bundle.questions[0].answer).toBeNull()
    expect(preparationDraft(checked, true).spec_version).toBe(1)
  })
  it.each(['hash', 'version', 'baseline', 'requirements', 'text', 'scope', 'rationale', 'answers', 'question', 'proposal', 'oracle'])(
    'rejects stale or silently altered %s', kind => {
      const { current, packet } = fixture()
      if (kind === 'hash') packet.base_spec_hash = 'old-hash'
      if (kind === 'version') packet.bundle.spec_version = 2
      if (kind === 'baseline') packet.bundle.baseline.model_hash = 'other-model'
      if (kind === 'requirements') packet.bundle.requirements = []
      if (kind === 'text') packet.bundle.requirements[0].text = '축소한 요구'
      if (kind === 'scope') packet.scope[0].disposition = 'deferred'
      if (kind === 'rationale') packet.scope[0].rationale = '명세와 다른 범위 설명'
      if (kind === 'answers') packet.bundle.questions[0].answer = '사용자에게 묻지 않고 채운 답변'
      if (kind === 'question') packet.bundle.questions[0].question = '원본과 다른 질문'
      if (kind === 'proposal') packet.answer_proposals = []
      if (kind === 'oracle') packet.bundle.acceptance_cases = []
      expect(() => readPreparation(JSON.stringify(packet), current)).toThrow()
    },
  )
  it('rejects malformed or oversized files', () => {
    const { current } = fixture()
    for (const text of ['null', '{}', '{', ' '.repeat(2_000_001)]) expect(() => readPreparation(text, current)).toThrow()
  })
})
