/* Synthetic platform responses; actual case execution has separate Docker integration tests. */
import {createServer} from 'node:http'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
import {chromium} from '/runner/node_modules/playwright/index.mjs'
let view=JSON.parse(await readFile('/out/view.json','utf8'))
const report=JSON.parse(await readFile('/out/booking-report.json','utf8'))
const server=createServer(async(req,res)=>{
 const path=req.url.startsWith('/assets/')||req.url.startsWith('/fonts/')?req.url:'/index.html'
 res.setHeader('Content-Type',path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':path.endsWith('.woff2')?'font/woff2':'text/html')
 res.end(await readFile('/app'+path))
}).listen(8080,'127.0.0.1')
const browser=await chromium.launch({args:['--no-sandbox']})
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 let saves=0,approvals=0
 await page.route('**/api/v1/**',route=>{
  const req=route.request(),path=new URL(req.url()).pathname
  if(path.endsWith('/verifications')) return route.fulfill({json:[{id:'verification',status:'smoke_passed',source_hash:report.source_hash,report_hash:'a'.repeat(64),report}]})
  if(path.endsWith('/previews')) return route.fulfill({json:[]})
  if(path==='/api/v1/implementations/impl') return route.fulfill({json:{id:'impl',source_hash:report.source_hash,spec_version:view.bundle.spec_version}})
  if(path.endsWith('/approve'))approvals++
  if(req.method()==='PATCH'){
   saves++;view={...view,bundle:{...req.postDataJSON().bundle,spec_version:view.bundle.spec_version+1},versions:[...view.versions,view.bundle.spec_version+1],status:'ready_for_review'}
  }
  if(path.startsWith('/api/v1/specs/'))return route.fulfill({json:view})
  return route.fulfill({status:401,json:{message:'synthetic'}})
 })
 await page.goto('http://127.0.0.1:8080/specifications/'+view.bundle.spec_id+'?implementation=impl')
 await page.getByText('요구사항별 검증 근거 (3건)',{exact:true}).click()
 await page.getByText(view.bundle.requirements[0].id+' · 연결 API 검사 통과',{exact:true}).click()
 await page.getByText('TC-executable-0 · 실행 인수 · 통과 · normal',{exact:true}).waitFor()
 await page.getByRole('button',{name:'사례 편집',exact:true}).first().click()
 const editor=page.getByLabel('실행 인수 사례 JSON',{exact:true})
 const item=JSON.parse(await editor.inputValue())
 item.execution.steps[2].expect.body[0].amount='0.51'
 await editor.fill(JSON.stringify(item,null,2))
 await page.getByRole('button',{name:'인수 사례를 명세 편집기에 적용',exact:true}).click()
 assert.equal(saves,0);assert.equal(approvals,0)
 const bundle=JSON.parse(await page.getByLabel('명세 JSON',{exact:true}).inputValue())
 assert.equal(bundle.schema_version,'spec-v0.7')
 assert.equal(bundle.acceptance_cases.find(c=>c.id===item.id).execution.steps[2].expect.body[0].amount,'0.51')
 assert.equal(await page.getByRole('button',{name:'이 버전의 실행 명세 승인',exact:true}).isDisabled(),true)
 await page.getByRole('button',{name:'새 버전 저장',exact:true}).click()
 await page.getByText('새 버전을 저장했습니다. 보완 항목을 다시 확인하세요.',{exact:true}).waitFor()
 assert.equal(saves,1);assert.equal(approvals,0)
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:1000})
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
 }
 assert.deepEqual(errors,[])
 console.log('PASS: executable case evidence, explicit edit/save, no automatic approval, responsive UI')
}finally{await browser.close();server.close()}
