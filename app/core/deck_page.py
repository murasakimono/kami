"""Kami Deck telefon sayfasi (/deck): Stream Deck benzeri tus izgarasi + profil duzenleme + uzaktan indirme yonetimi."""

DECK_HTML = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="theme-color" content="#120E18">
<title>Kami Deck</title>
<style>
:root{--bg:#120E18;--card:#1D1726;--line:#2D2440;--tx:#E7E2EF;--mut:#9A90AB;--ac:#9D6BFF;--ok:#2EE6A6;--bad:#FF6B81}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--tx);font:15px system-ui,-apple-system,sans-serif;padding:env(safe-area-inset-top) 12px 90px}
header{display:flex;align-items:center;gap:8px;padding:12px 0}
header h1{font-size:18px;margin:0;flex:1}header h1 b{color:var(--ac)}
button,select,input{font:inherit;color:var(--tx);background:var(--card);border:1px solid var(--line);border-radius:12px;padding:9px 12px}
button:active{transform:scale(.96)}
.tabs{display:flex;gap:6px;overflow-x:auto;padding-bottom:8px;scrollbar-width:none}
.tabs button{white-space:nowrap}.tabs button.on{background:var(--ac);border-color:var(--ac);color:#fff}
.grid{display:grid;gap:10px;margin-top:6px}
.key{aspect-ratio:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;border-radius:18px;
 background:linear-gradient(160deg,#2A2138,#1A1423);border:1px solid var(--line);font-size:12px;text-align:center;padding:6px;
 box-shadow:0 4px 14px #0006,inset 0 1px 0 #ffffff10;user-select:none;position:relative;overflow:hidden}
.key i{font-style:normal;font-size:30px;line-height:1}.key span{color:var(--mut);max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.key.ok{box-shadow:0 0 0 2px var(--ok)}.key.err{box-shadow:0 0 0 2px var(--bad)}
.edit .key:not(.add){animation:wob .3s infinite alternate}@keyframes wob{from{transform:rotate(-1.2deg)}to{transform:rotate(1.2deg)}}
.key .x{position:absolute;top:4px;right:6px;color:var(--bad);font-size:16px;display:none}.edit .key .x{display:block}
.add{border-style:dashed;background:none;color:var(--mut)}
nav{position:fixed;left:0;right:0;bottom:0;display:flex;background:#0E0B13ee;backdrop-filter:blur(10px);border-top:1px solid var(--line);
 padding:8px 10px calc(8px + env(safe-area-inset-bottom))}nav button{flex:1;margin:0 4px;border:0;background:none;color:var(--mut)}
nav button.on{color:var(--ac);font-weight:600}
.dl{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:10px;margin:8px 0}
.dl .t{font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dl .m{font-size:12px;color:var(--mut);margin:4px 0}
.bar{height:5px;background:#000;border-radius:3px;overflow:hidden}.bar div{height:100%;background:var(--ac)}
.dl .b{display:flex;gap:6px;margin-top:8px}.dl .b button{padding:6px 10px;font-size:13px}
.sheet{position:fixed;inset:0;background:#000a;display:none;align-items:flex-end;z-index:9}.sheet.on{display:flex}
.sheet>div{background:var(--card);width:100%;max-height:80vh;overflow:auto;border-radius:20px 20px 0 0;padding:16px}
.cat{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.cat .key{font-size:11px}.cat .key i{font-size:22px}
h3{margin:14px 0 6px;font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.05em}
#msg{position:fixed;left:50%;bottom:90px;transform:translateX(-50%);background:#000c;padding:8px 14px;border-radius:20px;font-size:13px;display:none}
.row{display:flex;gap:8px;align-items:center;margin:8px 0}.row input{flex:1}
</style></head><body>
<header><h1>Kami <b>Deck</b></h1><button id="bEdit">✎</button></header>
<div id="keyBox" class="row" style="display:none"><input id="k" placeholder="Anahtar (Kami > Ayarlar > Telefon)"><button id="kOk">Kaydet</button></div>
<section id="pDeck"><div class="tabs" id="tabs"></div><div class="grid" id="grid"></div></section>
<section id="pDl" hidden>
 <div class="row"><button id="pa">⏸ Hepsi</button><button id="ra">▶ Hepsi</button>
 <select id="lim"><option value="0">Sınırsız</option><option value="512">512 KB/s</option><option value="1024">1 MB/s</option>
 <option value="2048">2 MB/s</option><option value="5120">5 MB/s</option><option value="10240">10 MB/s</option></select></div>
 <div id="dls"></div>
 <h3>Link ekle</h3><div class="row"><input id="url" placeholder="https://…"><button id="addUrl">Ekle</button></div>
</section>
<nav><button class="on" data-p="pDeck">🎛 Deck</button><button data-p="pDl">⬇ İndirmeler</button></nav>
<div class="sheet" id="sheet"><div id="sheetIn"></div></div><div id="msg"></div>
<script>
const $=i=>document.getElementById(i);let D=null,P=0,EDIT=false,tmr=0;
const key=()=>localStorage.kamiKey||new URLSearchParams(location.search).get('k')||'';
if(new URLSearchParams(location.search).get('k'))localStorage.kamiKey=new URLSearchParams(location.search).get('k');
const msg=(t,ms=1600)=>{const m=$('msg');m.textContent=t;m.style.display='block';clearTimeout(m._t);m._t=setTimeout(()=>m.style.display='none',ms)};
async function post(path,body={}){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Kami-Key':key()},body:JSON.stringify(body)});
 if(r.status===401){$('keyBox').style.display='flex';throw new Error('anahtar')}return r.json()}
const catOf=a=>D.catalog.find(c=>c.id===a)||{label:a,icon:'?'};
function save(){post('/deck/save',{profiles:D.profiles,cols:D.cols}).then(r=>{D.profiles=r.profiles;D.cols=r.cols}).catch(()=>{})}
function render(){
 const t=$('tabs');t.innerHTML='';D.profiles.forEach((p,i)=>{const b=document.createElement('button');b.textContent=p.name;b.className=i===P?'on':'';
  b.onclick=()=>{if(!EDIT||i!==P){P=i;render();return}const n=prompt('Profil adı',p.name);if(n===null)return;if(!n){if(D.profiles.length>1&&confirm('Profili sil?')){D.profiles.splice(i,1);P=0}}else p.name=n;save();render()};t.appendChild(b)});
 if(EDIT&&!document.getElementById('hint')){const h=document.createElement('div');h.id='hint';h.style.cssText='font-size:12px;color:var(--mut);margin:4px 0';h.textContent='Düzenleme: seçili profile tekrar dokun → adını değiştir/sil · tuşa dokun → ayarla · ✕ sil · sürükle → sırala';$('pDeck').insertBefore(h,$('grid'))}
 if(!EDIT)document.getElementById('hint')?.remove();
 if(EDIT){const b=document.createElement('button');b.textContent='+ Profil';b.onclick=()=>{D.profiles.push({name:'Yeni',buttons:[]});P=D.profiles.length-1;save();render()};t.appendChild(b);
  const c=document.createElement('select');[2,3,4,5,6].forEach(n=>{const o=new Option(n+' sütun',n);o.selected=n===D.cols;c.appendChild(o)});c.onchange=()=>{D.cols=+c.value;save();render()};t.appendChild(c)}
 const g=$('grid');g.className='grid'+(EDIT?' edit':'');g.style.gridTemplateColumns=`repeat(${D.cols||4},1fr)`;g.innerHTML='';
 const prof=D.profiles[P]||{buttons:[]};
 prof.buttons.forEach((b,i)=>{const c=catOf(b.a),k=document.createElement('div');k.className='key';if(b.color)k.style.background=b.color;
  k.innerHTML=`<b class="x">✕</b><i></i><span></span>`;k.querySelector('i').textContent=b.icon||c.icon;k.querySelector('span').textContent=b.label||c.label;
  k.onclick=e=>{if(EDIT){if(e.target.classList.contains('x')){prof.buttons.splice(i,1);save();render()}else pick(i);return}fire(b,k)};
  if(EDIT){k.draggable=true;k.ondragstart=e=>e.dataTransfer.setData('i',i);k.ondragover=e=>e.preventDefault();
   k.ondrop=e=>{const f=+e.dataTransfer.getData('i');const [m]=prof.buttons.splice(f,1);prof.buttons.splice(i,0,m);save();render()}}
  g.appendChild(k)});
 if(EDIT){const a=document.createElement('div');a.className='key add';a.innerHTML='<i>＋</i><span>Tuş ekle</span>';a.onclick=()=>pick(-1);g.appendChild(a)}
}
async function fire(b,el){navigator.vibrate?.(15);
 try{const r=await post('/deck/run',{a:b.a,arg:b.arg||''});el.classList.add(r.ok?'ok':'err');if(!r.ok)msg('✕ '+(r.error||'olmadı'),2600)}
 catch(e){el.classList.add('err');msg('✕ '+e.message)}setTimeout(()=>el.classList.remove('ok','err'),500)}
function pick(i){const prof=D.profiles[P],cur=i>=0?prof.buttons[i]:null,groups={};D.catalog.forEach(c=>(groups[c.group]=groups[c.group]||[]).push(c));
 let h='';for(const[g,list]of Object.entries(groups)){h+=`<h3>${g}</h3><div class="cat">`+list.map(c=>`<div class="key" data-a="${c.id}"><i>${c.icon}</i><span>${c.label}</span></div>`).join('')+'</div>'}
 $('sheetIn').innerHTML=(cur?`<div class="row"><input id="eL" placeholder="Etiket" value="${(cur.label||'').replace(/"/g,'&quot;')}"><input id="eI" placeholder="Simge" style="max-width:70px" value="${cur.icon||''}"></div>
  <div class="row"><input id="eA" placeholder="${catOf(cur.a).arg||'argüman yok'}" value="${(cur.arg||'').replace(/"/g,'&quot;')}"><input id="eC" type="color" value="${cur.color||'#2A2138'}" style="max-width:60px"><button id="eS">Kaydet</button></div>
  <div class="row"><button id="eL1">◀ Sola taşı</button><button id="eR1">Sağa taşı ▶</button></div>`:'')+h;
 $('sheet').classList.add('on');
 if(cur)$('eS').onclick=()=>{cur.label=$('eL').value;cur.icon=$('eI').value;cur.arg=$('eA').value;cur.color=$('eC').value==='#2a2138'?'':$('eC').value;save();close();render()};
 const mv=d=>{const j=i+d;if(j<0||j>=prof.buttons.length)return;[prof.buttons[i],prof.buttons[j]]=[prof.buttons[j],prof.buttons[i]];save();close();render()};
 if(cur){$('eL1').onclick=()=>mv(-1);$('eR1').onclick=()=>mv(1)}
 $('sheetIn').querySelectorAll('.cat .key').forEach(k=>k.onclick=()=>{const c=catOf(k.dataset.a);let arg='';
  if(c.arg){arg=prompt(c.label+': '+c.arg,cur?.arg||'');if(arg===null)return}
  const nb={a:c.id,arg};if(cur)Object.assign(cur,nb,{label:'',icon:''});else prof.buttons.push(nb);save();close();render()})}
const close=()=>$('sheet').classList.remove('on');$('sheet').onclick=e=>{if(e.target.id==='sheet')close()};
$('bEdit').onclick=()=>{EDIT=!EDIT;$('bEdit').textContent=EDIT?'✓':'✎';render()};
$('kOk').onclick=()=>{localStorage.kamiKey=$('k').value.trim();$('keyBox').style.display='none';load()};
function renderDl(list){$('dls').innerHTML='';if(!list.length){$('dls').innerHTML='<p style="color:var(--mut)">İndirme yok.</p>';return}
 for(const d of list){const e=document.createElement('div');e.className='dl';const pct=d.percent||0;
  e.innerHTML=`<div class="t"></div><div class="m"></div><div class="bar"><div style="width:${pct}%"></div></div><div class="b"></div>`;
  e.querySelector('.t').textContent=d.name||('#'+d.id);e.querySelector('.m').textContent=d.label||'';
  const B=e.querySelector('.b'),btn=(t,a,x={})=>{const b=document.createElement('button');b.textContent=t;b.onclick=async()=>{
   if(a==='remove'&&!confirm('Listeden kaldırılsın mı?'))return;const r=await post('/dl/action',{id:d.id,action:a,...x});if(r.downloads)renderDl(r.downloads);else msg(r.ok?'✓':'✕')};B.appendChild(b)};
  if(d.can_pause)btn('⏸','pause');if(d.can_resume)btn('▶','resume');if(d.can_top)btn('⇡ Öne al','top');btn('✕','remove');$('dls').appendChild(e)}}
async function load(){try{D=await post('/deck/data');if(P>=D.profiles.length)P=0;render();renderDl(D.downloads||[]);$('lim').value=String(D.limit||0)}catch(e){}}
async function pollDl(){if($('pDl').hidden)return;try{const r=await post('/deck/data');renderDl(r.downloads||[])}catch(e){}}
document.querySelectorAll('nav button').forEach(b=>b.onclick=()=>{document.querySelectorAll('nav button').forEach(x=>x.classList.toggle('on',x===b));
 ['pDeck','pDl'].forEach(p=>$(p).hidden=p!==b.dataset.p);clearInterval(tmr);if(b.dataset.p==='pDl'){pollDl();tmr=setInterval(pollDl,2000)}});
$('pa').onclick=()=>post('/deck/run',{a:'dl:pause_all'}).then(pollDl);$('ra').onclick=()=>post('/deck/run',{a:'dl:resume_all'}).then(pollDl);
$('lim').onchange=()=>post('/deck/run',{a:'dl:limit',arg:$('lim').value}).then(r=>msg(r.ok?'✓ Hız sınırı':'✕'));
$('addUrl').onclick=async()=>{const u=$('url').value.trim();if(!u)return;const r=await fetch('/send',{method:'POST',headers:{'Content-Type':'application/json','X-Kami-Key':key()},body:JSON.stringify({text:u})}).then(r=>r.json());
 msg(r.message||(r.ok?'✓':'✕'),2600);if(r.ok){$('url').value='';setTimeout(pollDl,800)}};
if(!key())$('keyBox').style.display='flex';else load();
</script></body></html>"""
