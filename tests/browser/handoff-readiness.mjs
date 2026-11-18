/* Actual Chromium/platform UI; saved-spec and report responses are fixed fixtures.
 * The separate PostgreSQL API tests check ownership, versions and sealed evidence.
 */
import {createServer} from 'node:http'
import {readFile,writeFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
import {chromium} from '/runner/node_modules/playwright/index.mjs'
const spec=JSON.parse(await readFile('/out/view.json','utf8'))
const report=JSON.parse(await readFile('/out/readiness.json','utf8'))
const server=createServer(async(req,res)=>{
 const path=req.url.startsWith('/assets/')||req.url.startsWith('/fonts/')?req.url:'/index.html'
 try {
  res.setHeader('Content-Type',path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':path.endsWith('.woff2')?'font/woff2':'text/html')
  res.end(await readFile('/app'+path))
 } catch {res.statusCode=404;res.end()}
}).listen(8080,'127.0.0.1')
const browser=await chromium.launch({args:['--no-sandbox']})
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 let reads=0,mutations=0,fail=false
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),url=new URL(req.url())
  if(req.method()!=='GET')mutations++
  if(url.pathname.endsWith('/handoff')){
   reads++
   if(fail)return route.fulfill({status:500,json:{error:{message:'test failure'}}})
   const version=Number(url.searchParams.get('version'))
   return route.fulfill({json:{...report,spec_version:version,is_latest:version===2}})
  }
  if(url.pathname.endsWith('/versions/1'))return route.fulfill({json:{...spec,bundle:{...spec.bundle,spec_version:1}}})
  return route.fulfill({json:spec})
 })
 await page.goto('http://127.0.0.1:8080/specifications/'+spec.bundle.spec_id)
 const panel=page.getByRole('region',{name:'수주·납품 준비도',exact:true})
 assert.equal(reads,0)
 await panel.getByRole('button',{name:'수주·납품 준비도 점검',exact:true}).click()
 await panel.getByText('업무 계약 보완이 필요합니다.',{exact:true}).waitFor()
 assert.equal(reads,1)
 assert.equal(await panel.locator(':scope > details').count(),report.contracts.length)
 const download=page.waitForEvent('download')
 await panel.getByRole('button',{name:'점검·업무 계약 초안 JSON 내려받기'}).click()
 const downloaded=await download;await downloaded.saveAs('/out/download.json')
 const saved=JSON.parse(await readFile('/out/download.json','utf8'))
 assert.equal(saved.spec_hash,report.spec_hash)
 assert.equal(saved.business_acceptance,'not_run')
 await panel.locator(':scope > details').first().locator('summary').first().click()
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:1000})
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),`overflow at ${width}`)
  await panel.screenshot({path:`/out/review-${width}.png`})
 }
 await page.setViewportSize({width:1440,height:1000})
 fail=true
 await panel.getByRole('button',{name:'수주·납품 준비도 점검',exact:true}).click()
 await panel.getByRole('alert').waitFor()
 assert.equal(await panel.getByRole('button',{name:'점검·업무 계약 초안 JSON 내려받기'}).count(),0)
 fail=false
 await panel.getByRole('button',{name:'수주·납품 준비도 점검',exact:true}).click()
 await panel.getByText('업무 계약 보완이 필요합니다.',{exact:true}).waitFor()
 await page.getByLabel('저장 이력').selectOption('1')
 await page.getByText('과거 버전은 읽기 전용입니다. 최신 버전에서 보완하세요.',{exact:true}).waitFor()
 assert.equal(await panel.count(),1)
 await panel.getByRole('button',{name:'점검·업무 계약 초안 JSON 내려받기'}).waitFor({state:'detached'})
 assert.equal(await panel.getByRole('button',{name:'점검·업무 계약 초안 JSON 내려받기'}).count(),0)
 await panel.getByRole('button',{name:'수주·납품 준비도 점검',exact:true}).click()
 await panel.getByText('과거 설계 또는 명세의 점검입니다. 최신 버전에서 다시 확인하세요.',{exact:true}).waitFor()
 assert.equal(mutations,0)
 await writeFile('/out/browser-report.json',JSON.stringify({status:'passed',checks:['manual_read_only_review','contract_links_and_scope','json_export_hash','failure_clears_old_result_and_retry','version_change_clears_old_result','desktop_mobile'],reads,mutations,backend:'fixed fixtures; ownership/evidence covered by PostgreSQL integration tests'},null,2))
 console.log('PASS: read-only handoff review, contract draft, JSON, failures/retry, version change, responsive UI')
}finally{await browser.close();server.close()}
