"""GymPulse AI · Media editor and reels viewer (in-browser components).

media_editor(): the member taps "Choose from your photos" (the phone's own photo picker, which
is how websites get photos: iOS and Android show their privacy picker and share only what the
member picks) or "Take a photo". Then they edit like on social apps:
  * swipe left / right on the photo to change the colour filter
  * add text (drag it, pick a colour and size, plain or with a background)
  * add gym stickers, and the gym's branded frame
  * save as a draft on this phone, or share
Videos (reels, video stories): up to 60 seconds; filter and text are kept as settings and shown
over the video when it plays. The edited photo / video is sent back to Python as base64.

reels_viewer(): full-height vertical reels, swipe up / down, the visible one plays muted (tap to
unmute), double-tap or the heart to like, comments and the author's profile.
"""
import base64
import uuid

import streamlit as st

import gympulse_workspaces as gw

FILTERS = {  # name: CSS filter used when a video plays (photos are filtered pixel by pixel in the editor)
    "Normal": "none", "Vivid": "saturate(1.45) contrast(1.08)", "Warm": "sepia(.25) saturate(1.25) hue-rotate(-8deg)",
    "Cool": "saturate(1.1) hue-rotate(12deg) brightness(1.03)", "Mono": "grayscale(1) contrast(1.1)",
    "Fade": "contrast(.88) brightness(1.08) saturate(.8)", "Noir": "grayscale(1) contrast(1.45) brightness(.92)",
    "Gym": "saturate(1.3) contrast(1.12) hue-rotate(-18deg)",
}
MAX_VIDEO_MB = 45
MAX_VIDEO_SECONDS = 60

_CSS = r"""
:host { all: initial; }
* { box-sizing: border-box; font-family: Inter, -apple-system, system-ui, sans-serif; }
.me { color:#F4F7FB; background: radial-gradient(120% 80% at 0% 0%, rgba(183,243,74,.10), transparent 60%),
      radial-gradient(120% 80% at 100% 100%, rgba(53,211,232,.10), transparent 60%), #070B14;
      border:1px solid rgba(255,255,255,.08); border-radius:24px; padding:16px; }
.hd { display:flex; align-items:center; justify-content:space-between; margin-bottom:12px; }
.hd b { font-size:17px; font-weight:800; letter-spacing:-.2px; }
.ghost { background:transparent; border:none; color:#93A0B4; font-size:15px; font-weight:700; padding:6px 4px; cursor:pointer; }
.pill { border:none; border-radius:999px; padding:12px 18px; font-size:15px; font-weight:800; cursor:pointer;
        background: linear-gradient(135deg,#B7F34A,#35D3E8); color:#0A0F1E; }
.pill.dark { background: rgba(255,255,255,.08); color:#F4F7FB; }
.pick { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
.tile { border-radius:20px; padding:22px 14px; text-align:center; cursor:pointer; background: rgba(255,255,255,.05);
        border:1px solid rgba(255,255,255,.08); font-weight:800; font-size:15px; }
.tile .ic { font-size:30px; display:block; margin-bottom:8px; }
.tile.main { background: linear-gradient(135deg, rgba(183,243,74,.22), rgba(53,211,232,.22)); border-color: rgba(183,243,74,.4); }
.note { color:#93A0B4; font-size:12.5px; line-height:1.5; margin:10px 2px 0; }
.drafts { display:flex; gap:8px; overflow-x:auto; margin-top:14px; padding-bottom:4px; }
.drafts img { width:64px; height:80px; object-fit:cover; border-radius:12px; cursor:pointer; border:2px solid transparent; }
.lbl { font-size:12px; color:#93A0B4; font-weight:700; letter-spacing:.06em; text-transform:uppercase; margin:12px 2px 6px; }
.grid { display:grid; grid-template-columns:repeat(3,1fr); gap:4px; }
.grid img, .grid video { width:100%; aspect-ratio:1/1; object-fit:cover; border-radius:8px; cursor:pointer; }
.stage { position:relative; border-radius:18px; overflow:hidden; background:#000; touch-action: pan-y; }
.stage canvas, .stage video { display:block; width:100%; height:auto; }
.toast { position:absolute; left:50%; top:46%; transform:translate(-50%,-50%); font-size:26px; font-weight:900;
         text-shadow:0 2px 14px rgba(0,0,0,.7); opacity:0; transition:opacity .25s; pointer-events:none; }
.toast.on { opacity:1; }
.ovl { position:absolute; inset:0; pointer-events:none; }
.ovl span { position:absolute; transform:translate(-50%,-50%); font-weight:900; white-space:pre; pointer-events:auto;
            cursor:grab; padding:2px 8px; border-radius:10px; }
.tools { display:flex; gap:8px; margin:12px 0 4px; overflow-x:auto; }
.tool { flex:0 0 auto; border:none; border-radius:14px; padding:10px 14px; background: rgba(255,255,255,.07);
        color:#F4F7FB; font-weight:800; font-size:14px; cursor:pointer; }
.tool.on { background:#B7F34A; color:#0A0F1E; }
.chips { display:flex; gap:6px; overflow-x:auto; padding:6px 0; }
.chip { flex:0 0 auto; border-radius:999px; padding:8px 12px; background: rgba(255,255,255,.07); font-size:13px;
        font-weight:700; cursor:pointer; border:2px solid transparent; }
.chip.on { border-color:#B7F34A; }
.sw { width:28px; height:28px; border-radius:50%; border:2px solid rgba(255,255,255,.35); cursor:pointer; flex:0 0 auto; }
.row { display:flex; gap:8px; align-items:center; }
input[type=text], textarea { width:100%; background: rgba(255,255,255,.06); color:#F4F7FB; border:1px solid rgba(255,255,255,.12);
  border-radius:14px; padding:12px; font-size:15px; outline:none; }
textarea { min-height:84px; resize:vertical; }
input[type=range] { width:100%; accent-color:#B7F34A; }
.foot { display:flex; gap:10px; margin-top:14px; } .foot .pill { flex:1; }
.qk { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
.q { border-radius:18px; padding:14px 6px 12px; text-align:center; cursor:pointer; background: rgba(255,255,255,.06);
     border:1px solid rgba(255,255,255,.08); font-weight:800; font-size:13.5px; display:flex; flex-direction:column; align-items:center; gap:6px; }
.q.off { opacity:.45; }
.qi { width:44px; height:44px; border-radius:14px; display:flex; align-items:center; justify-content:center; font-size:21px; font-weight:900;
      background: linear-gradient(135deg, rgba(183,243,74,.25), rgba(53,211,232,.25)); }
.sub { color:#93A0B4; font-size:12.5px; font-weight:700; }
.libhd { display:flex; justify-content:space-between; align-items:center; margin:16px 2px 4px; } .libhd b { font-size:15px; }
.tg { font-size:12.5px; font-weight:800; border-radius:999px; padding:7px 12px; background: rgba(255,255,255,.07); cursor:pointer; }
.tg.on { background:#B7F34A; color:#0A0F1E; }
.lib { display:flex; flex-direction:column; align-items:center; gap:4px; text-align:center; cursor:pointer; margin-top:6px;
       border-radius:20px; padding:22px 14px; background: linear-gradient(135deg, rgba(183,243,74,.18), rgba(53,211,232,.18));
       border:1px dashed rgba(183,243,74,.45); }
.lib .ic { font-size:30px; } .lib .note { margin:2px 0 0; }
.th { position:relative; cursor:pointer; } .th img, .th video { width:100%; aspect-ratio:3/4; object-fit:cover; border-radius:8px; display:block; }
.th span { position:absolute; right:6px; top:4px; font-size:13px; text-shadow:0 1px 4px rgba(0,0,0,.7); }
.tstage { position:relative; border-radius:18px; overflow:hidden; display:flex; align-items:center; justify-content:center; max-height:62vh; margin:0 auto; width:100%; }
.tstage textarea { background:transparent; border:none; text-align:center; font-size:30px; font-weight:900; min-height:40%; width:88%; resize:none; }
.tstage textarea::placeholder { color:inherit; opacity:.55; }
.tstage .hint { position:absolute; bottom:10px; left:0; right:0; text-align:center; font-size:12px; font-weight:700; opacity:.6; color:#0A0F1E; }
.sw.on { border-color:#B7F34A; border-width:3px; }
.err { color:#FF6B6B; font-size:13px; margin-top:8px; }
.busy { text-align:center; padding:40px 10px; font-weight:800; }
.dots { display:inline-block; width:46px; text-align:left; }
"""

_JS = r"""
const FILTERS = {
  Normal:{}, Vivid:{s:1.45,c:1.08}, Warm:{s:1.2,warm:18}, Cool:{s:1.1,warm:-16,b:1.03}, Mono:{gray:1,c:1.1},
  Fade:{c:.88,b:1.08,s:.8}, Noir:{gray:1,c:1.45,b:.92}, Gym:{s:1.3,c:1.12,tint:[183,243,74],mix:.08}
};
const NAMES = Object.keys(FILTERS);
const COLORS = ['#FFFFFF','#0A0F1E','#B7F34A','#35D3E8','#FF6B6B','#FFB84D','#B388FF'];

function applyFilter(src, name){
  const f = FILTERS[name] || {}; const out = document.createElement('canvas');
  out.width = src.width; out.height = src.height; const x = out.getContext('2d'); x.drawImage(src,0,0);
  if (name === 'Normal') return out;
  const im = x.getImageData(0,0,out.width,out.height), d = im.data;
  const s = f.s ?? 1, c = f.c ?? 1, b = f.b ?? 1, w = f.warm ?? 0, g = f.gray ?? 0, mix = f.mix ?? 0, t = f.tint || [0,0,0];
  for (let i=0;i<d.length;i+=4){
    let r=d[i], gg=d[i+1], bb=d[i+2];
    const l = .299*r + .587*gg + .114*bb;
    r = l + (r-l)*s; gg = l + (gg-l)*s; bb = l + (bb-l)*s;
    if (g) { r = gg = bb = l; }
    r = (r-128)*c+128; gg = (gg-128)*c+128; bb = (bb-128)*c+128;
    r*=b; gg*=b; bb*=b; r+=w; bb-=w;
    if (mix) { r = r*(1-mix)+t[0]*mix; gg = gg*(1-mix)+t[1]*mix; bb = bb*(1-mix)+t[2]*mix; }
    d[i]=r<0?0:r>255?255:r; d[i+1]=gg<0?0:gg>255?255:gg; d[i+2]=bb<0?0:bb>255?255:bb;
  }
  x.putImageData(im,0,0); return out;
}

export default function(component){
  const { data, parentElement, setTriggerValue } = component;
  const D = data || {}; const MODE = D.mode || 'post'; const GYM = D.gym || 'My gym';
  const STICKERS = D.stickers || []; const CSSF = D.cssfilters || {};
  const W = 1080, H = MODE === 'post' ? 1350 : 1920;
  const DKEY = 'gp_drafts_' + (D.draftkey || 'x');
  let root = parentElement.querySelector('.me');
  if (!root) { root = document.createElement('div'); root.className = 'me'; parentElement.appendChild(root); }
  if (root._init) return;                         // already open: keep the member's edits when the page reruns
  root._init = true;

  const st = { files: [], img: null, video: null, vfile: null, fi: 0, items: [], frame: false, tool: 'filter',
               sel: -1, caption: '', base: null, err: '' };
  const title = MODE === 'story' ? 'New story' : MODE === 'reel' ? 'New reel' : 'New post';
  const accept = MODE === 'reel' ? 'video/*' : MODE === 'story' ? 'image/*,video/*' : 'image/*';

  function drafts(){ try { return JSON.parse(localStorage.getItem(DKEY) || '[]'); } catch(e){ return []; } }
  function saveDrafts(a){ try { localStorage.setItem(DKEY, JSON.stringify(a.slice(0,8))); return true; } catch(e){ return false; } }

  const GRADS = [['#B7F34A','#35D3E8'],['#FF6B6B','#FFB84D'],['#B388FF','#35D3E8'],['#0A0F1E','#2B3A67'],
                 ['#FFB84D','#B7F34A'],['#35D3E8','#0A0F1E'],['#FF6B9A','#B388FF'],['#F4F7FB','#C9D2E0']];
  function picker(){
    const ds = drafts().filter(d => d.mode === MODE);
    if (st.lib === undefined) { st.lib = MODE === 'reel' ? 'video' : MODE === 'post' ? 'image' : 'all'; st.multi = false; }
    const acc = st.lib === 'video' ? 'video/*' : st.lib === 'image' ? 'image/*' : 'image/*,video/*';
    const chips = MODE === 'story' ? [['all','All'],['image','Photos'],['video','Videos']] : [];
    root.innerHTML = `<div class="hd"><b>${title}</b><span class="sub">${MODE==='reel'?'Up to '+D.maxsec+'s':''}</span></div>
      <div class="qk">
        <label class="q"><span class="qi">📷</span><span>Camera</span>
          <input id="f2" type="file" accept="${MODE==='reel'?'video/*':MODE==='post'?'image/*':'image/*,video/*'}" capture="environment" hidden></label>
        ${MODE==='reel' ? '' : '<div class="q" id="tx"><span class="qi">Aa</span><span>Text</span></div>'}
        <div class="q ${ds.length?'':'off'}" id="dr"><span class="qi">🗂️</span><span>Drafts${ds.length?' · '+ds.length:''}</span></div>
      </div>
      <div class="libhd"><b>Library</b>
        ${MODE==='reel' ? '' : `<span class="tg ${st.multi?'on':''}" id="mu">${st.multi?'✓ ':''}Select multiple</span>`}</div>
      ${chips.length ? `<div class="chips">${chips.map(([k,l])=>`<span class="chip ${st.lib===k?'on':''}" data-l="${k}">${l}</span>`).join('')}</div>` : ''}
      <label class="lib"><span class="ic">🖼️</span><b>Open my ${st.lib==='video'?'videos':st.lib==='image'?'photos':'photos & videos'}</b>
        <span class="note">Your phone opens its own library. GymPulse only gets what you choose.</span>
        <input id="f1" type="file" accept="${acc}" ${st.multi?'multiple':''} hidden></label>
      ${st.files.length > 1 ? `<div class="lbl">Chosen · tap one to edit</div>${thumbs()}` : ''}
      ${st.err ? `<div class="err">${st.err}</div>` : ''}`;
    root.querySelector('#f1').onchange = e => chosen([...e.target.files]);
    root.querySelector('#f2').onchange = e => chosen([...e.target.files]);
    const mu = root.querySelector('#mu'); if (mu) mu.onclick = () => { st.multi = !st.multi; picker(); };
    root.querySelectorAll('.chip[data-l]').forEach(c => c.onclick = () => { st.lib = c.dataset.l; picker(); });
    const tx = root.querySelector('#tx'); if (tx) tx.onclick = textMode;
    root.querySelector('#dr').onclick = () => ds.length && draftList(ds);
    bindThumbs();
  }
  function thumbs(){
    return `<div class="grid">${st.files.map((f,i)=> f.type.startsWith('video') ?
      `<div class="th" data-i="${i}"><video src="${URL.createObjectURL(f)}" muted playsinline></video><span>▶︎</span></div>` :
      `<div class="th" data-i="${i}"><img src="${URL.createObjectURL(f)}" alt=""></div>`).join('')}</div>`;
  }
  function bindThumbs(){ root.querySelectorAll('.th[data-i]').forEach(el => el.onclick = () => open(st.files[+el.dataset.i])); }
  function draftList(ds){
    root.innerHTML = `<div class="hd"><button class="ghost" id="bk">Back</button><b>Drafts</b><span></span></div>
      <div class="grid">${ds.map((d,i)=>`<div class="th" data-d="${i}"><img src="${d.img}" alt="draft"></div>`).join('')}</div>
      <div class="note">Drafts stay on this phone only.</div>`;
    root.querySelector('#bk').onclick = picker;
    root.querySelectorAll('.th[data-d]').forEach(el => el.onclick = () => {
      const d = ds[+el.dataset.d]; const im = new Image();
      im.onload = () => { st.img = im; st.video = null; st.items = []; st.caption = d.caption || ''; st.fi = 0; st.draftId = d.id; editor(); };
      im.src = d.img; });
  }
  function gradImage(gi){
    const c = document.createElement('canvas'); c.width = W; c.height = H; const x = c.getContext('2d');
    const g = x.createLinearGradient(0, 0, W, H); g.addColorStop(0, GRADS[gi][0]); g.addColorStop(1, GRADS[gi][1]);
    x.fillStyle = g; x.fillRect(0, 0, W, H); return c.toDataURL('image/jpeg', .9);
  }
  function textMode(){
    st.gi = st.gi || 0;
    const dark = gi => ['#0A0F1E','#35D3E8'].includes(GRADS[gi][0]) && gi !== 2;
    function paint(){
      const g = GRADS[st.gi];
      root.innerHTML = `<div class="hd"><button class="ghost" id="bk">Back</button><b>Text</b><button class="ghost" id="nx" style="color:#B7F34A">Next</button></div>
        <div class="tstage" id="ts" style="background:linear-gradient(135deg,${g[0]},${g[1]});aspect-ratio:${W}/${H}">
          <textarea id="tt" placeholder="Type something…" maxlength="160" style="color:${dark(st.gi)?'#F4F7FB':'#0A0F1E'}">${esc(st.ttext||'')}</textarea>
          <div class="hint">Swipe for colours</div></div>
        <div class="chips">${GRADS.map((c,i)=>`<span class="sw ${i===st.gi?'on':''}" data-g="${i}" style="background:linear-gradient(135deg,${c[0]},${c[1]})"></span>`).join('')}</div>`;
      const ta = root.querySelector('#tt'); ta.oninput = () => st.ttext = ta.value;
      root.querySelector('#bk').onclick = picker;
      root.querySelectorAll('.sw[data-g]').forEach(el => el.onclick = () => { st.gi = +el.dataset.g; paint(); });
      const ts = root.querySelector('#ts'); let x0 = null;
      ts.addEventListener('touchstart', e => x0 = e.touches[0].clientX, {passive:true});
      ts.addEventListener('touchend', e => { if (x0 === null) return; const dx = e.changedTouches[0].clientX - x0; x0 = null;
        if (Math.abs(dx) > 40) { st.gi = (st.gi + (dx < 0 ? 1 : GRADS.length - 1)) % GRADS.length; paint(); } });
      root.querySelector('#nx').onclick = () => {
        const t = (st.ttext || '').trim(); if (!t) { ta.focus(); return; }
        const im = new Image();
        im.onload = () => { st.img = im; st.video = null; st.fi = 0; st.frame = false; st.caption = '';
          const lines = t.length > 22 ? t.replace(/(.{1,20})(\s|$)/g, '$1\n').trim() : t;
          st.items = [{text: lines, x:.5, y:.5, size: t.length > 60 ? 64 : 96, color: dark(st.gi) ? '#FFFFFF' : '#0A0F1E', bg:false}];
          editor(); };
        im.src = gradImage(st.gi);
      };
    }
    paint();
  }

  function chosen(files){
    st.err = ''; if (!files.length) return;
    st.files = files;
    if (files.length > 1) return grid();
    open(files[0]);
  }

  function grid(){ picker(); }

  function open(f){
    st.items = []; st.fi = 0; st.frame = false; st.caption = '';
    if (f.type.startsWith('video')) {
      if (f.size > D.maxmb*1024*1024) { st.err = `That video is over ${D.maxmb} MB. Trim it or choose a shorter one.`; return picker(); }
      const v = document.createElement('video'); v.preload = 'metadata'; v.muted = true; v.playsInline = true;
      v.onloadedmetadata = () => {
        if (v.duration > D.maxsec + .5) { st.err = `Videos can be up to ${D.maxsec} seconds.`; return picker(); }
        st.video = v; st.vfile = f; st.img = null; editor(); };
      v.onerror = () => { st.err = "That video couldn't be read on this phone."; picker(); };
      v.src = URL.createObjectURL(f); return;
    }
    const im = new Image();
    im.onload = () => { st.img = im; st.video = null; editor(); };
    im.onerror = () => { st.err = "That photo couldn't be read. Try a JPG or PNG (or set your camera to 'Most compatible')."; picker(); };
    im.src = URL.createObjectURL(f);
  }

  // ---------------- editor
  let canvas, ctx, ovl, toastEl;
  function cover(src, sw, sh){
    const c = document.createElement('canvas'); c.width = W; c.height = H; const x = c.getContext('2d');
    const r = Math.max(W/sw, H/sh); const dw = sw*r, dh = sh*r;
    x.fillStyle = '#000'; x.fillRect(0,0,W,H); x.drawImage(src, (W-dw)/2, (H-dh)/2, dw, dh); return c;
  }
  function rebuild(){ if (st.img) { st.base = applyFilter(cover(st.img, st.img.naturalWidth, st.img.naturalHeight), NAMES[st.fi]); draw(); } }
  function drawItems(x, scale){
    st.items.forEach(it => {
      const fs = it.size*scale; x.font = `900 ${fs}px Inter, system-ui, sans-serif`; x.textAlign='center'; x.textBaseline='middle';
      const lines = it.text.split('\n'); const lh = fs*1.15;
      const wmax = Math.max(...lines.map(l => x.measureText(l).width));
      const cx = it.x*W*scale/ (scale) , cy = it.y*H;
      const px = it.x*(x.canvas.width), py = it.y*(x.canvas.height);
      if (it.bg) { x.fillStyle = it.color === '#FFFFFF' ? 'rgba(10,15,30,.75)' : 'rgba(255,255,255,.92)';
        const bw = wmax+fs*.8, bh = lh*lines.length+fs*.4; roundRect(x, px-bw/2, py-bh/2, bw, bh, fs*.35); x.fill(); }
      x.fillStyle = it.color; if (!it.bg) { x.shadowColor='rgba(0,0,0,.55)'; x.shadowBlur=fs*.25; }
      lines.forEach((l,i) => x.fillText(l, px, py - (lines.length-1)*lh/2 + i*lh)); x.shadowBlur = 0;
    });
  }
  function roundRect(x,a,b,w,h,r){ x.beginPath(); x.moveTo(a+r,b); x.arcTo(a+w,b,a+w,b+h,r); x.arcTo(a+w,b+h,a,b+h,r);
    x.arcTo(a,b+h,a,b,r); x.arcTo(a,b,a+w,b,r); x.closePath(); }
  function drawFrame(x){
    const w = x.canvas.width, h = x.canvas.height, band = Math.max(70, h/11);
    x.fillStyle = 'rgba(7,11,20,.85)'; x.fillRect(0, h-band, w, band);
    x.fillStyle = '#fff'; x.font = `900 ${band*.42}px Inter, system-ui, sans-serif`; x.textAlign='left'; x.textBaseline='middle';
    x.fillText(GYM.toUpperCase(), band*.35, h-band/2);
    x.fillStyle = '#B7F34A'; x.font = `700 ${band*.26}px Inter, system-ui, sans-serif`; x.textAlign='right';
    x.fillText('GymPulse AI', w-band*.35, h-band/2);
  }
  function draw(){
    if (!canvas || !st.base) return;
    ctx.clearRect(0,0,W,H); ctx.drawImage(st.base,0,0); drawItems(ctx, 1); if (st.frame) drawFrame(ctx);
  }
  function toast(t){ toastEl.textContent = t; toastEl.classList.add('on'); clearTimeout(toastEl._t);
    toastEl._t = setTimeout(()=>toastEl.classList.remove('on'), 700); }
  function setFilter(i){ st.fi = (i+NAMES.length)%NAMES.length; toast(NAMES[st.fi]);
    if (st.img) rebuild(); else if (st.video) { st.video.style.filter = CSSF[NAMES[st.fi]] || 'none'; }
    paintTools(); }

  function editor(){
    root.innerHTML = `<div class="hd"><button class="ghost" id="bk">Back</button><b>Edit</b>
        <button class="ghost" id="nx" style="color:#B7F34A">Next</button></div>
      <div class="stage" id="stage"><div class="toast" id="toast"></div><div class="ovl" id="ovl"></div></div>
      <div class="tools" id="tools"></div><div id="panel"></div>
      <div class="note">Swipe left or right on the ${st.video?'video':'photo'} to change the colour.</div>`;
    const stage = root.querySelector('#stage'); toastEl = root.querySelector('#toast'); ovl = root.querySelector('#ovl');
    if (st.video) {
      const v = st.video; v.style.filter = CSSF[NAMES[st.fi]] || 'none'; v.loop = true; v.controls = false;
      v.style.aspectRatio = MODE === 'post' ? '4/5' : '9/16'; v.style.objectFit = 'cover'; v.style.width = '100%';
      stage.insertBefore(v, stage.firstChild); v.play().catch(()=>{});
    } else {
      canvas = document.createElement('canvas'); canvas.width = W; canvas.height = H; ctx = canvas.getContext('2d');
      stage.insertBefore(canvas, stage.firstChild); rebuild();
    }
    // swipe for filters, drag for text
    let sx=0, sy=0, drag=-1, moved=false;
    stage.addEventListener('pointerdown', e => { sx=e.clientX; sy=e.clientY; moved=false;
      const r = stage.getBoundingClientRect(); const fx=(e.clientX-r.left)/r.width, fy=(e.clientY-r.top)/r.height;
      drag = hit(fx, fy); if (drag>=0) { st.sel = drag; stage.setPointerCapture(e.pointerId); } });
    stage.addEventListener('pointermove', e => { if (drag<0) return; const r = stage.getBoundingClientRect();
      st.items[drag].x = Math.min(.97,Math.max(.03,(e.clientX-r.left)/r.width));
      st.items[drag].y = Math.min(.97,Math.max(.03,(e.clientY-r.top)/r.height)); moved=true; paintItems(); });
    stage.addEventListener('pointerup', e => { const dx = e.clientX-sx, dy = e.clientY-sy;
      if (drag<0 && Math.abs(dx)>40 && Math.abs(dx)>Math.abs(dy)) setFilter(st.fi + (dx<0?1:-1));
      drag=-1; });
    root.querySelector('#bk').onclick = picker; root.querySelector('#nx').onclick = details;
    paintTools(); paintItems();
  }
  function hit(fx, fy){ for (let i=st.items.length-1;i>=0;i--){ const it=st.items[i];
      if (Math.abs(fx-it.x) < .28 && Math.abs(fy-it.y) < it.size/H*1.4) return i; } return -1; }
  function paintItems(){
    if (st.img) { ovl.innerHTML=''; draw(); return; }
    ovl.innerHTML = st.items.map(it => `<span style="left:${it.x*100}%;top:${it.y*100}%;color:${it.color};
      font-size:${it.size/W*100}cqw;${it.bg?`background:${it.color==='#FFFFFF'?'rgba(10,15,30,.75)':'rgba(255,255,255,.92)'}`:'text-shadow:0 2px 10px rgba(0,0,0,.6)'}">${esc(it.text)}</span>`).join('');
    ovl.style.containerType = 'inline-size'; if (st.frame) ovl.innerHTML += `<span style="left:50%;top:95%;width:100%;transform:translate(-50%,-50%);
      background:rgba(7,11,20,.85);color:#fff;font-size:4cqw;border-radius:0;text-align:left;padding:2.5cqw 4cqw">${esc(GYM.toUpperCase())}</span>`;
  }
  function esc(t){ return String(t).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
  function paintTools(){
    const tools = root.querySelector('#tools'); if (!tools) return;
    const T = [['filter','🎨 Filters'],['text','Aa Text'],['sticker','✨ Stickers'],['frame', st.frame ? '▣ Frame on' : '▢ Frame']];
    tools.innerHTML = T.map(([k,l]) => `<button class="tool ${st.tool===k||(k==='frame'&&st.frame)?'on':''}" data-k="${k}">${l}</button>`).join('');
    tools.querySelectorAll('.tool').forEach(b => b.onclick = () => { const k=b.dataset.k;
      if (k==='frame') { st.frame=!st.frame; paintItems(); } else st.tool=k; paintTools(); });
    const p = root.querySelector('#panel');
    if (st.tool === 'filter') {
      p.innerHTML = `<div class="chips">${NAMES.map((n,i)=>`<span class="chip ${i===st.fi?'on':''}" data-i="${i}">${n}</span>`).join('')}</div>`;
      p.querySelectorAll('.chip').forEach(c => c.onclick = () => setFilter(+c.dataset.i));
    } else if (st.tool === 'text') {
      const it = st.items[st.sel];
      p.innerHTML = `<div class="row"><input type="text" id="tx" placeholder="Type something…" value="${it?esc(it.text):''}">
          <button class="tool" id="add">${it?'Update':'Add'}</button></div>
        <div class="chips">${COLORS.map(c=>`<span class="sw" data-c="${c}" style="background:${c};${it&&it.color===c?'border-color:#B7F34A':''}"></span>`).join('')}
          <span class="chip ${it&&it.bg?'on':''}" id="bgt">Background</span>${it?'<span class="chip" id="del">Remove</span>':''}</div>
        <input type="range" id="sz" min="40" max="200" value="${it?it.size:90}">`;
      const tx = p.querySelector('#tx');
      p.querySelector('#add').onclick = () => { const v = tx.value.trim(); if (!v) return;
        if (it) it.text = v; else { st.items.push({text:v, x:.5, y:.4, size:+p.querySelector('#sz').value, color:'#FFFFFF', bg:false});
          st.sel = st.items.length-1; } paintItems(); paintTools(); };
      p.querySelectorAll('.sw').forEach(s => s.onclick = () => { const t = st.items[st.sel]; if (t) { t.color = s.dataset.c; paintItems(); paintTools(); } });
      p.querySelector('#bgt').onclick = () => { const t = st.items[st.sel]; if (t) { t.bg = !t.bg; paintItems(); paintTools(); } };
      p.querySelector('#sz').oninput = e => { const t = st.items[st.sel]; if (t) { t.size = +e.target.value; paintItems(); } };
      const del = p.querySelector('#del'); if (del) del.onclick = () => { st.items.splice(st.sel,1); st.sel=-1; paintItems(); paintTools(); };
    } else if (st.tool === 'sticker') {
      p.innerHTML = `<div class="chips">${STICKERS.map((s,i)=>`<span class="chip" data-i="${i}">${esc(s)}</span>`).join('')}</div>`;
      p.querySelectorAll('.chip').forEach(c => c.onclick = () => { st.items.push({text: STICKERS[+c.dataset.i], x:.5, y:.18, size:80,
        color:'#0A0F1E', bg:true}); st.sel = st.items.length-1; paintItems(); });
    }
  }

  // ---------------- details and share
  function details(){
    const thumb = st.img ? canvas.toDataURL('image/jpeg', .6) : '';
    root.innerHTML = `<div class="hd"><button class="ghost" id="bk">Back</button><b>${title}</b><span></span></div>
      <div class="row" style="align-items:flex-start">${thumb?`<img src="${thumb}" style="width:84px;border-radius:12px">`:''}
        <textarea id="cap" placeholder="${MODE==='story'?'Add a caption (optional)':'Write a caption…'}">${esc(st.caption)}</textarea></div>
      <div class="foot">${st.img?'<button class="pill dark" id="dr">Save draft</button>':''}
        <button class="pill" id="go">Share ${MODE==='story'?'story':MODE==='reel'?'reel':'post'}</button></div>
      <div id="msg" class="note"></div>`;
    root.querySelector('#bk').onclick = editor;
    const cap = root.querySelector('#cap'); cap.oninput = () => st.caption = cap.value;
    const dr = root.querySelector('#dr');
    if (dr) dr.onclick = () => { const a = drafts().filter(d => d.id !== st.draftId);
      const ok = saveDrafts([{id: st.draftId || String(Date.now()), mode: MODE, caption: st.caption,
        img: canvas.toDataURL('image/jpeg', .78)}, ...a]);
      root.querySelector('#msg').textContent = ok ? 'Saved on this phone. Find it under Drafts next time.' :
        "This phone's storage is full: share it now or delete old drafts."; };
    root.querySelector('#go').onclick = share;
  }

  async function share(){
    root.dataset.busy = '1';
    root.innerHTML = `<div class="busy">Sharing<span class="dots">…</span></div>`;
    const caption = st.caption.trim();
    if (st.img) {
      const out = document.createElement('canvas'); out.width = W; out.height = H; const x = out.getContext('2d');
      x.drawImage(st.base,0,0); drawItems(x,1); if (st.frame) drawFrame(x);
      const data = out.toDataURL('image/jpeg', .86).split(',')[1];
      if (st.draftId) saveDrafts(drafts().filter(d => d.id !== st.draftId));
      setTriggerValue('submit', {type:'image', data, caption, nonce: Date.now()});
      return;
    }
    // video: a poster frame, then the file itself
    const v = st.video; let poster = '';
    try { const c = document.createElement('canvas'); c.width = 720; c.height = Math.round(720*v.videoHeight/(v.videoWidth||1)) || 1280;
      c.getContext('2d').drawImage(v,0,0,c.width,c.height); poster = c.toDataURL('image/jpeg', .7).split(',')[1]; } catch(e) {}
    const buf = await st.vfile.arrayBuffer(); let bin = ''; const bytes = new Uint8Array(buf);
    for (let i=0;i<bytes.length;i+=0x8000) bin += String.fromCharCode.apply(null, bytes.subarray(i,i+0x8000));
    setTriggerValue('submit', {type:'video', data: btoa(bin), mime: st.vfile.type || 'video/mp4', poster, caption,
      filter: NAMES[st.fi], items: st.items, frame: st.frame, duration: v.duration || 0, nonce: Date.now()});
  }

  picker();
}
"""

_editor = None


def _component():
    global _editor
    if _editor is None:
        _editor = st.components.v2.component("gp_media_editor", css=_CSS, js=_JS)
    return _editor


def media_editor(mode, gym_name, key, stickers=(), draftkey="x"):
    """Show the editor. Returns the shared media once ({type, data(bytes), caption, …}) or None."""
    import gympulse_engage as ge
    stickers = [s for s in (stickers or ge.STICKERS) if s] + [f"At {gym_name} 💪"]
    holder = f"{key}_payload"

    def _keep():
        v = st.session_state.get(key)
        sub = getattr(v, "submit", None) if v is not None else None
        if sub is None and isinstance(v, dict):
            sub = v.get("submit")
        if sub:
            st.session_state[holder] = sub

    _component()(key=key, data={"mode": mode, "gym": gym_name, "stickers": stickers, "cssfilters": FILTERS,
                               "maxmb": MAX_VIDEO_MB, "maxsec": MAX_VIDEO_SECONDS, "draftkey": draftkey},
                 on_submit_change=_keep)
    sub = st.session_state.pop(holder, None)
    if not sub:
        return None
    try:
        out = dict(sub)
        out["bytes"] = base64.b64decode(sub.get("data") or "")
        out["poster_bytes"] = base64.b64decode(sub.get("poster") or "") if sub.get("poster") else b""
        return out
    except Exception:
        return None


def store_media(sc, gym_id, media):
    """Upload the shared media. Returns (photo_url or None, meta dict)."""
    import gympulse_community as gcom
    if media["type"] == "image":
        return gcom._store_photo(sc, gym_id, media["bytes"]), {}
    ext = {"video/quicktime": "mov", "video/webm": "webm"}.get(media.get("mime"), "mp4")
    path = f"{gym_id}/v_{uuid.uuid4().hex}.{ext}"
    store = sc.storage.from_(gcom.BUCKET)
    store.upload(path, media["bytes"], {"content-type": media.get("mime") or "video/mp4"})
    url = store.get_public_url(path)
    if isinstance(url, dict):
        url = url.get("publicURL") or url.get("publicUrl") or ""
    poster = gcom._store_photo(sc, gym_id, media["poster_bytes"]) if media.get("poster_bytes") else None
    meta = {"video": str(url).split("?")[0], "filter": media.get("filter") or "Normal",
            "items": media.get("items") or [], "frame": bool(media.get("frame")),
            "duration": round(float(media.get("duration") or 0), 1)}
    return poster, meta


def video_html(meta, poster=None, gym_name="", autoplay=False, height=None):
    """A video with its filter and text shown on top, for the feed and stories."""
    if not meta or not meta.get("video"):
        return ""
    f = FILTERS.get(meta.get("filter") or "Normal", "none")
    items = "".join(
        f'<span style="position:absolute;left:{float(i.get("x", .5)) * 100}%;top:{float(i.get("y", .5)) * 100}%;'
        f'transform:translate(-50%,-50%);font-weight:900;white-space:pre;color:{gw._esc(i.get("color") or "#fff")};'
        f'font-size:{float(i.get("size", 90)) / 1080 * 100}cqw;padding:2px 8px;border-radius:10px;'
        + (f'background:{"rgba(10,15,30,.75)" if i.get("color") == "#FFFFFF" else "rgba(255,255,255,.92)"};'
           if i.get("bg") else "text-shadow:0 2px 10px rgba(0,0,0,.6);")
        + f'">{gw._esc(i.get("text"))}</span>' for i in meta.get("items") or [])
    frame = (f'<div style="position:absolute;left:0;right:0;bottom:0;background:rgba(7,11,20,.85);color:#fff;'
             f'font-weight:900;font-size:4cqw;padding:2.5cqw 4cqw">{gw._esc(gym_name.upper())}</div>'
             if meta.get("frame") else "")
    auto = "autoplay muted loop" if autoplay else "muted loop"
    return (f'<div style="position:relative;container-type:inline-size;border-radius:16px;overflow:hidden;background:#000;'
            f'margin:6px 0">'
            f'<video src="{gw._esc(meta["video"])}" {auto} playsinline controls preload="metadata" '
            f'{f"poster={chr(34)}{gw._esc(poster)}{chr(34)}" if poster else ""} '
            f'style="width:100%;display:block;filter:{f};{f"max-height:{height};" if height else ""}object-fit:cover"></video>'
            f'<div style="position:absolute;inset:0;pointer-events:none">{items}{frame}</div></div>')


# ------------------------------------------------------------------ reels viewer
_RCSS = r"""
:host { all: initial; }
* { box-sizing: border-box; font-family: Inter, -apple-system, system-ui, sans-serif; }
.rv { height: 78vh; overflow-y: auto; scroll-snap-type: y mandatory; border-radius: 22px; background:#000; scrollbar-width:none; }
.rv::-webkit-scrollbar { display:none; }
.r { position:relative; height:78vh; scroll-snap-align:start; display:flex; align-items:center; justify-content:center;
     container-type:inline-size; overflow:hidden; }
.r video { width:100%; height:100%; object-fit:cover; }
.grad { position:absolute; inset:auto 0 0 0; height:42%; background:linear-gradient(transparent, rgba(0,0,0,.75)); pointer-events:none; }
.ov span.t { position:absolute; transform:translate(-50%,-50%); font-weight:900; white-space:pre; padding:2px 8px; border-radius:10px; }
.side { position:absolute; right:10px; bottom:96px; display:flex; flex-direction:column; gap:18px; align-items:center; }
.btn { background:none; border:none; color:#fff; font-size:13px; font-weight:800; display:flex; flex-direction:column;
       align-items:center; gap:4px; cursor:pointer; text-shadow:0 1px 8px rgba(0,0,0,.6); }
.btn .i { font-size:30px; line-height:1; }
.who { position:absolute; left:14px; right:76px; bottom:22px; color:#fff; }
.who b { font-size:15px; cursor:pointer; } .who p { margin:6px 0 0; font-size:14px; line-height:1.4; opacity:.92; }
.av { width:34px; height:34px; border-radius:50%; object-fit:cover; vertical-align:middle; margin-right:8px;
      background:linear-gradient(135deg,#B7F34A,#35D3E8); display:inline-flex; align-items:center; justify-content:center;
      color:#0A0F1E; font-weight:900; font-size:13px; }
.heart { position:absolute; left:50%; top:45%; transform:translate(-50%,-50%) scale(.2); font-size:110px; opacity:0;
         transition: all .35s cubic-bezier(.2,1.4,.4,1); pointer-events:none; }
.heart.on { transform:translate(-50%,-50%) scale(1); opacity:1; }
.mute { position:absolute; top:14px; right:14px; background:rgba(0,0,0,.45); color:#fff; border:none; border-radius:999px;
        padding:6px 10px; font-size:13px; font-weight:800; }
.empty { color:#93A0B4; text-align:center; padding:80px 20px; font-weight:700; }
"""

_RJS = r"""
export default function(component){
  const { data, parentElement, setTriggerValue } = component;
  const R = (data && data.reels) || []; const CSSF = (data && data.cssfilters) || {};
  let root = parentElement.querySelector('.rv');
  const scrollTop = root ? root.scrollTop : 0;
  if (!root) { root = document.createElement('div'); root.className = 'rv'; parentElement.appendChild(root); }
  if (!R.length) { root.innerHTML = '<div class="empty">No reels yet. Be the first: tap New reel 🎬</div>'; return; }
  const esc = t => String(t ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
  root.innerHTML = R.map((r,i) => `<div class="r" data-i="${i}">
      <video src="${esc(r.video)}" ${r.poster?`poster="${esc(r.poster)}"`:''} muted loop playsinline preload="metadata"
        style="filter:${CSSF[r.filter]||'none'}"></video>
      <div class="ov">${(r.items||[]).map(t=>`<span class="t" style="left:${t.x*100}%;top:${t.y*100}%;color:${esc(t.color)};
        font-size:${t.size/1080*100}cqw;${t.bg?`background:${t.color==='#FFFFFF'?'rgba(10,15,30,.75)':'rgba(255,255,255,.92)'}`:'text-shadow:0 2px 10px rgba(0,0,0,.6)'}">${esc(t.text)}</span>`).join('')}</div>
      <div class="grad"></div><div class="heart">❤️</div><button class="mute">🔇</button>
      <div class="side">
        <button class="btn lk"><span class="i">${r.liked?'❤️':'🤍'}</span>${r.likes||''}</button>
        <button class="btn cm"><span class="i">💬</span>${r.comments||''}</button>
      </div>
      <div class="who"><b class="pr">${r.avatar?`<img class="av" src="${esc(r.avatar)}">`:`<span class="av">${esc(r.initials)}</span>`}${esc(r.author)}</b>
        ${r.caption?`<p>${esc(r.caption)}</p>`:''}</div></div>`).join('');
  root.scrollTop = scrollTop;
  let unmuted = false;
  const vids = [...root.querySelectorAll('video')];
  const io = new IntersectionObserver(es => es.forEach(e => { const v = e.target;
    if (e.isIntersecting && e.intersectionRatio > .6) { v.muted = !unmuted; v.play().catch(()=>{}); } else v.pause(); }),
    { root, threshold: [0, .6, 1] });
  vids.forEach(v => io.observe(v));
  root.querySelectorAll('.r').forEach(el => {
    const r = R[+el.dataset.i]; const v = el.querySelector('video'); let last = 0;
    el.querySelector('.mute').onclick = e => { e.stopPropagation(); unmuted = !unmuted; vids.forEach(x => x.muted = !unmuted);
      root.querySelectorAll('.mute').forEach(b => b.textContent = unmuted ? '🔊' : '🔇'); };
    el.addEventListener('click', e => { if (e.target.closest('button,.pr')) return; const now = Date.now();
      if (now - last < 320) { const h = el.querySelector('.heart'); h.classList.add('on'); setTimeout(()=>h.classList.remove('on'), 700);
        if (!r.liked) setTriggerValue('like', {id: r.id, n: now}); }
      else { v.paused ? v.play() : v.pause(); } last = now; });
    el.querySelector('.lk').onclick = e => { e.stopPropagation(); setTriggerValue('like', {id: r.id, n: Date.now()}); };
    el.querySelector('.cm').onclick = e => { e.stopPropagation(); setTriggerValue('comments', {id: r.id, n: Date.now()}); };
    el.querySelector('.pr').onclick = e => { e.stopPropagation(); if (r.member_id) setTriggerValue('profile', {id: r.member_id, n: Date.now()}); };
  });
}
"""

_viewer = None


def reels_viewer(reels, key="gp_reels"):
    """Show reels. Returns ("like" | "comments" | "profile", id) once after a tap, or None."""
    global _viewer
    if _viewer is None:
        _viewer = st.components.v2.component("gp_reels_viewer", css=_RCSS, js=_RJS)
    holder = f"{key}_evt"

    def mk(name):
        def cb():
            v = st.session_state.get(key)
            val = getattr(v, name, None) if v is not None else None
            if val is None and isinstance(v, dict):
                val = v.get(name)
            if val:
                st.session_state[holder] = (name, val.get("id"))
        return cb

    _viewer(key=key, data={"reels": reels, "cssfilters": FILTERS},
            on_like_change=mk("like"), on_comments_change=mk("comments"), on_profile_change=mk("profile"))
    return st.session_state.pop(holder, None)
