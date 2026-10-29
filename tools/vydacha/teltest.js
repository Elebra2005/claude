const {chromium}=require('playwright');const path=require('path');
(async()=>{const b=await chromium.launch();const p=await b.newPage({viewport:{width:900,height:1600}});
const T=process.env.TDIR;
await p.route(/unpkg\.com\/three@[^/]+\/(.*)/,r=>{const m=r.request().url().match(/three@[^/]+\/(.*?)(\?|$)/);r.fulfill({path:path.join(T,m[1]),contentType:'application/javascript'});});
const errs=[];p.on('pageerror',e=>errs.push(e.message));p.on('console',m=>{if(m.type()=='error')errs.push(m.text())});
await p.goto('file://'+process.argv[2]);await p.waitForTimeout(12000);await p.screenshot({path:process.argv[3]});console.log('errors',errs.slice(0,5));await b.close();})();
