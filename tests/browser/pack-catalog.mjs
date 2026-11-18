/* Catalog UI integration with synthetic server responses; never submits a customer run. */
import {createServer} from 'node:http'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
import {chromium} from '/runner/node_modules/playwright/index.mjs'
const server=createServer(async(req,res)=>{
 const path=req.url.startsWith('/assets/')||req.url.startsWith('/fonts/')?req.url:'/index.html'
 res.setHeader('Content-Type',path.endsWith('.js')?'application/javascript':path.endsWith('.css')?'text/css':path.endsWith('.woff2')?'font/woff2':'text/html')
 res.end(await readFile('/app'+path))
}).listen(8080,'127.0.0.1')
const browser=await chromium.launch({args:['--no-sandbox']})
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000}})
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 let failed=false,creates=0
 await page.route('**/api/v1/**',route=>{
  const path=new URL(route.request().url()).pathname
  if(path==='/api/v1/packs')return route.fulfill({status:failed?503:200,json:failed?{message:'unavailable'}:[
   {name:'facilities',label:'시설관리',summary:'서버에서 등록한 새 팩',version:'1.0.0',status:'available',selectable:true,reason:'사용 가능'},
   {name:'maintenance',label:'설비보전',summary:'초안',version:'0.1.8',status:'draft',selectable:false,reason:'팩 검토·승인 대기'},
  ]})
  return route.fulfill({status:401,json:{message:'로그인 필요'}})
 })
 await page.route('**/runs**',route=>{
  if(route.request().method()==='POST')creates++
  return route.fulfill({json:[]})
 })
 await page.goto('http://127.0.0.1:8080/')
 await page.waitForFunction(()=>document.querySelector('#pack')?.value==='facilities')
 assert.equal(await page.locator('#pack option[value="maintenance"]').isDisabled(),true)
 await page.locator('input[type=file]').setInputFiles({name:'synthetic.csv',mimeType:'text/csv',buffer:Buffer.from('요구사항 ID,상세 설명\nR1,시설 등록')})
 await page.getByRole('button',{name:'설계 시작',exact:true}).waitFor()
 assert.equal(await page.getByRole('button',{name:'설계 시작',exact:true}).isEnabled(),true)
 failed=true
 await page.getByRole('button',{name:'업무 분야 새로고침',exact:true}).click()
 await page.getByText('업무 분야 목록을 불러오지 못했습니다.',{exact:true}).waitFor()
 assert.equal(await page.getByRole('button',{name:'설계 시작',exact:true}).isDisabled(),true)
 failed=false
 await page.getByRole('button',{name:'업무 분야 새로고침',exact:true}).click()
 await page.waitForFunction(()=>document.querySelector('#pack')?.value==='facilities')
 for(const width of [1440,390]){
  await page.setViewportSize({width,height:1000})
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
 }
 assert.equal(creates,0);assert.deepEqual(errors,[])
 console.log('PASS: dynamic pack discovery, draft disabled, failed catalog blocks submission, refresh recovery, responsive UI')
} finally {await browser.close();server.close()}
