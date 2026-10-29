# usage: python3 md2pdf.py <in.md> <out.pdf>  (markdown -> html -> pdf via headless chromium)
import sys,subprocess,os,html,re
src,dst=sys.argv[1],sys.argv[2]
try:
    import markdown
except ImportError:
    subprocess.run([sys.executable,'-m','pip','install','-q','markdown'],check=True); import markdown
body=markdown.markdown(open(src,encoding='utf8').read(),extensions=['tables','fenced_code'])
page=('<html><head><meta charset="utf-8"><style>body{font:11pt "DejaVu Sans",sans-serif;margin:18mm}table{border-collapse:collapse;font-size:9pt}'
      'td,th{border:1px solid #999;padding:3px 5px;vertical-align:top}th{background:#eee}h1{font-size:16pt}h2{font-size:13pt}</style></head><body>'+body+'</body></html>')
tmp=dst+'.tmp.html'; open(tmp,'w',encoding='utf8').write(page)
js=("const {chromium}=require('playwright');(async()=>{const b=await chromium.launch();const p=await b.newPage();"
    "await p.goto('file://"+os.path.abspath(tmp)+"');await p.pdf({path:'"+os.path.abspath(dst)+"',format:'A4',landscape:true,printBackground:true});await b.close();})();")
subprocess.run(['node','-e',js],check=True,env=dict(os.environ,NODE_PATH=subprocess.run(['npm','root','-g'],capture_output=True,text=True).stdout.strip()))
os.remove(tmp); print(dst)
