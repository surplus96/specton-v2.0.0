/* Actual browser controls; simulated API snapshot, no customer backend writes. */
import {createServer} from 'node:http'
import {readFile,writeFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
import {chromium} from '/runner/node_modules/playwright/index.mjs'
const initial=JSON.parse(await readFile('/input/spec-view.json','utf8'))
const packet=JSON.parse(await readFile('/input/preparation.json','utf8'))
const server=createServer(async(req,res)=>{
 const path=req.url.startsWith('/assets/')||req.url.startsWith('/fonts/')?req.url:'/index.html'
 res.setHeader('Content-Type',path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':path.endsWith('.woff2')?'font/woff2':'text/html')
 res.end(await readFile('/app'+path))
}).listen(8080,'127.0.0.1')
const browser=await chromium.launch({args:['--no-sandbox']})
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 let writes=0,approved=0,saved=structuredClone(initial)
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/v1/**',async route=>{
  const req=route.request(),path=new URL(req.url()).pathname
  if(path.endsWith('/scope')||path.endsWith('/handoff'))return route.fulfill({status:503,json:{message:'독립 UI 시험에서는 범위 조회를 호출하지 않습니다.'}})
  if(path.endsWith('/approve')){approved++;return route.fulfill({status:409,json:{message:'시험 범위 밖 승인'}})}
  if(req.method()==='PATCH'){
   writes++;saved.bundle=req.postDataJSON().bundle;saved.bundle.spec_version++
   saved.versions.push(saved.bundle.spec_version);saved.readiness.spec_hash='new-version-hash'
   return route.fulfill({json:saved})
  }
  assert.equal(req.method(),'GET','Unexpected mutation/external analysis')
  return route.fulfill({json:saved})
 })
 await page.goto('http://127.0.0.1:8080/specifications/'+initial.bundle.spec_id)
 const input=page.getByLabel('준비 파일 선택',{exact:true});await input.waitFor()
 const file=obj=>({name:'preparation.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify(obj))})
 await input.setInputFiles(file({...packet,base_spec_hash:'stale'}))
 await page.getByText('준비 파일의 기준 버전이 현재 명세와 다릅니다. 최신 명세로 다시 준비하세요.',{exact:true}).waitFor()
 assert.equal(writes,0)
 await input.setInputFiles(file(packet))
 await page.getByRole('button',{name:'준비안을 편집기에 반영',exact:true}).click()
 let draft=JSON.parse(await page.getByLabel('명세 JSON',{exact:true}).inputValue())
 assert.ok(draft.questions.every(q=>q.answer===null));assert.equal(writes,0);assert.equal(approved,0)
 await page.getByRole('button',{name:'편집 되돌리기',exact:true}).click()
 await input.setInputFiles(file(packet))
 await page.getByLabel('포함·제외 범위와 테스트 가정을 검토했으며, 제안된 답변을 편집기에 함께 반영합니다.').check()
 await page.getByRole('button',{name:'준비안을 편집기에 반영',exact:true}).click()
 draft=JSON.parse(await page.getByLabel('명세 JSON',{exact:true}).inputValue())
 assert.ok(draft.questions.every(q=>q.answer?.includes('미승인')))
 assert.equal(draft.requirements.length,25);assert.equal(draft.requirements.filter(r=>r.priority==='Must').length,7)
 assert.equal(writes,0);assert.equal(approved,0)
 assert.equal(await page.getByRole('button',{name:'이 버전의 실행 명세 승인',exact:true}).isDisabled(),true)
 for(const[device,width]of[['desktop',1440],['tablet',820],['mobile',390]]){
  await page.setViewportSize({width,height:1000})
  await page.getByRole('heading',{name:'E2E 준비 파일 검토',exact:true}).scrollIntoViewIfNeeded()
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
  await page.screenshot({path:'/out/import-'+device+'.png'})
 }
 await page.getByRole('button',{name:'새 버전 저장',exact:true}).click()
 await page.getByText('새 버전을 저장했습니다. 보완 항목을 다시 확인하세요.',{exact:true}).waitFor()
 assert.equal(writes,1);assert.equal(approved,0);assert.equal(saved.bundle.spec_version,initial.bundle.spec_version+1);assert.equal(saved.approved_by,null)
 await input.setInputFiles(file(packet))
 await page.getByText('준비 파일의 기준 버전이 현재 명세와 다릅니다. 최신 명세로 다시 준비하세요.',{exact:true}).waitFor()
 assert.deepEqual(errors,[])
 const report={status:'passed',platform_api:'simulated_snapshot',customer_mutation:false,real_browser:true,automatic_saves:0,automatic_approvals:0,explicit_simulated_saves:writes,checks:['stale file rejected','unanswered import','explicit assumption review','25 requirements preserved','7 included/18 deferred','no save on import','approval disabled for unsaved draft','explicit save only','desktop/tablet/mobile','reimport stale after save rejected']}
 await writeFile('/out/import-report.json',JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report))
}finally{await browser.close();server.close()}
