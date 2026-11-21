// Navigation au clavier / à la télécommande de la TV : flèches = élément le plus proche dans cette direction,
// Entrée = choisir, Retour / Échap = page précédente, Espace = lecture / pause.
(()=>{const lecteur=document.getElementById('p');
document.querySelectorAll('li').forEach(l=>{l.tabIndex=0});
const q=document.getElementById('q');if(q&&matchMedia('(pointer:fine)').matches)q.focus();  // pas sur TV : clavier à l'écran
const cibles=()=>[...document.querySelectorAll('a.tab,li,.carte,button,input,select,video')]
 .filter(e=>!e.hidden&&!e.disabled&&e.offsetParent!==null&&e.getClientRects().length);
const DIR={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]};
document.addEventListener('keydown',e=>{const a=document.activeElement,d=DIR[e.key];
 const saisie=a&&(a.tagName==='INPUT'&&a.type!=='range'||a.tagName==='SELECT');
 if(d){if(saisie&&(d[0]||a.tagName==='SELECT'))return;  // curseur dans la recherche, choix dans un menu
  if(a&&(a.tagName==='VIDEO'||a.tagName==='AUDIO'||a.type==='range')&&d[0])return;  // ←/→ : avance/recul, volume
  const tous=cibles();if(!a||a===document.body||!tous.includes(a)){if(tous[0]){tous[0].focus();e.preventDefault()}return}
  const r=a.getBoundingClientRect(),cx=r.left+r.width/2,cy=r.top+r.height/2;let mieux=null,dist=1e9;
  for(const el of tous){if(el===a)continue;const s=el.getBoundingClientRect();
   const dx=s.left+s.width/2-cx,dy=s.top+s.height/2-cy,avance=d[0]?dx*d[0]:dy*d[1];if(avance<=2)continue;
   if(d[0]&&(s.bottom<=r.top||s.top>=r.bottom))continue;  // ← → : seulement sur la même rangée (et vers ↱ + d'un morceau)
   if(!d[0]&&(d[1]>0?s.top<r.bottom-4:s.bottom>r.top+4))continue;  // ↑ ↓ : vraiment la rangée d'en dessous / d'au-dessus
   if(!d[0]&&el.parentElement.closest('li,.carte'))continue;  // ↑ ↓ : s'arrêter sur le morceau / l'affiche, pas sur ses boutons
   const v=avance+(d[0]?Math.abs(dy):Math.abs(dx))*0.5;/* la rangée la plus proche d'abord */if(v<dist){dist=v;mieux=el}}
  if(mieux){mieux.focus();mieux.scrollIntoView({block:'nearest',inline:'nearest'});e.preventDefault()}}
 else if(e.key==='Enter'&&a&&a.matches('li,.carte')){a.click();e.preventDefault()}
 else if((e.key==='Escape'||e.key==='BrowserBack'||e.key==='Backspace'&&!saisie)&&!document.fullscreenElement){
  if(history.length>1){history.back();e.preventDefault()}}
 else if((e.key===' '||e.key==='MediaPlayPause')&&lecteur&&lecteur.getAttribute('src')!==null&&!saisie&&!(a&&a.matches('button,select,video,audio'))){
  lecteur.paused?lecteur.play().catch(()=>{}):lecteur.pause();e.preventDefault()}})})();
