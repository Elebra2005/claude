# usage: python3 mob_viewer.py <viewer.html> <packed.glb> <out.html> <gltf_name>
import sys,base64,re
v,glb,out,name=sys.argv[1:5]
t=open(v,encoding='utf8').read()
t=t.replace('</style>','</style>\n<style>@media (max-width:820px){#groups{display:none;max-height:45vh;overflow:auto}#groups.open{display:block}}#gbtn{margin-top:6px}</style>',1) if '#gbtn' not in t else t
t=t.replace('<div id="groups"></div>','<button id="gbtn" onclick="document.getElementById(\'groups\').classList.toggle(\'open\')">Группы (вкл/выкл слоёв)</button><div id="groups"></div>',1)
t=t.replace("import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';","import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';\nimport { MeshoptDecoder } from 'three/addons/libs/meshopt_decoder.module.js';",1)
pat=re.compile(r"new GLTFLoader\(\)\.load\(\s*['\"]"+re.escape(name)+r"['\"]\s*,\s*g\s*=>\s*\{")
rep=("const __b=atob(document.getElementById('glbdata').textContent.trim());const __u=new Uint8Array(__b.length);for(let i=0;i<__b.length;i++)__u[i]=__b.charCodeAt(i);\n"
     "const __L=new GLTFLoader(); __L.setMeshoptDecoder(MeshoptDecoder); __L.parse(__u.buffer,'', g => {")
t,n=pat.subn(lambda m:rep,t,count=1)
assert n==1,'loader call not found'
# parse(buffer,path,onLoad,onError): original load(url,onLoad,onProgress,onError) -> drop onProgress if present is not handled; fine for lib3d viewer
b64=base64.b64encode(open(glb,'rb').read()).decode()
t=t.replace('</body>','<script id="glbdata" type="application/octet-stream">'+b64+'</script>\n</body>',1)
open(out,'w',encoding='utf8').write(t)
print(out, round(len(t)/1e6,1),'MB')
