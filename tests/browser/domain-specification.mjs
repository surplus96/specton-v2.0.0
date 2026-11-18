/* Synthetic responses exercise UI boundaries; DB/compiler and generated apps have separate tests. */
import {createServer} from 'node:http'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
import {chromium} from '/runner/node_modules/playwright/index.mjs'
let spec=JSON.parse(await readFile('/out/view.json','utf8'))
const proposal=JSON.parse(await readFile('/out/proposal.json','utf8'))
const server=createServer(async(req,res)=>{
 const path=req.url.startsWith('/assets/')||req.url.startsWith('/fonts/')?req.url:'/index.html'
 res.setHeader('Content-Type',path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':path.endsWith('.woff2')?'font/woff2':'text/html')
 res.end(await readFile('/app'+path))
}).listen(8080,'127.0.0.1')
const browser=await chromium.launch({args:['--no-sandbox']})
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 let derives=0,saves=0,approvals=0
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname
  if(path.endsWith('/derive')){derives++;return route.fulfill({json:proposal})}
  if(req.method()==='PATCH'){
   saves++;spec={...spec,bundle:{...req.postDataJSON().bundle,spec_version:spec.bundle.spec_version+1},versions:[...spec.versions,spec.bundle.spec_version+1]}
  }
  if(path.endsWith('/approve'))approvals++
  return route.fulfill({json:spec})
 })
 await page.goto('http://127.0.0.1:8080/specifications/'+spec.bundle.spec_id)
 await page.getByRole('button',{name:'승인 설계 구조 자동 연결',exact:true}).click()
 await page.getByText('승인 설계의 구조를 연결했습니다. 요구별 업무 동작을 검토한 후 저장하세요.',{exact:true}).waitFor()
 assert.equal(derives,1);assert.equal(saves,0);assert.equal(approvals,0)
 assert.equal(await page.getByRole('button',{name:'주문·반품·알림 실행 명세 자동 작성'}).count(),0)
 assert.equal(await page.getByRole('button',{name:'이 버전의 실행 명세 승인',exact:true}).isDisabled(),true)
 const requirements=proposal.bundle.requirements
 for(const req of requirements) assert.equal(await page.getByLabel('구현 상태 '+req.id,{exact:true}).inputValue(),'needs_review')
 await page.getByLabel('구현 상태 '+requirements[0].id,{exact:true}).selectOption('unsupported')
 await page.getByRole('button',{name:'새 버전 저장',exact:true}).click()
 await page.getByText('새 버전을 저장했습니다. 보완 항목을 다시 확인하세요.',{exact:true}).waitFor()
 assert.equal(saves,1);assert.equal(approvals,0)
 assert.equal(await page.getByRole('button',{name:'이 버전의 실행 명세 승인',exact:true}).isDisabled(),true)
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:1000})
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
 }
 console.log('PASS: domain-derived draft, no fixed profile, explicit coverage, no auto save/approval, responsive UI')
}finally{await browser.close();server.close()}
