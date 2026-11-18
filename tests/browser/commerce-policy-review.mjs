/* Synthetic platform API; the generated business runtime is verified separately. */
import {createServer} from 'node:http'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
import {chromium} from '/runner/node_modules/playwright/index.mjs'
const bundle=JSON.parse(await readFile('/out/before.json','utf8'))
const quote='상품 비고란을 추가하고 반품 경고 비율을 10%로 변경해 주세요.'
let change={id:'change-demo',project_id:bundle.baseline.project_id,title:quote,quote,instruction:'',state:'awaiting_decision',version:1,spec_id:bundle.spec_id,spec_version:bundle.spec_version,analysis:{summary:quote,quotes:[quote],requests:[quote],questions:[],unsupported:[],suggestions:[{section:'commerce',object_id:'wholesale-demo-v1',field:'return_warning_percent',value_json:'5',rationale:quote},{section:'commerce',object_id:'wholesale-demo-v1',field:'product_note_enabled',value_json:'false',rationale:quote}]},proposal_hash:'synthetic',implementation_id:null,baseline_stale:false,verification:null,events:[]}
const server=createServer(async(req,res)=>{
 const path=req.url.startsWith('/assets/')||req.url.startsWith('/fonts/')?req.url:'/index.html'
 res.setHeader('Content-Type',path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':path.endsWith('.woff2')?'font/woff2':'text/html')
 res.end(await readFile('/app'+path))
}).listen(8080,'127.0.0.1')
const browser=await chromium.launch({args:['--no-sandbox']})
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 let saves=0,approvals=0
 await page.route('**/api/v1/**',async route=>{
  const request=route.request(),path=new URL(request.url()).pathname
  if(path.endsWith('/integrations/gmail'))return route.fulfill({json:{analysis_enabled:true}})
  if(path.includes('/specs/'))return route.fulfill({json:{bundle}})
  if(path.endsWith('/proposal')){
   const body=request.postDataJSON();saves++
   assert.equal(body.analysis.suggestions[0].value_json,'10')
   assert.equal(body.analysis.suggestions[1].value_json,'true')
   change={...change,version:2,analysis:body.analysis}
  }
  if(path.endsWith('/decide'))approvals++
  return route.fulfill({json:change})
 })
 await page.goto('http://127.0.0.1:8080/changes/change-demo')
 const groups=page.locator('fieldset')
 await groups.nth(0).getByLabel('수정할 값',{exact:true}).fill('10')
 await groups.nth(1).getByLabel('수정할 값',{exact:true}).selectOption('true')
 await page.getByRole('button',{name:'검토한 변경안 저장',exact:true}).click()
 await page.waitForFunction(()=>!document.querySelector('fieldset[disabled]'))
 assert.equal(saves,1);assert.equal(approvals,0)
 assert.equal(await groups.nth(0).getByLabel('수정할 값',{exact:true}).inputValue(),'10')
 await page.screenshot({path:'/out/policy-review.png',fullPage:true})
 console.log('PASS: numeric policy and boolean schema-field review/save without automatic approval')
}finally{await browser.close();server.close()}
