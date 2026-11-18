/* UI interaction using synthetic API responses; no external AI request or user data. */
import {createServer} from 'node:http'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
import {chromium} from '/runner/node_modules/playwright/index.mjs'
const initial=JSON.parse(await readFile('/out/spec-view.json','utf8'))
const server=createServer(async(req,res)=>{
  const path=req.url.startsWith('/assets/')||req.url.startsWith('/fonts/')?req.url:'/index.html'
  res.setHeader('Content-Type',path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':path.endsWith('.woff2')?'font/woff2':'text/html')
  res.end(await readFile('/app'+path))
}).listen(8080,'127.0.0.1')
const browser=await chromium.launch({args:['--no-sandbox']})
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 let saved=structuredClone(initial), calls=0, demoCalls=0, saves=0, businessCalls=0
 const specId=saved.bundle.spec_id
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(), path=new URL(req.url()).pathname
  if(path.endsWith('/business')) {
   const body=req.postDataJSON();assert.equal(body.acknowledge_demo_defaults,true)
   businessCalls++;const bundle=structuredClone(saved.bundle);bundle.screens[0].name='주문·반품 시연'
   await route.fulfill({json:{bundle,readiness:saved.readiness,generation_ready:true,generation_issue:null,calls:[]}})
  } else if(path.endsWith('/storage-catalog')) {
   await route.fulfill({json:{normalized:{tables:[{id:'TBL-demo',name:'상품',primary_key:['COL-key'],columns:[{data_type:'varchar'},{data_type:'numeric'}]}],foreign_keys:[]}}})
  } else if(path.endsWith('/demo')) {
   const body=req.postDataJSON();assert.equal(body.acknowledge_demo_scope,true)
   assert.equal(body.table_id,'TBL-demo');assert.equal(body.screen_name,'상품 기준정보 관리')
   assert.equal(body.expected_version,saved.bundle.spec_version);demoCalls++
   const bundle=structuredClone(saved.bundle);bundle.screens[0].name=body.screen_name
   await route.fulfill({json:{bundle,readiness:saved.readiness,generation_ready:true,generation_issue:null,calls:[]}})
  } else if(path.endsWith('/complete')) {
   const body=req.postDataJSON(); assert.equal(body.consent_external_analysis,true)
   assert.equal(body.spec_hash,saved.readiness.spec_hash);calls++
   const bundle=structuredClone(saved.bundle);bundle.screens[0].name='고객 상품 관리'
   await route.fulfill({json:{bundle,readiness:saved.readiness,generation_ready:true,generation_issue:null,calls:[]}})
  } else if(req.method()==='PATCH') {
   saves++;saved.bundle=req.postDataJSON().bundle;saved.bundle.spec_version++
   saved.versions.push(saved.bundle.spec_version)
   await route.fulfill({json:saved})
  } else await route.fulfill({json:saved})
 })
 await page.goto('http://127.0.0.1:8080/specifications/'+specId)
 const button=page.getByRole('button',{name:'승인 설계에서 실행 명세 자동 작성',exact:true})
 await button.waitFor(); assert.equal(await button.isDisabled(),true)
 await page.getByLabel('승인 설계·현재 명세·추가 지시를 외부 AI에 전송해 실행 명세를 작성하는 데 동의합니다.').check()
 await page.getByLabel('구현 범위·추가 지시').fill('기존 화면과 업무 범위를 유지해 실행 명세를 보완합니다.')
 await button.click()
 await page.getByText('생성기 계약 검사 통과 · 사용자 승인 필요',{exact:true}).waitFor()
 assert.equal(calls,1);assert.equal(saved.bundle.spec_version,initial.bundle.spec_version)
 assert.ok((await page.getByLabel('명세 JSON').inputValue()).includes('고객 상품 관리'))
 await page.getByRole('button',{name:'새 버전 저장',exact:true}).click()
 await page.getByText('새 버전을 저장했습니다. 보완 항목을 다시 확인하세요.',{exact:true}).waitFor()
 assert.equal(saved.bundle.spec_version,initial.bundle.spec_version+1)
 assert.equal(saved.approved_by,null)
 for(const [device,width] of [['desktop',1440],['mobile',390]]) {
  await page.setViewportSize({width,height:1000});await page.evaluate(()=>scrollTo(0,0));await page.waitForTimeout(400)
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
  await page.screenshot({path:'/out/completion-'+device+'.png'})
 }
 console.log('PASS: demo scope gate, numeric table selection, proposal review/revert without save or approval; AI consent gate, proposal without persistence, review/save, no auto approval, responsive layout')
} finally {await browser.close();server.close()}
