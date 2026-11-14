import fs from 'node:fs'
import http from 'node:http'
import crypto from 'node:crypto'
import { chromium } from 'playwright'

const root = '/workspace/frontend/dist'
const contract = JSON.parse(fs.readFileSync('/workspace/frontend/src/contract.json'))
const spec = JSON.parse(fs.readFileSync('/workspace/spec/approved-spec.json'))
const server = http.createServer(async (req, res) => {
  if (req.url.startsWith('/api/')) {
    try {
      const chunks = []; for await (const chunk of req) chunks.push(chunk)
      const reply = await fetch('http://application:8000' + req.url.slice(4), {
        method: req.method, headers: {authorization: req.headers.authorization ?? '',
          'content-type':'application/json','idempotency-key':req.headers['idempotency-key'] ?? ''},
        body: ['GET','HEAD'].includes(req.method) ? undefined : Buffer.concat(chunks),
        redirect:'error', signal:AbortSignal.timeout(5000),
      })
      res.writeHead(reply.status, {'content-type':'application/json'}); res.end(await reply.text())
    } catch { res.writeHead(502); res.end('{}') }
  } else {
    const path = new URL(req.url, 'http://localhost').pathname
    const asset = /^\/assets\/[A-Za-z0-9_.-]+$/.test(path)
    const file = asset ? root + path : root + '/index.html'
    if (!fs.existsSync(file)) {res.writeHead(404);res.end();return}
    res.writeHead(200, {'content-type': asset ? 'text/javascript' : 'text/html'});res.end(fs.readFileSync(file))
  }
})
await new Promise(resolve => server.listen(4173,'127.0.0.1',resolve))
const browser = await chromium.launch({headless:true,args:['--disable-dev-shm-usage']})
const page = await browser.newPage({viewport:{width:1100,height:780}})
page.setDefaultTimeout(8000)
const checks=[]; const errors=[]
page.on('pageerror',error=>errors.push(error.name))
async function form(apiId) {
  const screen=contract.screens.find(s=>s.api_ids.includes(apiId))
  await page.locator(`[data-screen="${screen.id}"]`).click()
  return page.locator(`[data-api="${apiId}"]`)
}
async function submit(api, values, expected=200) {
  const id=api.id ?? api.api_id
  const f=await form(id)
  for (const [name,value] of Object.entries(values)) {
    const field=f.getByLabel(name,{exact:true})
    if (await field.evaluate(e=>e.tagName)==='SELECT') await field.selectOption(String(value))
    else await field.fill(String(value))
  }
  const response=page.waitForResponse(r=>r.url().includes('/api/') && r.request().method()===api.method)
  await f.locator('button').click()
  const reply=await response
  if (reply.status()!==expected) throw Error(`HTTP ${reply.status()} expected ${expected} for ${id}`)
  const data=await reply.json()
  if (expected<400) await page.locator('[data-result]').filter({hasText:JSON.stringify(data,null,2)}).waitFor()
  else await page.getByRole('alert').waitFor()
  const a=spec.apis.find(a=>a.id===id)
  checks.push({api_id:id,screen_id:contract.screens.find(s=>s.api_ids.includes(id)).id,
    req_ids:spec.use_cases.find(u=>u.id===a.use_case_id).req_ids,status:'passed'})
  return data
}
try {
  await page.goto('http://127.0.0.1:4173')
  await page.getByLabel('데모 접근 토큰').fill(process.env.PROBE_TOKEN)
  for (const op of contract.operations.filter(o=>o.action==='insert')) {
    const values=Object.fromEntries(op.fields.map(f=>[f.name,({string:'b',integer:9,boolean:true})[f.data_type]]))
    await submit(op,values,201)
    const get=contract.operations.find(o=>o.action==='get'&&o.entity_id===op.entity_id)
    await submit(get,{[op.key.name]:values[op.key.name]})
    await page.reload()
    if (await page.getByLabel('데모 접근 토큰').inputValue()!=='') throw Error('Token persisted')
    await page.getByLabel('데모 접근 토큰').fill(process.env.PROBE_TOKEN)
    await submit(get,{[op.key.name]:values[op.key.name]})
  }
  if (contract.inventory) {
    const ops=Object.fromEntries(contract.inventory.operations.map(o=>[o.action,o]))
    const draft=(id,kind,q)=>submit(ops.draft,{id,warehouse_id:'b',item_id:'b',kind,quantity:q},201)
    const command=(action,id)=>submit(ops[action],{'입출고 ID':id})
    const balance=async expected=>{
      const row=await submit(ops.balance,{warehouse_id:'b',item_id:'b'})
      if(row.quantity!==expected) throw Error('Balance mismatch')
    }
    await draft('browser-receipt','receive','12.125')
    await submit(ops.edit,{'입출고 ID':'browser-receipt',quantity:'10.125'})
    await command('confirm','browser-receipt'); await balance('10.125')
    await draft('browser-issue','issue','3.125'); await command('confirm','browser-issue'); await balance('7.000')
    await submit(ops.cancel,{'입출고 ID':'browser-receipt'},409)
    await page.getByLabel('데모 접근 토큰').fill(process.env.PROBE_NON_CANCEL_TOKEN)
    await submit(ops.cancel,{'입출고 ID':'browser-issue'},403)
    await page.getByLabel('데모 접근 토큰').fill(process.env.PROBE_TOKEN)
    await command('cancel','browser-issue'); await balance('10.125')
    await command('cancel','browser-receipt'); await balance('0.000')
    await command('movement','browser-receipt')
  }
  await import('./preview.mjs')
  await page.evaluate(({html,token})=>{
    document.body.innerHTML=''
    const frame=document.createElement('iframe');frame.setAttribute('sandbox','allow-scripts allow-forms');frame.style='width:100%;height:720px'
    addEventListener('message',async event=>{
      if(event.source!==frame.contentWindow||event.origin!=='null'||event.data?.type!=='specton-preview-request')return
      const d=event.data
      if(!d.path.startsWith('/api/'))return
      const r=await fetch(d.path,{method:d.method,body:d.body,headers:{Authorization:'Bearer '+token,'Content-Type':'application/json','Idempotency-Key':d.command_key||crypto.randomUUID()}})
      frame.contentWindow.postMessage({type:'specton-preview-response',id:d.id,status:r.status,body:await r.text()},'*')
    })
    frame.srcdoc=html;document.body.append(frame)
  },{html:fs.readFileSync('/workspace/preview.html','utf8'),token:process.env.PROBE_TOKEN})
  const embedded=page.frameLocator('iframe')
  const get=contract.operations.find(o=>o.action==='get')
  const screen=contract.screens.find(s=>s.api_ids.includes(get.api_id))
  await embedded.locator(`[data-screen="${screen.id}"]`).click()
  const input=embedded.locator(`[data-api="${get.api_id}"]`)
  await input.getByLabel(get.key.name,{exact:true}).fill(get.key.data_type==='integer'?'9':'b')
  await input.locator('button').click()
  await embedded.locator('[data-result]').waitFor()
  const child=page.frames().find(f=>f.parentFrame())
  const isolated=await child.evaluate(()=>{
    let parentBlocked=false,storageBlocked=false
    try {void parent.document.body}catch {parentBlocked=true}
    try {void localStorage.length}catch {storageBlocked=true}
    return parentBlocked&&storageBlocked
  })
  if(!isolated)throw Error('Preview origin isolation failed')
  if (errors.length) throw Error('Browser page error')
  const screenshot=await page.screenshot({type:'png'})
  if (screenshot.length>256*1024) throw Error('Screenshot limit exceeded')
  const assets=Object.fromEntries(fs.readdirSync(root+'/assets').sort().map(name=>[name,
    crypto.createHash('sha256').update(fs.readFileSync(root+'/assets/'+name)).digest('hex')]))
  const result={preview_checks:['opaque_origin','parent_dom_denied','storage_denied','bridge_read'],profile:'generated-ui-v1',status:'passed',browser:await browser.version(),checks,assets,
    screenshot_sha256:crypto.createHash('sha256').update(screenshot).digest('hex'),screenshot_base64:screenshot.toString('base64')}
  fs.writeFileSync('/workspace/browser-report.json',JSON.stringify(result))
} finally {await browser.close();server.close()}
