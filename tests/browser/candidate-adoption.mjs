/* Built platform UI interaction test. API fixtures exercise UI only; DB tests cover authorization. */
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { chromium } from '/runner/node_modules/playwright/index.mjs'
import assert from 'node:assert/strict'

const server = createServer(async (req, res) => {
  const path = req.url.startsWith('/assets/') ? req.url : '/index.html'
  const body = await readFile('/app' + path)
  res.setHeader('Content-Type', path.endsWith('.js') ? 'application/javascript' : path.endsWith('.css') ? 'text/css' : 'text/html')
  res.end(body)
}).listen(8080, '127.0.0.1')
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] })
try {
  const page = await browser.newPage()
  const adoption = { id: 'adopted', sequence: 1, implementation_id: 'candidate', rationale: '검증 근거를 검토하여 기준으로 채택합니다.', created_at: new Date().toISOString() }
  let adopted = false, eligible = false
  const submissions = []
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    let body = {}
    if (path.endsWith('/candidates')) body = { items: [{ id: 'candidate', spec_version: 2, design_version: 1, verification_status: 'smoke_passed' }], current_adoption: adopted ? adoption : null }
    else if (path.endsWith('/implementation-baseline')) body = { history: adopted ? [adoption] : [] }
    else if (path.endsWith('/comparison')) body = {
      comparison_hash: 'c'.repeat(64), current_adoption: null, eligible, reasons: eligible ? [] : ['검증 결과가 없습니다.'],
      latest_verification_id: 'verification', latest_verification_status: eligible ? 'smoke_passed' : 'queued',
      ddl_changed: true, files: [{ path: 'backend/approved.sql', change: 'modified', before_hash: 'a', after_hash: 'b', diff: '-old\n+new', truncated: false }],
      semantic: { requirements: { added: ['R1'], removed: [], modified: [] } },
      verification: eligible ? { checks: [{ status: 'passed' }], browser_checks: [{ status: 'passed' }], report_hash: 'r' } : null,
      unverified_acceptance_count: 1, unverified_acceptance: [{ id: 'AC1', req_ids: ['R1'], tier: 'browser' }],
    }
    else if (path.endsWith('/adoptions')) {
      submissions.push(request.postDataJSON()); adopted = true; body = adoption
    }
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) })
  })
  await page.goto('http://127.0.0.1:8080/projects/project/candidates')
  const compare = page.getByRole('button', { name: '변경·검증 비교' })
  await compare.click()
  const adopt = page.getByRole('button', { name: '검토한 후보 채택' })
  await adopt.waitFor()
  assert.equal(await adopt.isDisabled(), true)
  eligible = true
  await compare.click()
  await page.getByText('최근 검증: smoke_passed', { exact: false }).waitFor()
  assert.equal(await adopt.isDisabled(), true)
  await page.getByRole('textbox').fill(adoption.rationale)
  assert.equal(await adopt.isDisabled(), true)
  await page.getByRole('checkbox').check()
  assert.equal(await adopt.isEnabled(), true)
  await adopt.click()
  await page.getByText('구현 기준을 채택하고 검토 이력을 기록했습니다.').waitFor()
  assert.equal(submissions.length, 1)
  assert.equal(submissions[0].expected_current_id, null)
  assert.equal(submissions[0].acknowledge_unverified_acceptance, true)
  assert.equal(submissions[0].comparison_hash, 'c'.repeat(64))
  assert.match(submissions[0].request_key, /^[0-9a-f-]{36}$/)
  console.log('PASS: failed evidence gate, rationale and acknowledgement gates, adoption payload, history refresh')
} finally {
  await browser.close()
  server.close()
}
