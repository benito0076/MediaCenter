const p=document.getElementById('p'),lis=[...document.querySelectorAll('li')];let cur=-1;
const vid='{kind}'!=='musique';let last=0,proprio=false,geste=0;const APPAREIL=(()=>{try{let a=sessionStorage.getItem('appareil');  // même onglet = même appareil, même après rechargement
 if(!a)sessionStorage.setItem('appareil',a=Math.random().toString(36).slice(2));return a}catch(e){return Math.random().toString(36).slice(2)}})();  // proprio : cet appareil joue (ou a joué) le morceau en cours
function envoi(l,data){navigator.sendBeacon('/suivi/{kind}/'+l.dataset.id,JSON.stringify(data))}
function save(){if(!vid){if(cur>=0&&proprio)navigator.sendBeacon('/encours',  // musique : morceau en cours, commun aux appareils
  JSON.stringify({k:lis[cur].dataset.k,t:p.currentTime||0,lecture:!p.paused,dev:APPAREIL,vol:p.volume}));return}
 if(window.etatVideo)etatVideo();  // télécommande : position toutes les 10 s
 if(cur<0||!(p.currentTime>1))return;const l=lis[cur];envoi(l,{t:p.currentTime,d:p.duration||0});
 l.dataset.pos=p.currentTime;if(p.duration&&p.currentTime>.9*p.duration){l.classList.add('vu');l.dataset.pos=0}}
p.ontimeupdate=()=>{if(Math.abs(p.currentTime-last)>10){last=p.currentTime;save()}};
p.onpause=save;addEventListener('pagehide',save);
document.querySelectorAll('.ck').forEach(b=>b.onclick=e=>{e.stopPropagation();const l=b.closest('li'),v=!l.classList.contains('vu');
 l.classList.toggle('vu',v);l.dataset.pos=0;const bar=l.querySelector('.bar');if(bar)bar.remove();envoi(l,{vu:v})});
// Source : lecture directe, ou conversion à la volée par le PC (HLS) si le navigateur ne sait pas lire la vidéo.
let hls=null;window.enHls=false;const FFMPEG_OK='{ffmpeg}';
async function source(l,auto){if(hls){hls.destroy();hls=null}enHls=false;
 const direct='/media/{kind}/'+l.dataset.id,lance=()=>{if(auto)p.play().catch(()=>{})};  // interrompu par un changement : normal
 let d={};if(vid&&FFMPEG_OK)try{d=await (await fetch('/lecture/{kind}/'+l.dataset.id)).json()}catch(e){}
 if(lis[cur]!==l)return;
 if(d.hls)return versHls(l,lance);
 p.src=direct;lance();
 if(vid&&FFMPEG_OK)p.addEventListener('error',()=>{if(lis[cur]===l&&!enHls)versHls(l,lance)},{once:true})}  // illisible malgré tout
async function versHls(l,lance){enHls=true;const url='/hls/{kind}/'+l.dataset.id+'/index.m3u8';
 if(window.MediaSource){if(!window.Hls)await new Promise((ok,ko)=>{const s=document.createElement('script');
   s.src='/hlsjs/hls.light.min.js';s.onload=ok;s.onerror=ko;document.head.append(s)});
  if(lis[cur]!==l)return;hls=new Hls({maxBufferLength:30});hls.loadSource(url);hls.attachMedia(p)}
 else p.src=url;  // Safari / iPhone : HLS natif
 lance()}
function play(i,auto=true){if(i<0||i>=lis.length)return;save();lis.forEach(l=>l.classList.remove('on'));
 cur=i;const l=lis[i];l.classList.add('on');last=+l.dataset.pos||0;
 if(vid&&last>5)p.addEventListener('loadedmetadata',()=>p.currentTime=last,{once:true});  // reprise
 const pret=source(l,auto);
 p.querySelectorAll('track').forEach(t=>t.remove());
 assOff();if(window.audioReset)pret.then(()=>audioReset(l));{const a=document.getElementById('amp');if(a)a.hidden=!AMPLI}
 if(vid)pistesST(l);
 document.title=dt.textContent=l.dataset.t;dr.textContent=l.dataset.r||'';
 const pc=document.getElementById('pc');if(pc){pc.src=l.dataset.img||'';pc.hidden=!l.dataset.img}window.scrollTo(0,0)}
function pistesST(l,choisir){p.querySelectorAll('track').forEach(t=>t.remove());
 fetch('/pistes/{kind}/'+l.dataset.id).then(r=>r.json()).then(st=>{if(lis[cur]!==l)return;  // déjà passé à une autre vidéo
  const choix=choisir!=null?st.findIndex(s=>s.nom===choisir):Math.max(0,st.findIndex(s=>/fr|vf/i.test(s.nom)));  // français de préférence
  st.forEach((s,n)=>{const t=document.createElement('track');
   Object.assign(t,{kind:'subtitles',label:s.nom,default:n===choix,src:'/sub/{kind}/'+l.dataset.id+'/'+n});
   if(s.ass)t.dataset.ass='/ass/{kind}/'+l.dataset.id+'/'+n;p.appendChild(t);});
  setTimeout(()=>{if(choisir!=null)p.querySelectorAll('track').forEach((t,j)=>t.track.mode=j===choix?'showing':'disabled');majAss()},300)})}  // après la sélection automatique du navigateur
// Sous-titres en ligne (OpenSubtitles) : téléchargés sur le PC à côté de la vidéo, puis ajoutés à la liste.
{const b=document.getElementById('osub');if(vid&&b&&'{osub}'){b.hidden=false;b.onclick=async()=>{if(cur<0)return;const l=lis[cur],txt=b.textContent;
 b.disabled=true;b.textContent='⏳ Recherche…';try{const r=await fetch('/soustitres-en-ligne/{kind}/'+l.dataset.id,{method:'POST'});
  if(r.ok)pistesST(l,(await r.json()).nom);else alert(r.status==404?'Aucun sous-titre trouvé.':r.status==429?'Quota du jour atteint sur OpenSubtitles.':'OpenSubtitles ne répond pas.')}
 catch(e){alert('OpenSubtitles ne répond pas.')}b.disabled=false;b.textContent=txt}}}
document.getElementById('lg').onclick=async()=>{await fetch('/langue',{method:'POST'});location.reload()};
document.getElementById('rs').onclick=async e=>{const b=e.currentTarget;b.disabled=true;b.textContent='⏳';
 try{const r=await (await fetch('/rescan',{method:'POST'})).json();if(r.nouveaux)location.reload();else{b.textContent='✓';setTimeout(()=>{b.textContent='🔄';b.disabled=false},1500)}}
 catch(x){b.textContent='🔄';b.disabled=false}};
// Sous-titres .ass : rendu stylé par JASSUB par-dessus la vidéo ; la piste WebVTT simple reste en secours.
let jas=null,assUrl=null;
function assOff(){assUrl=null;if(jas){jas.destroy();jas=null}p.classList.remove('ass')}
async function majAss(){const t=[...p.querySelectorAll('track')].find(t=>t.track.mode==='showing'),url=t&&t.dataset.ass||null;
 if(url===assUrl)return;assOff();if(!url)return;assUrl=url;p.classList.add('ass');
 try{const id=lis[cur].dataset.id,[{default:JASSUB},fonts]=await Promise.all([import('/jassub/jassub.js'),
   fetch('/polices/{kind}/'+id).then(r=>r.json())]);
  if(assUrl!==url)return;
  jas=new JASSUB({video:p,subUrl:url,fonts,wasmUrl:'/jassub/wasm/jassub-worker-modern.wasm',
   wasmWorkerUrl:'/jassub/wasm/jassub-worker-modern.js'});await jas.ready}
 catch(e){console.warn('Rendu .ass indisponible, sous-titres simples :',e);if(assUrl===url){jas=null;p.classList.remove('ass')}}}
if(vid){p.textTracks.onchange=majAss;const vw=document.getElementById('vw'),
 fs=()=>document.fullscreenElement?document.exitFullscreen():vw.requestFullscreen();  // plein écran avec les sous-titres stylés
 document.getElementById('fs').onclick=fs;p.ondblclick=fs}
let distant=false;  // télécommande : un autre appareil joue, les clics le pilotent
function commande(cmd,k,pour,v){fetch('/commande'+(pour?'?pour='+pour:''),{method:'POST',body:JSON.stringify({cmd,k,v})}).catch(()=>{})}
let vdistant=false;  // télécommande vidéo : un autre appareil joue un film/épisode de cette même page
lis.forEach((l,i)=>l.onclick=()=>l.dataset.href?location.href=l.dataset.href:distant?commande('jouer',l.dataset.k)
 :vdistant?commande('jouer',l.dataset.id,'video'):play(i));
// ---- Pistes audio : le navigateur ne sait pas changer de piste ; une autre piste est convertie une fois par le PC (ffmpeg)
// puis jouée dans un lecteur audio caché, synchronisé avec l'image (le son d'origine de la vidéo est coupé).
if(vid){const pa=new Audio(),pas=document.getElementById('pas'),pal=document.getElementById('pal'),pae=document.getElementById('pae');
 let paActif=false,volPrec=1,demande=0,auListe=[];window.audioIdx=0;
 window.audioNoms=()=>auListe.map(a=>a.nom);
 const sync=()=>{if(paActif&&Math.abs(pa.currentTime-p.currentTime)>0.25)pa.currentTime=p.currentTime};
 p.addEventListener('play',()=>{if(paActif){sync();pa.play().catch(()=>{})}});
 for(const ev of ['pause','waiting'])p.addEventListener(ev,()=>{if(paActif)pa.pause()});
 p.addEventListener('playing',()=>{if(paActif){sync();pa.play().catch(()=>{})}});
 p.addEventListener('seeked',sync);p.addEventListener('ratechange',()=>{pa.playbackRate=p.playbackRate});
 setInterval(()=>{if(paActif&&!p.paused)sync()},1000);  // rattrape la dérive
 // Son d'origine coupé (p.muted) : le volume et le bouton muet du lecteur pilotent la piste convertie.
 p.addEventListener('volumechange',()=>{if(!paActif)return;if(!p.muted){if(p.volume!==volPrec)pa.muted=false;else pa.muted=!pa.muted;p.muted=true}
  pa.volume=volPrec=p.volume});
 function natif(){paActif=false;pa.pause();pa.removeAttribute('src');pa.load();p.muted=false}
 window.choisirAudio=async n=>{const l=lis[cur],id=l.dataset.id,jeton=++demande;audioIdx=n;pas.value=String(n);pae.textContent='';
  if(window.etatVideo)etatVideo();
  if(n===0&&(!(auListe[0]||{}).convertir||enHls))return natif();  // piste d'origine lisible (ou déjà convertie en HLS)
  pae.textContent='préparation de la piste… (jusqu’à une minute la première fois)';
  for(;;){let e;try{e=(await (await fetch('/audio-etat/{kind}/'+id+'/'+n)).json()).etat}catch(x){e='erreur réseau'}
   if(jeton!==demande)return;if(e==='pret')break;if(e!=='en cours'){pae.textContent=e;return}await new Promise(r=>setTimeout(r,2000))}
  pa.src='/audio/{kind}/'+id+'/'+n;pa.volume=volPrec=p.volume;pa.muted=false;
  await new Promise(r=>pa.addEventListener('loadedmetadata',r,{once:true}));if(jeton!==demande)return;
  paActif=true;p.muted=true;pae.textContent='';sync();if(!p.paused)pa.play().catch(()=>{})};
 pas.onchange=()=>choisirAudio(+pas.value);
 window.audioReset=async l=>{demande++;natif();auListe=[];audioIdx=0;pal.hidden=true;pae.textContent='';
  try{auListe=await (await fetch('/audios/{kind}/'+l.dataset.id)).json()}catch(e){}if(lis[cur]!==l)return;
  pas.replaceChildren(...auListe.map((a,j)=>{const o=document.createElement('option');o.value=String(j);
   o.textContent=a.nom+(a.convertir?' – convertie':'');return o}));
  pal.hidden=auListe.length<2&&!(auListe[0]||{}).convertir;
  if((auListe[0]||{}).convertir&&!enHls)choisirAudio(0);  // son illisible (AC3, DTS…) : converti d'office
  if(window.etatVideo)etatVideo()}}
{const cv=document.getElementById('cv');if(cv)cv.onclick=async()=>{
 if(!confirm('Supprimer les pistes audio converties ? Elles seront reconverties si tu les rechoisis.'))return;
 try{const r=await (await fetch('/cache-audio',{method:'POST'})).json();
  document.getElementById('ct').textContent=Math.round(r.octets/1e6)+' Mo'+(r.octets?' (piste en cours d’écoute gardée)':'');cv.disabled=true}catch(e){}}}
// ---- Passthrough : le navigateur décode toujours le son ; mpv/VLC sur le PC l'envoie tel quel (Dolby/DTS) à l'ampli.
const AMPLI='{ampli}';
async function versAmpli(kind,id,t,piste,ici){const r=await fetch('/externe',{method:'POST',body:JSON.stringify({kind,id,t,piste})});
 if(!r.ok)return alert('Impossible d’ouvrir le lecteur '+AMPLI+' sur le PC.');if(ici)p.pause();else commande('pause','','video')}
if(vid&&AMPLI){document.getElementById('amp').title='Ouvre ce film dans '+AMPLI+' sur le PC, à la même position';
 document.getElementById('amp').onclick=()=>versAmpli('{kind}',+lis[cur].dataset.id,p.currentTime,window.audioIdx||0,true)}
// ---- Films / séries : l'appareil qui joue publie son état et exécute les ordres ; les autres affichent la télécommande.
if(vid){let vproprio=false,vtTouche=0,vtEnvoi=0,volV;
 const vt=document.getElementById('vt'),vtpp=document.getElementById('vtpp'),vtv=document.getElementById('vtv'),
  hms=s=>{s=Math.max(0,Math.floor(s));const h=Math.floor(s/3600),m=Math.floor(s/60)%60;return (h?h+':'+String(m).padStart(2,'0'):m)+':'+String(s%60).padStart(2,'0')};
 window.etatVideo=()=>{if(!vproprio||cur<0)return;navigator.sendBeacon('/video',JSON.stringify({kind:'{kind}',id:+lis[cur].dataset.id,
  titre:lis[cur].dataset.t,t:p.currentTime||0,d:p.duration||0,lecture:!p.paused,vol:p.volume,page:location.search,dev:APPAREIL,
  st:[...p.textTracks].map(t=>t.label),sti:[...p.textTracks].findIndex(t=>t.mode==='showing'),au:audioNoms(),aui:audioIdx}))};
 p.textTracks.addEventListener('change',()=>etatVideo());p.textTracks.addEventListener('addtrack',()=>setTimeout(etatVideo,400));
 p.addEventListener('play',()=>{vproprio=true;etatVideo()});for(const ev of ['pause','seeked','loadedmetadata'])p.addEventListener(ev,()=>etatVideo());  // loadedmetadata : durée connue
 p.addEventListener('volumechange',()=>{clearTimeout(volV);volV=setTimeout(etatVideo,300)});
 setInterval(async()=>{if(!vproprio)return;try{for(const c of await (await fetch('/commande?dev='+APPAREIL)).json()){
  if(c.cmd==='lecture')p.play().catch(()=>{});else if(c.cmd==='pause')p.pause();else if(c.cmd==='volume')p.volume=c.v;
  else if(c.cmd==='deplacer')p.currentTime=Math.max(0,Math.min(p.duration||1e9,p.currentTime+c.v));
  else if(c.cmd==='audio'&&c.v<audioNoms().length)choisirAudio(c.v);
  else if(c.cmd==='soustitres')[...p.textTracks].forEach((t,j)=>t.mode=j===c.v?'showing':'disabled');  // déclenche aussi le rendu .ass
  else if(c.cmd==='suivant')suivant();else if(c.cmd==='jouer'){const i=lis.findIndex(l=>l.dataset.id===c.k);if(i>=0)play(i)}}}catch(e){}},1000);
 vt.querySelectorAll('[data-v]').forEach(b=>b.onclick=()=>commande('deplacer','','video',+b.dataset.v));
 const vtsv=document.getElementById('vtsv');if(vtsv)vtsv.onclick=()=>commande('suivant','','video');
 const envoyerVolV=()=>{vtTouche=Date.now();if(Date.now()-vtEnvoi>200){vtEnvoi=Date.now();commande('volume','','video',vtv.value/100)}};
 vtv.oninput=envoyerVolV;vtv.onchange=()=>{vtEnvoi=0;envoyerVolV()};
 const vts=document.getElementById('vts'),vtsl=document.getElementById('vtsl');let vtsListe='',vtsTouche=0;
 vts.onchange=()=>{vtsTouche=Date.now();commande('soustitres','','video',+vts.value)};
 const vta=document.getElementById('vta'),vtal=document.getElementById('vtal');let vtaListe='',vtaTouche=0;
 vta.onchange=()=>{vtaTouche=Date.now();commande('audio','','video',+vta.value)};
 const vtamp=document.getElementById('vtamp');let dernierEtat=null;
 vtamp.onclick=()=>{const e=dernierEtat;if(e)versAmpli(e.kind,e.id,e.t+(e.lecture&&e.age<30?e.age:0),e.aui||0,false)};
 async function suivreVideo(){try{const e=await (await fetch('/video?dev='+APPAREIL)).json();
  const visible=!!(e.titre&&!e.moi&&e.joignable&&p.paused);vt.hidden=!visible;vdistant=visible&&(e.page===location.search||e.page==='*')&&e.kind==='{kind}';  // * : mpv
  if(!visible)return;const t=e.t+(e.lecture&&e.age<30?e.age:0);
  document.getElementById('vtt').textContent='Sur un autre appareil : '+e.titre+' — '+hms(Math.min(t,e.d||t))+(e.d?' / '+hms(e.d):'')+(e.lecture?'':' (pause)');
  // État inversé tout de suite au clic : deux appuis rapides ne renvoient pas deux fois le même ordre.
  let lect=e.lecture;vtpp.textContent=lect?'⏸':'▶';vtpp.onclick=()=>{commande(lect?'pause':'lecture','','video');lect=!lect;vtpp.textContent=lect?'⏸':'▶'};
  dernierEtat=e;vtamp.hidden=!AMPLI||!!e.mpv;
  if(Date.now()-vtTouche>3000)vtv.value=Math.round((e.vol??1)*100);
  const st=e.st||[],cle=JSON.stringify(st);vtsl.hidden=!st.length;
  if(cle!==vtsListe){vtsListe=cle;vts.replaceChildren(...[['-1','Sans sous-titres'],...st.map((n,j)=>[String(j),n])].map(([v,n])=>{
   const o=document.createElement('option');o.value=v;o.textContent=n;return o}))}
  if(Date.now()-vtsTouche>3000)vts.value=String(e.sti??-1);
  const au=e.au||[],cleA=JSON.stringify(au);vtal.hidden=au.length<2;
  if(cleA!==vtaListe){vtaListe=cleA;vta.replaceChildren(...au.map((n,j)=>{const o=document.createElement('option');o.value=String(j);o.textContent=n;return o}))}
  if(Date.now()-vtaTouche>3000)vta.value=String(e.aui??0)}catch(e){}}
 suivreVideo();setInterval(suivreVideo,2000)}
// Musique : aléatoire (chaque morceau visible une fois) ; bouton répéter : non → tout → un seul morceau → non.
const al=document.getElementById('al'),rp=document.getElementById('rp');let alea=false,repete=0,joues=new Set(),hist=[];  // hist : morceaux joués en aléatoire, pour « précédent »
try{alea=localStorage.getItem('alea')==='1';repete=Math.min(2,+localStorage.getItem('repete')||0)}catch(e){}
const REPETE=['🔁 Répéter','🔁 Répéter tout','🔂 Répéter 1'];
function majRepete(){rp.textContent=REPETE[repete];rp.setAttribute('aria-pressed',repete>0);p.loop=repete===2;  // boucle native
 try{localStorage.setItem('repete',repete)}catch(e){}}
const visibles=()=>lis.map((_,i)=>i).filter(i=>!lis[i].hidden);
function hasard(){if(cur>=0)joues.add(cur);let v=visibles().filter(i=>!joues.has(i));
 if(!v.length){joues.clear();if(!repete)return -1;v=visibles().filter(i=>i!==cur||lis.length===1)}  // nouveau tour, sans rejouer le même
 return v.length?v[Math.floor(Math.random()*v.length)]:-1}
function bascule(b,cle,val){b.setAttribute('aria-pressed',val);try{localStorage.setItem(cle,val?'1':'0')}catch(e){}}
if(al){al.setAttribute('aria-pressed',alea);majRepete();
 al.onclick=()=>{alea=!alea;bascule(al,'alea',alea);joues.clear();hist=[];if(alea&&p.paused)play(hasard())};
 rp.onclick=()=>{repete=(repete+1)%3;majRepete()}}
// File d'attente : les morceaux ajoutés avec « + » passent avant la suite normale (ou aléatoire).
let file=[];const fa=document.getElementById('fa'),fl=document.getElementById('fl');
let glisse=null,derniere=null;
function deplacer(a,b){if(a==null||a===b||b<0||b>=file.length)return;file.splice(b,0,file.splice(a,1)[0]);majFile()}
function bouton(txt,titre,fn){const x=document.createElement('button');x.textContent=txt;x.title=x.ariaLabel=titre;
 x.onclick=e=>{e.stopPropagation();fn()};return x}
function majFile(envoyer=true){fa.hidden=!file.length;fl.replaceChildren(...file.map((i,k)=>{const d=document.createElement('div');
  d.className='fi';d.textContent=(k+1)+'. '+lis[i].dataset.t;d.onclick=()=>{file.splice(k,1);majFile();play(i)};
  // Glisser-déposer pour réorganiser ; ↑ ↓ pour le clavier et les écrans tactiles.
  d.draggable=true;d.ondragstart=e=>{glisse=k;d.classList.add('glisse');e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',k)};
  d.ondragend=()=>{glisse=null;d.classList.remove('glisse')};
  d.ondragover=e=>{e.preventDefault();d.classList.add('cible')};d.ondragleave=()=>d.classList.remove('cible');
  d.ondrop=e=>{e.preventDefault();d.classList.remove('cible');deplacer(glisse,k)};
  d.append(bouton('↑','Monter',()=>deplacer(k,k-1)),bouton('↓','Descendre',()=>deplacer(k,k+1)),
   bouton('×','Retirer de la file',()=>{file.splice(k,1);majFile()}));return d}));
 if(envoyer){derniere=JSON.stringify(file.map(i=>lis[i].dataset.k));  // sauvegarde sur le PC, commune à tous les appareils
  fetch('/file',{method:'POST',body:derniere,keepalive:true}).catch(()=>{})}}
if(fa){document.querySelectorAll('.qa').forEach(b=>b.onclick=e=>{e.stopPropagation();file.push(+b.closest('li').dataset.id);majFile()});
 document.querySelectorAll('.qn').forEach(b=>b.onclick=e=>{e.stopPropagation();file.unshift(+b.closest('li').dataset.id);majFile()});
 document.getElementById('fv').onclick=()=>{file=[];majFile()};
 // File commune : relue sur le PC toutes les 5 s (identifiants stables ; morceaux disparus ignorés).
 // ponytail: le dernier qui écrit gagne ; deux appareils modifiant la file dans la même seconde peuvent s'écraser.
 const parK=new Map(lis.map((l,i)=>[l.dataset.k,i]));
 async function chargerFile(){try{const ks=await (await fetch('/file')).json(),j=JSON.stringify(ks);
  if(j===derniere||glisse!==null)return;derniere=j;file=ks.map(k=>parK.get(k)).filter(i=>i!==undefined);majFile(false)}catch(e){}}
 chargerFile();setInterval(chargerFile,5000);
 // Listes de lecture nommées (sur le PC, communes à tous les appareils) : la file en cours devient une liste, et inversement.
 let listes={};const ls=document.getElementById('ls');
 async function chargerListes(){try{listes=await (await fetch('/listes')).json();const v=ls.value;
  ls.replaceChildren(ls.options[0],...Object.keys(listes).sort().map(n=>{const o=document.createElement('option');o.value=o.textContent=n;return o}));
  ls.value=v in listes?v:''}catch(e){}}
 const envoyerListe=(nom,k)=>fetch('/listes',{method:'POST',body:JSON.stringify({nom,k})}).then(chargerListes);
 document.getElementById('lsc').onclick=()=>{if(!ls.value)return alert("Choisis d'abord une liste.");
  file=file.concat(listes[ls.value].map(k=>parK.get(k)).filter(i=>i!==undefined));majFile();if(p.paused&&cur<0)suivant()};
 document.getElementById('lse').onclick=()=>{if(!file.length)return alert('La file est vide.');const nom=prompt('Nom de la liste ?',ls.value);
  if(nom&&nom.trim()){ls.value='';envoyerListe(nom.trim(),file.map(i=>lis[i].dataset.k)).then(()=>{ls.value=nom.trim()})}};
 document.getElementById('lsx').onclick=()=>{if(ls.value&&confirm(ls.value+' ?'))envoyerListe(ls.value,null)};
 chargerListes();
 // Radio : la file se remplit avec l'artiste du morceau en cours (dossier de 1er niveau), mélangé, et se recharge à la fin.
 // ponytail: « artiste » = dossier ; pas de genre (les tags ne sont pas lus) ; complété au hasard si l'artiste a peu de morceaux.
 const radio=document.getElementById('radio');let radioOn=false;
 const melange=t=>{for(let i=t.length-1;i>0;i--){const j=Math.floor(Math.random()*(i+1));[t[i],t[j]]=[t[j],t[i]]}return t};
 function remplirRadio(){if(cur<0)return;const art=lis[cur].dataset.k.split('/')[0];
  let t=melange(lis.map((l,i)=>i).filter(i=>i!==cur&&lis[i].dataset.k.split('/')[0]===art));
  if(t.length<10)t=t.concat(melange(lis.map((l,i)=>i).filter(i=>i!==cur&&!t.includes(i))).slice(0,10-t.length));
  file=file.concat(t.slice(0,50));majFile()}
 radio.onclick=()=>{radioOn=!radioOn;bascule(radio,'radio',radioOn);if(radioOn){if(cur<0)play(hasard());remplirRadio()}};
 p.addEventListener('play',()=>{if(radioOn&&!file.length)remplirRadio()});
 // Paroles synchronisées (.lrc à côté du morceau) : la ligne en cours est surlignée.
 const pz=document.getElementById('paroles');let lignes=[];
 p.addEventListener('loadstart',async()=>{lignes=[];pz.hidden=true;pz.replaceChildren();const l=lis[cur];if(!l)return;
  try{const r=await fetch('/paroles/'+l.dataset.id);if(!r.ok||lis[cur]!==l)return;
   for(const ln of (await r.text()).split(/\r?\n/)){const ts=[...ln.matchAll(/\[(\d+):(\d+(?:[.:]\d+)?)\]/g)],txt=ln.replace(/\[[^\]]*\]/g,'').trim();
    if(!ts.length&&(!txt||/^\[\w+:/.test(ln)))continue;  // lignes vides, en-têtes [ar:…] [ti:…]
    for(const m of ts.length?ts:[null])lignes.push({t:m?+m[1]*60+parseFloat(m[2].replace(':','.')):-1,txt})}
   lignes.sort((a,b)=>a.t-b.t);pz.replaceChildren(...lignes.map(x=>{const d=document.createElement('div');d.textContent=x.txt||'♪';return d}));pz.hidden=!lignes.length}catch(e){}});
 p.addEventListener('timeupdate',()=>{if(!lignes.length)return;let k=-1;lignes.forEach((x,i)=>{if(x.t>=0&&x.t<=p.currentTime)k=i});
  const on=pz.querySelector('.on'),d=pz.children[k];if(d===on)return;if(on)on.classList.remove('on');
  if(d){d.classList.add('on');pz.scrollTop=d.offsetTop-pz.offsetTop-pz.clientHeight/2+d.clientHeight/2}});
 // Morceau en cours commun : un appareil à l'arrêt suit ce que joue un autre (même morceau, même position, en pause) ;
 // appuyer sur ▶ reprend alors la lecture ici. Les navigateurs interdisent de lancer le son tout seul.
 p.addEventListener('play',()=>{proprio=true;save()});
 for(const ev of ['pointerdown','keydown'])p.addEventListener(ev,()=>{geste=Date.now()});  // curseur déplacé à la main
 const tc=document.getElementById('tc'),tcpp=document.getElementById('tcpp');
 async function suivreEncours(){try{const e=await (await fetch('/encours?dev='+APPAREIL)).json(),i=parK.get(e.k);
  // Télécommande visible si un autre appareil, page ouverte, a le morceau en cours et que celui-ci ne joue pas ici.
  distant=!!(e.k&&!e.moi&&e.joignable&&p.paused);tc.hidden=!distant;
  if(distant&&i!==undefined){document.getElementById('tct').textContent='Sur un autre appareil : '+lis[i].dataset.t+(e.lecture?' (lecture)':' (pause)');
   let lect=e.lecture;tcpp.textContent=lect?'⏸':'▶';tcpp.onclick=()=>{commande(lect?'pause':'lecture');lect=!lect;tcpp.textContent=lect?'⏸':'▶'};
   if(Date.now()-tcvTouche>3000)tcv.value=Math.round((e.vol??1)*100)}  // pas pendant qu'on bouge le curseur
  if(!p.paused||Date.now()-geste<15000||i===undefined)return;const t=e.t+(e.lecture&&e.age<30?e.age:0);  // > 30 s sans nouvelles : appareil éteint
  if(i===cur&&Math.abs(p.currentTime-t)<3)return;proprio=false;
  if(i!==cur){p.addEventListener('loadedmetadata',()=>{p.currentTime=t},{once:true});play(i,false)}else p.currentTime=t}catch(e){}}
 tc.querySelectorAll('[data-c]').forEach(b=>b.onclick=()=>commande(b.dataset.c));
 // Volume à distance : envoyé au plus toutes les 200 ms pendant qu'on fait glisser, et au relâchement.
 const tcv=document.getElementById('tcv');let tcvTouche=0,tcvEnvoi=0;
 const envoyerVol=()=>{tcvTouche=Date.now();if(Date.now()-tcvEnvoi>200){tcvEnvoi=Date.now();fetch('/commande',
  {method:'POST',body:JSON.stringify({cmd:'volume',v:tcv.value/100})}).catch(()=>{})}};
 tcv.oninput=envoyerVol;tcv.onchange=()=>{tcvEnvoi=0;envoyerVol()};
 let volT;p.addEventListener('volumechange',()=>{clearTimeout(volT);volT=setTimeout(save,300)});  // la télécommande voit le volume
 suivreEncours();setInterval(suivreEncours,2000);
 // Appareil qui joue : exécute les ordres de la télécommande (relevés chaque seconde).
 setInterval(async()=>{if(!proprio)return;try{for(const c of await (await fetch('/commande?dev='+APPAREIL)).json()){
  if(c.cmd==='lecture')p.play().catch(()=>{});else if(c.cmd==='pause')p.pause();else if(c.cmd==='suivant')suivant();
  else if(c.cmd==='precedent')precedent();else if(c.cmd==='jouer'&&parK.has(c.k))play(parK.get(c.k));
  else if(c.cmd==='volume')p.volume=c.v}}catch(e){}},1000)}
function suivant(){if(file.length){if(alea&&cur>=0)hist.push(cur);const n=file.shift();majFile();return play(n)}
 if(alea&&al){const n=hasard();if(n>=0&&cur>=0)hist.push(cur);return play(n)}
 let n=cur+1;while(n<lis.length&&lis[n].hidden)n++;if(n>=lis.length&&repete&&al)n=visibles()[0];play(n)}
// Précédent : après 3 s, revient au début du morceau ; sinon morceau d'avant (en aléatoire : celui joué juste avant).
function precedent(){const debut=()=>{p.currentTime=0};if(cur<0||p.currentTime>3)return debut();
 if(alea)return hist.length?play(hist.pop()):debut();
 let n=cur-1;while(n>=0&&lis[n].hidden)n--;if(n<0&&repete)n=visibles().pop();n>=0?play(n):debut()}
// Fin d'un épisode : compte à rebours de 10 s avant le suivant (annulable) ; musique : enchaîne tout de suite.
let suiteT=null;const suite=document.getElementById('suite');
function annulerSuite(){clearInterval(suiteT);suiteT=null;if(suite)suite.hidden=true}
p.onended=()=>{if('{kind}'==='musique')return suivant();if('{kind}'!=='series'||!suite)return;
 let n=cur+1;while(n<lis.length&&lis[n].hidden)n++;if(n>=lis.length)return;
 let r=10;suite.hidden=false;document.getElementById('suite_s').textContent=r;
 suiteT=setInterval(()=>{r--;document.getElementById('suite_s').textContent=r;if(r<=0){annulerSuite();suivant()}},1000)};
if(suite){document.getElementById('suite_ok').onclick=()=>{annulerSuite();suivant()};document.getElementById('suite_x').onclick=annulerSuite;
 p.addEventListener('play',annulerSuite)}
// Séries : « Passer l'intro » jusqu'à la fin du générique mémorisée pour la série (📍 la fixe à la position actuelle).
{const sh=document.querySelector('.show'),bi=document.getElementById('intro'),bm=document.getElementById('marque');
 if(sh&&bi&&bm){let fin=+sh.dataset.intro||0;
  p.addEventListener('timeupdate',()=>{bi.hidden=!(fin&&p.currentTime>1&&p.currentTime<fin-2);bm.hidden=!(p.currentTime>0)});
  bi.onclick=()=>{p.currentTime=fin;bi.hidden=true};
  bm.onclick=async()=>{if(!(p.currentTime>5))return;fin=Math.round(p.currentTime);
   const r=await fetch('/intro',{method:'POST',body:JSON.stringify({serie:sh.dataset.serie,fin})});
   bm.textContent=r.ok?'📍 ✓ '+Math.floor(fin/60)+':'+String(fin%60).padStart(2,'0'):'✖';setTimeout(()=>{bm.textContent=bm.dataset.t},2500)};
  bm.dataset.t=bm.textContent}}
const sv2=()=>distant?commande('suivant'):suivant(),pv2=()=>distant?commande('precedent'):precedent();  // à distance si besoin
if(al){document.getElementById('sv').onclick=sv2;  // marche aussi en « Répéter 1 » : on passe quand même au suivant
 document.getElementById('pv').onclick=pv2;
 try{navigator.mediaSession.setActionHandler('nexttrack',sv2);navigator.mediaSession.setActionHandler('previoustrack',pv2)}
 catch(e){}}  // touches ⏮ ⏭ du clavier / casque
const txt=lis.map(l=>l.textContent.toLowerCase());  // préparé une fois : recherche rapide même avec 10 000 morceaux
// Recherche + filtres (genre, non vus) + tri ; choix gardés dans le navigateur, par page.
const tri=document.getElementById('tri'),genre=document.getElementById('genre'),nonvus=document.getElementById('nonvus'),avecaff=document.getElementById('avecaff');
const aImg=lis.map(l=>!!l.querySelector('img'));  // avec affiche (sans : vidéos perso, formations…)
const CLES={titre:l=>l.dataset.t.toLowerCase(),ajout:l=>-(+l.dataset.ajout||0),annee:l=>-(+l.dataset.annee||0),annee_asc:l=>+l.dataset.annee||9999};
function appliquer(){const s=q.value.toLowerCase(),g=genre?genre.value:'',nv=nonvus&&nonvus.checked,aa=avecaff&&avecaff.checked;
 lis.forEach((l,i)=>l.hidden=!(txt[i].includes(s)&&(!g||(l.dataset.genres||'').split('|').includes(g))
  &&(!nv||!l.classList.contains('vu')&&l.dataset.nonvu!=='0')&&(!aa||aImg[i])));
 if(tri){const c=CLES[tri.value]||CLES.titre,ul=document.getElementById('l');
  [...lis].sort((a,b)=>{const x=c(a),y=c(b);return x<y?-1:x>y?1:0}).forEach(l=>ul.appendChild(l));
  try{localStorage.setItem('filtres_{kind}',JSON.stringify({t:tri.value,g:genre?genre.value:'',n:!!nv,a:!!aa}))}catch(e){}}}
if(tri){try{const f=JSON.parse(localStorage.getItem('filtres_{kind}')||'{}');if(f.t)tri.value=f.t;
  if(genre&&f.g&&[...genre.options].some(o=>o.value===f.g))genre.value=f.g;nonvus.checked=!!f.n;if(avecaff)avecaff.checked=!!f.a}catch(e){}
 for(const el of [tri,genre,nonvus,avecaff])if(el)el.onchange=appliquer;appliquer()}
q.oninput=appliquer;
{const j=new URLSearchParams(location.search).get('jouer');  // venu de l'accueil : lancer la lecture
 if(j!==null){const i=lis.findIndex(l=>l.dataset.id===j);if(i>=0)play(i)}}
// Chromecast (Chrome sur le PC : page sur http://localhost) : la TV lit directement le fichier depuis le PC.
// Il faut --reseau (sinon le Chromecast ne peut pas joindre le PC) ; formats non lus par le Chromecast : conversion HLS.
if(vid&&'{cast}'&&window.chrome&&isSecureContext){window.__onGCastApiAvailable=ok=>{if(!ok)return;
 const ctx=cast.framework.CastContext.getInstance(),M=chrome.cast.media;
 ctx.setOptions({receiverApplicationId:M.DEFAULT_MEDIA_RECEIVER_APP_ID,autoJoinPolicy:chrome.cast.AutoJoinPolicy.ORIGIN_SCOPED});
 const b=document.getElementById('cast');b.hidden=false;b.onclick=async()=>{if(cur<0)return;
  try{if(!ctx.getCurrentSession())await ctx.requestSession()}catch(e){return}
  const l=lis[cur],c=await (await fetch('/cast/{kind}/'+l.dataset.id)).json(),mi=new M.MediaInfo(c.url,c.type);
  if(c.hls){mi.hlsSegmentFormat=M.HlsSegmentFormat.TS;mi.hlsVideoSegmentFormat=M.HlsVideoSegmentFormat.MPEG2_TS}
  mi.metadata=new M.MovieMediaMetadata();mi.metadata.title=l.dataset.t;
  const pistes=[...p.querySelectorAll('track')];
  mi.tracks=pistes.map((t,n)=>{const s=new M.Track(n+1,M.TrackType.TEXT);s.trackContentId=c.base+t.getAttribute('src')+c.q;
   s.trackContentType='text/vtt';s.subtype=M.TextTrackType.SUBTITLES;s.name=t.label;return s});
  const req=new M.LoadRequest(mi);req.currentTime=p.currentTime||0;
  const actif=pistes.findIndex(t=>t.track.mode==='showing');if(actif>=0)req.activeTrackIds=[actif+1];
  try{await ctx.getCurrentSession().loadMedia(req);p.pause()}catch(e){console.warn('Chromecast :',e)}}};
 const s=document.createElement('script');s.src='https://www.gstatic.com/cv/js/sender/v1/cast_sender.js?loadCastFramework=1';document.head.append(s)}
