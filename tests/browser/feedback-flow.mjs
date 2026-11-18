/* Actual platform HTTP/DB; only external Google and LLM responses are scripted by pytest. */
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
import { chromium } from '/runner/node_modules/playwright/index.mjs'
import assert from 'node:assert/strict'

const chunks = []
for await (const chunk of process.stdin) chunks.push(chunk)
const config = JSON.parse(Buffer.concat(chunks).toString())
const server = createServer(async (req, res) => {
  try {
    if (req.url.startsWith('/api/')) {
      const parts = []
      for await (const chunk of req) parts.push(chunk)
      const headers = {}
      for (const key of ['cookie', 'content-type', 'origin', 'x-csrf-token']) if (req.headers[key]) headers[key] = req.headers[key]
      const result = await fetch(config.backend + req.url, { method: req.method, headers,
        body: ['GET', 'HEAD'].includes(req.method) ? undefined : Buffer.concat(parts), redirect: 'manual' })
      res.statusCode = result.status
      res.setHeader('Content-Type', result.headers.get('content-type') ?? 'application/json')
      res.end(Buffer.from(await result.arrayBuffer()))
    } else {
      const path = (req.url.startsWith('/assets/') || req.url.startsWith('/fonts/')) ? req.url : '/index.html'
      const body = await readFile('/app' + path)
      res.setHeader('Content-Type', path.endsWith('.js') ? 'application/javascript' : path.endsWith('.css') ? 'text/css' : path.endsWith('.woff2') ? 'font/woff2' : 'text/html')
      res.end(body)
    }
  } catch { res.statusCode = 502; res.end('test bridge failed') }
}).listen(5173, '127.0.0.1')
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] })
try {
  const context = await browser.newContext()
  await context.addCookies(config.cookies.map(c => ({ ...c, url: 'http://localhost:5173' })))
  const page = await context.newPage()
  page.setDefaultTimeout(30000)
  page.on('pageerror', e => console.error('Page error:', e.message))
  const visualChecks = []
  async function capture(name, menu) {
    await page.locator('.extension-content').waitFor()
    for (const [device, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]]) {
      await page.setViewportSize({ width, height })
      await page.evaluate(() => document.fonts.ready)
      await page.waitForTimeout(500)
      await page.evaluate(() => scrollTo(0, 0))
      if (device === 'mobile') {
        await page.getByRole('button', { name: '메뉴 열기', exact: true }).click()
        assert.equal(await page.locator('.nav a[aria-current="page"]').isVisible(), true)
        await page.keyboard.press('Escape')
        assert.equal(await page.getByRole('button', { name: '메뉴 열기', exact: true }).getAttribute('aria-expanded'), 'false')
      }
      assert.equal(await page.locator('.nav a[aria-current="page"]').textContent(), menu)
      assert.equal(await page.locator('.extension-content button:not(.btn)').count(), 0)
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `${name}/${device}: horizontal overflow`)
      await page.screenshot({ path: `/out/${name}-${device}.png`, fullPage: false })
      visualChecks.push(`${name}/${device}`)
    }
    await page.setViewportSize({ width: 1440, height: 1000 })
  }
  await page.goto('http://localhost:5173/projects')
  await page.getByRole('button', { name: '프로젝트 만들기', exact: true }).waitFor()
  await page.locator('.extension-content ul button').first().click()
  await page.getByLabel('실행 ID', { exact: true }).waitFor()
  await capture('projects', '내 프로젝트')
  await page.goto('http://localhost:5173/feedback')
  await capture('feedback', '고객 메일')
  await page.getByRole('button', { name: '지금 동기화', exact: true }).click()
  await page.waitForTimeout(1500)
  await page.getByRole('button', { name: '수신함 새로고침' }).click()
  await page.getByRole('button', { name: config.subject ?? '화면 이름 변경 요청', exact: true }).click()
  await capture('feedback-mail', '고객 메일')
  await page.getByLabel('요청 원문 인용 (본문에서 그대로 복사)').fill(config.quote ?? '화면 이름을 고객 재고로 바꿔주세요.')
  await page.getByRole('button', { name: '변경 요청 등록', exact: true }).click()
  await page.waitForURL('**/changes/**')
  const changeId = page.url().split('/').at(-1)
  const analyse = page.getByRole('button', { name: '에이전트 영향 분석', exact: true })
  assert.equal(await analyse.isDisabled(), true)
  await page.getByLabel('선택 원문·추가 설명·승인 명세를 외부 AI에 전송해 분석하는 데 동의합니다.').check()
  await analyse.click()
  const approve = page.getByRole('button', { name: '변경안·실행 명세 승인', exact: true })
  if (config.contractChange) {
    await page.getByRole('heading', { name: '명령·계산 변경 인수 검토', exact: true }).waitFor()
    assert.equal(await approve.count(), 0)
    const reviews = page.getByRole('group', { name: /^TC-summary-/ })
    assert.equal(await reviews.count(), 3)
    const normal = reviews.filter({ has: page.locator('legend').filter({ hasText: 'TC-summary-normal' }) })
    await normal.getByText('기대값 변경 입력', { exact: true }).click()
    await normal.getByLabel('TC-summary-normal 기대값 변경', { exact: true }).fill(JSON.stringify([
      { step_index: 1, expect: { kind: 'exact', status: 200, body: { ratio: '0.13' } } }
    ]))
    for (const field of await reviews.all()) {
      await field.getByLabel('검토 근거 (10자 이상)', { exact: true }).fill('1/8=0.125의 half_up 두 자리 0.13 및 경계·실패 조건을 검토했습니다.')
      await field.getByRole('checkbox').check()
    }
    await page.getByRole('button', { name: '검토한 변경안 저장', exact: true }).click()
  }
  await approve.waitFor()
  await capture('change-review', '고객 메일')
  assert.equal(await approve.isDisabled(), true)
  await page.getByLabel('검토 사유', { exact: true }).fill('고객 요청과 화면 변경 범위를 확인했습니다.')
  await page.getByLabel('저장된 변경안을 검토했으며 업무 인수가 별도 필요함을 확인했습니다.').check()
  await approve.click()
  await page.getByRole('button', { name: '승인 변경으로 후보 생성·검증 요청', exact: true }).click()
  await page.getByText('검증: 기본 검증 통과', { exact: false }).waitFor({ timeout: 180000 })
  await page.getByRole('link', { name: '검증 상세·격리 미리보기', exact: true }).click()
  await page.getByRole('button', { name: '브라우저 검증 소스로 미리보기 준비', exact: true }).waitFor()
  await capture('specification', '내 프로젝트')
  await page.getByRole('button', { name: '브라우저 검증 소스로 미리보기 준비', exact: true }).click()
  const open = page.getByRole('button', { name: '미리보기 열기', exact: true })
  await page.waitForFunction(() => [...document.querySelectorAll('button')].some(b => b.textContent === '미리보기 열기' && !b.disabled), null, { timeout: 180000 })
  await open.click()
  await page.frameLocator('iframe').getByRole('button', { name: config.contractChange ? '합성 건수 비율' : '고객 재고', exact: true }).waitFor()
  await page.getByRole('button', { name: '미리보기 종료', exact: true }).click()
  await page.goto('http://localhost:5173/changes/' + changeId)
  await page.getByRole('link', { name: '기존 후보와 비교·채택', exact: true }).click()
  await page.getByRole('button', { name: '변경·검증 비교', exact: true }).click()
  await page.getByLabel('채택 사유 (10~2,000자)').waitFor()
  await page.getByText('명세·설계 산출물 일치: 재생성 결과 일치', { exact: true }).waitFor()
  await page.getByRole('region', { name: '기존 데이터 이전 검토', exact: true }).waitFor()
  await page.getByText('이 후보의 기존 데이터 이전은 아직 실행하지 않았습니다.', { exact: false }).waitFor()
  await capture('candidates', '내 프로젝트')
  await page.getByLabel('채택 사유 (10~2,000자)').fill('변경된 화면과 브라우저 검증을 확인했습니다.')
  await page.getByLabel('업무 인수 조건이 미검증임을 확인하고 구현 기준으로 채택합니다.').check()
  await page.getByRole('button', { name: '검토한 후보 채택', exact: true }).click()
  await page.getByText('구현 기준을 채택하고 검토 이력을 기록했습니다.').waitFor()
  await page.goto('http://localhost:5173/changes/' + changeId)
  await page.getByText('상태: 반영 완료', { exact: false }).waitFor()
  await page.screenshot({ path: '/out/feedback-flow.png', fullPage: true })
  console.log(JSON.stringify({ status: 'passed', visual_checks: visualChecks, change_id: changeId, external_google: 'scripted',
    external_llm: 'scripted', contract_change: !!config.contractChange, platform_api_database: 'real', generated_browser: 'real',
    checks: ['mail sync', 'quoted request', 'external consent gate', 'agent analysis',
      'review approval gate', 'source generation', 'real verification', 'isolated preview',
      'candidate comparison', 'regenerated document consistency', 'data transfer scope visible',
      'adoption linked to change'] }))
} finally {
  await browser.close()
  server.close()
}
