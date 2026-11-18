import http from 'node:http'
import fs from 'node:fs'
import assert from 'node:assert/strict'
import { chromium } from 'playwright'

const input=JSON.parse(fs.readFileSync(0,'utf8'))
const config=input.config,ops=config.domain.operations
const server=http.createServer(async(req,res)=>{
  try{
    const chunks=[];for await(const chunk of req)chunks.push(chunk)
    const headers={...req.headers};delete headers.host
    const reply=await fetch('http://application:8080'+req.url,{method:req.method,headers,body:['GET','HEAD'].includes(req.method)?undefined:Buffer.concat(chunks),redirect:'manual'})
    res.writeHead(reply.status,{'content-type':reply.headers.get('content-type')??'text/plain',...(reply.headers.getSetCookie().length?{'set-cookie':reply.headers.getSetCookie()}:{}),'cache-control':'no-store'})
    res.end(Buffer.from(await reply.arrayBuffer()))
  }catch{res.writeHead(502);res.end('proxy failed')}
})
await new Promise(resolve=>server.listen(4173,'127.0.0.1',resolve))
const browser=await chromium.launch({headless:true,args:['--disable-dev-shm-usage']})
const page=await browser.newPage({viewport:{width:1360,height:960}})
page.setDefaultTimeout(10000)
const errors=[];page.on('pageerror',e=>errors.push(e.message))
const checks=[]
const operation=(table,action)=>ops.find(o=>o.table===table&&o.action===action)
async function login(username){
  await page.getByLabel('아이디',{exact:true}).fill(username)
  await page.getByLabel('비밀번호',{exact:true}).fill(input.password)
  await page.getByRole('button',{name:'로그인',exact:true}).click()
  await page.getByRole('button',{name:'로그아웃',exact:true}).waitFor()
}
async function logout(){await page.getByRole('button',{name:'로그아웃',exact:true}).click();await page.getByLabel('아이디',{exact:true}).waitFor()}
async function raw(path,method='GET',body){return page.evaluate(async({path,method,body})=>{
  const session=await(await fetch('/api/auth/session')).json()
  const response=await fetch('/api'+path,{method,headers:{'Content-Type':'application/json','X-CSRF-Token':session.user?.csrf??'','Idempotency-Key':crypto.randomUUID()},body:body?JSON.stringify(body):undefined})
  return {status:response.status,body:await response.json()}
},{path,method,body})}
const op=ops.find(o=>o.action==='calculation')
const form=page.locator(`[data-api="${op.id}"]`)
async function submit(status){
  const waiting=page.waitForResponse(r=>new URL(r.url()).pathname==='/api'+op.path&&r.request().method()==='POST')
  await form.getByRole('button',{name:'계산·집계 결과 확인',exact:true}).click()
  const reply=await waiting;assert.equal(reply.status(),status)
  assert.equal(reply.request().headers()['idempotency-key'],undefined)
  return reply.json()
}
try{
  await page.goto('http://127.0.0.1:4173');await login('administrator')
  assert.equal((await raw(operation(input.parent,'insert').path,'POST',{id:'one',name:'fixture',amount:'5.00'})).status,200)
  let sequence=0
  for(const [scheduled,amount] of [['2030-01-01','1.01'],['2030-01-02','2.02'],['2030-02-01','99.00']]){
    assert.equal((await raw(operation(input.child,'insert').path,'POST',{parent_id:'one',sequence:++sequence,scheduled,status:'open',amount})).status,200)
  }
  await logout();await login('operator')
  const screen=config.screens.find(s=>s.api_ids.includes(op.id))
  await page.locator(`[data-screen="${screen.id}"]`).click()
  for(const [key,value] of Object.entries({id:'one',start:'2030-01-01',end:'2030-02-01',budget:'3.00'}))await form.locator(`[data-field=${key}]`).fill(value)
  const expected={count:'2',total:'3.03',average:'1.52',minimum:'1.01',maximum:'2.02',ratio:'1.0100'}
  assert.deepEqual(await submit(200),expected)
  assert.match(await form.locator('[data-result=total]').innerText(),/3.03/)
  assert.match(await form.locator('[data-result=total]').innerText(),/item/)
  checks.push('real session, read-only POST, date bounds, decimal average/ratio, visible result units')
  await form.locator('[data-field=budget]').fill('0.00')
  assert.equal((await submit(409)).detail,'CALCULATION_ERROR')
  await page.getByRole('alert').waitFor()
  assert.equal(await form.getByRole('table').count(),0)
  await form.locator('[data-field=budget]').fill('3.00')
  assert.deepEqual(await submit(200),expected)
  checks.push('zero denominator failure clears stale result; corrected retry succeeds')
  await form.locator('[data-field=end]').fill('2030-01-01')
  const empty=await submit(200);assert.equal(empty.count,'0');assert.equal(empty.average,null)
  assert.match(await form.locator('[data-result=average]').innerText(),/값 없음/)
  checks.push('equal exclusive boundary shows empty/null according to contract')
  await form.locator('[data-field=end]').fill('2030-02-01');await submit(200)
  await page.screenshot({path:'/out/calculation-desktop.png',fullPage:true})
  await page.setViewportSize({width:390,height:844})
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1))
  await page.screenshot({path:'/out/calculation-mobile.png',fullPage:true})
  checks.push('desktop and mobile result table')
  await logout();await login('administrator')
  assert.deepEqual((await raw(operation(input.parent,'list').path)).body,[{id:'one',name:'fixture',amount:'5.00'}])
  const entries=(await raw(operation(input.child,'list').path)).body
  assert.equal(entries.length,3);assert.deepEqual(entries.map(row=>row.amount),['1.01','2.02','99.00'])
  checks.push('no business rows changed by successful, failed or repeated aggregate requests')
  assert.deepEqual(errors,[])
  fs.writeFileSync('/out/report.json',JSON.stringify({status:'passed',checks,customer_auth:'real',database:'real',external_google:'not_used',external_llm:'not_used'},null,2))
}finally{await browser.close();await new Promise(resolve=>server.close(resolve))}
