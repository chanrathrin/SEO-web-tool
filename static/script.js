/* ═══════════════════════════════════════════════════════════════
   SEO Tool + Together AI — Web Port of ImageSEOPromptV4Full.py
   All logic matches Tkinter source exactly.
═══════════════════════════════════════════════════════════════ */

// ── Global state ──────────────────────────────────────────────
let _apiKey    = localStorage.getItem("together_api_key") || "";
let _sessionKey= "";

// Article state
let _sections  = {};          // currentSections
let _aiCounter = 0;           // ai_request_counter

// Image state
let _origImg   = null;        // HTMLImageElement (original_image)
let _origFile  = null;        // File (for FormData upload)
let _cropBlob  = null;        // cropped Blob
let _cropDataUrl = null;      // cropped data URL

// Canvas / crop state (matches ImageToolFrame attrs)
let _zoom      = 1.0;         // zoom_factor
let _baseScale = 1.0;
let _dispScale = 1.0;
let _dispW = 1, _dispH = 1;
let _offX = 0, _offY = 0;    // image_offset_x/y
let _ratio = 1200/366;        // current_ratio
let _lockRatio = true;        // lock_ratio_var
let _safeZone  = true;        // safe_zone_var
let _cropRect  = [120,60,720,243]; // [x1,y1,x2,y2]
let _dragCrop  = false, _dragImg = false;
let _resizeHandle = null;
let _dragStart = [0,0];
let _startCrop = null, _startOff = null;
const HS = 12; // handle_size

// ── Utils ─────────────────────────────────────────────────────
function setStatus(t){
  document.getElementById("status-text").textContent = "  " + t;
}
function setModalStatus(t){
  document.getElementById("m-status").textContent = t;
}

let _toastTimer = null;
function showToast(msg, ms=1800){
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(()=>el.classList.remove("show"), ms);
}

function copyText(text, statusMsg){
  if(!text || !text.trim()){setStatus("Nothing to copy");return;}
  navigator.clipboard.writeText(text).then(()=>{
    setStatus(statusMsg||"Copied");
    showToast(statusMsg||"Copied");
  }).catch(()=>{
    const t=document.createElement("textarea");
    t.value=text;document.body.appendChild(t);t.select();
    document.execCommand("copy");document.body.removeChild(t);
    setStatus(statusMsg||"Copied");showToast(statusMsg||"Copied");
  });
}

function getKey(){ return _sessionKey || _apiKey || ""; }

function updateBadge(){
  const saved = !!localStorage.getItem("together_api_key");
  const el = document.getElementById("api-badge");
  const active = getKey();
  if(active && saved)       el.textContent = "API: Together key saved";
  else if(active)           el.textContent = "API: Together session key loaded";
  else                      el.textContent = "API: not configured";
}

// ═══════════════════════════════════════════════════════════════
// API SETTINGS POPUP  (APISettingsPopup)
// ═══════════════════════════════════════════════════════════════
function openApiSettings(){
  document.getElementById("api-backdrop").classList.add("open");
  const k = getKey();
  document.getElementById("modal-key").value = k||"";
  setModalStatus(k ? "Loaded current API key into this window"
                   : "Paste your Together AI API key to test and save");
}
function backdropClose(e){
  if(e.target===document.getElementById("api-backdrop"))
    document.getElementById("api-backdrop").classList.remove("open");
}
function toggleShow(){
  document.getElementById("modal-key").type =
    document.getElementById("cb-show").checked ? "text" : "password";
}

async function testKey(){
  const k = document.getElementById("modal-key").value.trim();
  if(!k){alert("Please paste your API key first.");return;}
  setModalStatus("Testing API key...");
  try{
    const r = await fetch("/api/test-key",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({api_key:k})
    });
    const d=await r.json();
    if(d.ok){setModalStatus("API key test passed ✓");alert("API key is valid and ready to use.");}
    else{setModalStatus("API key test failed");alert("Could not verify this Together AI API key.\n\n"+(d.error||""));}
  }catch(e){setModalStatus("API key test failed");alert("Network error: "+e.message);}
}

function saveAndUse(){
  const k=document.getElementById("modal-key").value.trim();
  if(!k){alert("Please paste your API key first.");return;}
  const save=document.getElementById("cb-save").checked;
  if(save){ localStorage.setItem("together_api_key",k); _apiKey=k; }
  _sessionKey=k;
  updateBadge();
  setStatus("Together AI API key loaded successfully");
  setModalStatus("API key applied successfully");
  document.getElementById("api-backdrop").classList.remove("open");
}

function useSession(){
  const k=document.getElementById("modal-key").value.trim();
  if(!k){alert("Please paste your API key first.");return;}
  _sessionKey=k; _apiKey="";
  updateBadge();
  setStatus("Together AI API key loaded successfully");
  setModalStatus("Using API key for this session only");
  document.getElementById("api-backdrop").classList.remove("open");
}

function clearKey(){
  localStorage.removeItem("together_api_key");
  _apiKey="";_sessionKey="";
  document.getElementById("modal-key").value="";
  updateBadge();
  setStatus("API key cleared");
  setModalStatus("Saved API key cleared");
  alert("Saved API key has been removed.");
}

// ═══════════════════════════════════════════════════════════════
// ARTICLE TOOL (ArticleToolFrame)
// ═══════════════════════════════════════════════════════════════
async function processArticle(){
  const url = document.getElementById("url-entry").value.trim();
  const raw = document.getElementById("input-text").value.trim();
  const isPlaceholder = !raw || raw==="Paste your article here...";

  // URL import path (matches process_article in py)
  if(url && /^https?:\/\//i.test(url) && isPlaceholder){
    setStatus("Importing article from URL.");
    try{
      const r=await fetch("/api/fetch-url",{
        method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({url})
      });
      const d=await r.json();
      if(!d.ok){
        const msg=d.error||"Unknown error";
        setStatus(msg.includes("403")?"Import failed: site blocked auto import (403)":
                  "Import failed: "+msg.slice(0,100));
        document.getElementById("output-text").value=d.error||"";
        return;
      }
      document.getElementById("input-text").value=d.text;
      setStatus("Article imported successfully");
      await _processCore();
    }catch(e){setStatus("Import failed: "+e.message.slice(0,100));}
    return;
  }

  if(isPlaceholder){
    document.getElementById("output-text").value="Please paste a news URL or article first.";
    setStatus("Please paste a news URL or article first");
    return;
  }
  await _processCore();
}

async function _processCore(){
  const raw=document.getElementById("input-text").value.trim();
  if(!raw||raw==="Paste your article here..."){
    document.getElementById("output-text").value="Please paste an article first.";
    setStatus("Please paste an article first");
    return;
  }
  _aiCounter++;
  const myId=_aiCounter;
  setStatus("Generating SEO fields...");

  try{
    const r=await fetch("/api/process-article",{
      method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({text:raw,api_key:getKey()})
    });
    const ct=r.headers.get("content-type")||"";
    if(!ct.includes("application/json")){
      setStatus("Server error "+(r.status===502||r.status===504?"(timeout - try again)":r.status));
      return;
    }
    const d=await r.json();
    if(myId!==_aiCounter)return;
    if(!d.ok){
      document.getElementById("output-text").value=d.error||"Error";
      setStatus(d.error||"Error");
      return;
    }

    _sections={
      focus_keyphrase_copy: d.focus_keyphrase||"",
      seo_title_copy:       d.seo_title||"",
      meta_description_copy:d.meta_description||"",
      slug_copy:            d.slug||"",
      short_summary_copy:   d.short_summary||"",
      h1_copy:              d.h1||"",
      intro_copy:           d.intro||"",
      structure_copy:       d.structure||[],
      wp_html_copy:         d.wp_html||"",
    };

    // render_output_preview — build plain text preview
    let prev="";
    if(d.h1)    prev+=d.h1+"\n\n";
    if(d.intro) prev+=d.intro+"\n\n";
    for(const sec of (d.structure||[])){
      if(sec.h2) prev+=sec.h2+"\n\n";
      for(const sub of (sec.subsections||[])){
        if(sub.h3) prev+=sub.h3+"\n\n";
        if(sub.body){
          prev+=sub.body.split(/\n\n+/).filter(p=>p.trim()).join("\n\n")+"\n\n";
        }
      }
    }
    document.getElementById("output-text").value=prev.trim();
    setStatus("Article SEO output generated");

    // AI SEO — separate async call
    if(getKey()){
      setStatus("Generating SEO fields...");
      try{
        const ar=await fetch("/api/generate-ai-seo",{
          method:"POST",headers:{"Content-Type":"application/json"},
          body:JSON.stringify({api_key:getKey(),h1:d.h1||"",intro:d.intro||"",structure:d.structure||[]})
        });
        const act=ar.headers.get("content-type")||"";
        if(act.includes("application/json")){
          const ad=await ar.json();
          if(myId!==_aiCounter)return;
          if(ad.ok){
            if(ad.focus_keyphrase){document.getElementById("focus-keyphrase").value=ad.focus_keyphrase;_sections.focus_keyphrase_copy=ad.focus_keyphrase;}
            if(ad.seo_title){document.getElementById("seo-title").value=ad.seo_title;_sections.seo_title_copy=ad.seo_title;}
            if(ad.meta_description){document.getElementById("meta-description").value=ad.meta_description;_sections.meta_description_copy=ad.meta_description;}
            setStatus("AI SEO fields ready");
          }else{
            setStatus("Article SEO output generated (AI: "+( ad.error||"failed")+")");
          }
        }
      }catch(e){
        setStatus("Article SEO output generated");
      }
    }
  }catch(e){setStatus("Error: "+e.message);}
}

function clearInput(){
  _aiCounter++;_sections={};
  document.getElementById("url-entry").value="";
  document.getElementById("input-text").value="Paste your article here...";
  document.getElementById("output-text").value="Formatted SEO output will appear here.";
  setStatus("Input cleared");
}

function copyWpHtml(){
  const h=((_sections.wp_html_copy)||"").trim();
  if(!h){setStatus("Generate SEO output first");return;}
  copyText(h,"Copied WordPress HTML");
}

function copySection(name){
  if(!_sections||!Object.keys(_sections).length){setStatus("Generate SEO output first");return;}
  const map={
    "Focus Keyphrase": _sections.focus_keyphrase_copy||"",
    "SEO Title":       _sections.seo_title_copy||"",
    "Meta Description":_sections.meta_description_copy||"",
  };
  const v=(map[name]||"").trim();
  if(!v){setStatus(`No content for ${name}`);return;}
  copyText(v,`Smooth copied: ${name}`);
}

// ═══════════════════════════════════════════════════════════════
// IMAGE TOOL (ImageToolFrame)
// ═══════════════════════════════════════════════════════════════

function triggerUpload(){
  document.getElementById("img-file-input").click();
}

function onImageSelected(ev){
  const file=ev.target.files[0];
  if(!file)return;
  _origFile=file;
  _cropBlob=null;_cropDataUrl=null;
  const url=URL.createObjectURL(file);
  const img=new Image();
  img.onload=()=>{
    _origImg=img;
    _zoom=1.0;
    document.getElementById("zoom-slider").value=1.0;
    _offX=0;_offY=0;
    _resetCrop();
    _redraw();
    document.getElementById("cp-info").textContent=
      `Loaded: ${file.name}  •  ${img.naturalWidth}x${img.naturalHeight} px`;
    setStatus("Image loaded");
    URL.revokeObjectURL(url);
  };
  img.src=url;
  ev.target.value="";
}

// ── Canvas drawing (matches redraw_canvas / draw_crop_overlay) ──
function _canvas(){return document.getElementById("crop-canvas");}
function _ctx(){return _canvas().getContext("2d");}

function _syncSize(){
  const wrap=document.getElementById("canvas-wrap");
  const c=_canvas();
  c.width=wrap.clientWidth||800;
  c.height=wrap.clientHeight||560;
}

// reset_crop_rect
function _resetCrop(){
  const c=_canvas();
  const cw=c.width||800, ch=c.height||560;
  let tw=Math.min(cw-100,Math.max(320,Math.floor(cw*0.72)));
  let th=tw/_ratio;
  if(th>ch-100){th=ch-100;tw=th*_ratio;}
  const x1=(cw-tw)/2,y1=(ch-th)/2;
  _cropRect=[x1,y1,x1+tw,y1+th];
}

function setCropPreset(w,h){
  _ratio=w/Math.max(h,1);_resetCrop();_redraw();
  setStatus(`Crop preset set: ${w}x${h}`);
}

function toggleLockRatio(){
  _lockRatio=!_lockRatio;
  const sw=document.getElementById("sw-lock");
  sw.classList.toggle("on",_lockRatio);
  setStatus(_lockRatio?"Lock ratio enabled":"Lock ratio disabled");
}

function toggleSafeZone(){
  _safeZone=!_safeZone;
  const sw=document.getElementById("sw-safe");
  sw.classList.toggle("on",_safeZone);
  _redraw();
}

function onZoom(v){
  _zoom=parseFloat(v);_redraw();
}

function _redraw(){
  _syncSize();
  const c=_canvas(),ctx=_ctx();
  const cw=c.width,ch=c.height;
  ctx.clearRect(0,0,cw,ch);
  ctx.fillStyle="#031020";ctx.fillRect(0,0,cw,ch);
  if(!_origImg)return;

  const iw=_origImg.naturalWidth,ih=_origImg.naturalHeight;
  _baseScale=Math.min(cw/Math.max(iw,1),ch/Math.max(ih,1));
  _dispScale=_baseScale*_zoom;
  _dispW=Math.max(1,Math.round(iw*_dispScale));
  _dispH=Math.max(1,Math.round(ih*_dispScale));

  if(_offX===0&&_offY===0){
    _offX=(cw-_dispW)/2;
    _offY=(ch-_dispH)/2;
  }
  ctx.drawImage(_origImg,_offX,_offY,_dispW,_dispH);
  _drawOverlay(ctx,cw,ch);
}

// draw_crop_overlay
function _drawOverlay(ctx,cw,ch){
  const [x1,y1,x2,y2]=_cropRect;

  // dark mask outside crop (stipple="gray25" → semi-transparent)
  ctx.fillStyle="rgba(0,0,0,0.45)";
  ctx.fillRect(0,0,cw,y1);
  ctx.fillRect(0,y2,cw,ch-y2);
  ctx.fillRect(0,y1,x1,y2-y1);
  ctx.fillRect(x2,y1,cw-x2,y2-y1);

  // crop rect outline=#5eead4 width=2
  ctx.strokeStyle="#5eead4";ctx.lineWidth=2;ctx.setLineDash([]);
  ctx.strokeRect(x1,y1,x2-x1,y2-y1);

  // safe zone outline=#f59e0b dash=(4,4)
  if(_safeZone){
    const mx=(x2-x1)*0.08,my=(y2-y1)*0.08;
    ctx.strokeStyle="#f59e0b";ctx.lineWidth=1;ctx.setLineDash([4,4]);
    ctx.strokeRect(x1+mx,y1+my,(x2-x1)-mx*2,(y2-y1)-my*2);
    ctx.setLineDash([]);
  }

  // 8 handles: fill=#ffffff outline=#1e40af
  for(const [hx,hy] of _handles()){
    const s=HS/2;
    ctx.fillStyle="#ffffff";
    ctx.strokeStyle="#1e40af";ctx.lineWidth=1;
    ctx.fillRect(hx-s,hy-s,HS,HS);
    ctx.strokeRect(hx-s,hy-s,HS,HS);
  }
}

// get_handle_points
function _handles(){
  const [x1,y1,x2,y2]=_cropRect;
  const mx=(x1+x2)/2,my=(y1+y2)/2;
  return[[x1,y1],[mx,y1],[x2,y1],[x1,my],[x2,my],[x1,y2],[mx,y2],[x2,y2]];
}

// detect_handle
function _detectHandle(x,y){
  const labels=["nw","n","ne","w","e","sw","s","se"];
  const pts=_handles();
  for(let i=0;i<labels.length;i++){
    const[hx,hy]=pts[i];
    if(Math.abs(x-hx)<=HS&&Math.abs(y-hy)<=HS)return labels[i];
  }
  return null;
}
function _inCrop(x,y){const[x1,y1,x2,y2]=_cropRect;return x>=x1&&x<=x2&&y>=y1&&y<=y2;}
function _inImg(x,y){return x>=_offX&&x<=_offX+_dispW&&y>=_offY&&y<=_offY+_dispH;}

// clamp_crop
function _clampCrop(){
  const c=_canvas();
  const cw=c.width,ch=c.height,mw=80,mh=50;
  let[x1,y1,x2,y2]=_cropRect;
  x1=Math.max(0,Math.min(cw-mw,x1));
  y1=Math.max(0,Math.min(ch-mh,y1));
  x2=Math.max(x1+mw,Math.min(cw,x2));
  y2=Math.max(y1+mh,Math.min(ch,y2));
  _cropRect=[x1,y1,x2,y2];
}

// resize_crop
function _resizeCrop(handle,dx,dy){
  let[x1,y1,x2,y2]=_startCrop;
  if(handle.includes("w"))x1+=dx;
  if(handle.includes("e"))x2+=dx;
  if(handle.includes("n"))y1+=dy;
  if(handle.includes("s"))y2+=dy;
  if(_lockRatio){
    const r=_ratio;
    let w=Math.max(80,x2-x1),h=Math.max(50,y2-y1);
    if(Math.abs(dx)>=Math.abs(dy)){
      h=w/r;
      if(handle.includes("n")&&!handle.includes("s"))y1=y2-h;else y2=y1+h;
    }else{
      w=h*r;
      if(handle.includes("w")&&!handle.includes("e"))x1=x2-w;else x2=x1+w;
    }
  }
  _cropRect=[x1,y1,x2,y2];_clampCrop();
}

// Canvas event bindings
(function bindCanvas(){
  window.addEventListener("load",()=>{
    _syncSize();_resetCrop();_redraw();
    const wrap=document.getElementById("canvas-wrap");

    function pos(e){
      const r=wrap.getBoundingClientRect();
      const cx=e.touches?e.touches[0].clientX:e.clientX;
      const cy=e.touches?e.touches[0].clientY:e.clientY;
      return[cx-r.left,cy-r.top];
    }
    function onPress(e){
      const[x,y]=pos(e);
      _resizeHandle=_detectHandle(x,y);
      _dragStart=[x,y];
      _startCrop=[..._cropRect];
      _startOff=[_offX,_offY];
      if(_resizeHandle){_dragCrop=true;_dragImg=false;}
      else if(_inCrop(x,y)){_dragCrop=true;_dragImg=false;}
      else if(_inImg(x,y)){_dragImg=true;_dragCrop=false;}
      else{_dragCrop=false;_dragImg=false;}
      e.preventDefault();
    }
    function onDrag(e){
      const[x,y]=pos(e);
      const dx=x-_dragStart[0],dy=y-_dragStart[1];
      if(_dragImg){_offX=_startOff[0]+dx;_offY=_startOff[1]+dy;_redraw();return;}
      if(_dragCrop){
        if(_resizeHandle){_resizeCrop(_resizeHandle,dx,dy);}
        else{
          const[sx1,sy1,sx2,sy2]=_startCrop;
          const w=sx2-sx1,h=sy2-sy1;
          _cropRect=[sx1+dx,sy1+dy,sx1+dx+w,sy1+dy+h];
          _clampCrop();
        }
        _redraw();
      }
      e.preventDefault();
    }
    function onRelease(){_dragCrop=false;_dragImg=false;_resizeHandle=null;}

    wrap.addEventListener("mousedown",onPress);
    wrap.addEventListener("mousemove",onDrag);
    wrap.addEventListener("mouseup",onRelease);
    wrap.addEventListener("mouseleave",onRelease);
    wrap.addEventListener("touchstart",onPress,{passive:false});
    wrap.addEventListener("touchmove",onDrag,{passive:false});
    wrap.addEventListener("touchend",onRelease);

    // on_mousewheel_zoom
    wrap.addEventListener("wheel",e=>{
      const d=e.deltaY<0?0.1:-0.1;
      _zoom=Math.min(3.0,Math.max(0.5,_zoom+d));
      document.getElementById("zoom-slider").value=_zoom;
      _redraw();e.preventDefault();
    },{passive:false});

    new ResizeObserver(()=>{_syncSize();_redraw();}).observe(wrap);
  });
})();

// apply_crop
function applyCrop(){
  if(!_origImg){setStatus("Please upload an image first");return;}
  const iw=_origImg.naturalWidth,ih=_origImg.naturalHeight;
  const[cx1,cy1,cx2,cy2]=_cropRect;
  const left =Math.max(0,Math.min(iw,Math.round((cx1-_offX)/_dispScale)));
  const top  =Math.max(0,Math.min(ih,Math.round((cy1-_offY)/_dispScale)));
  const right=Math.max(left+1,Math.min(iw,Math.round((cx2-_offX)/_dispScale)));
  const bot  =Math.max(top+1, Math.min(ih,Math.round((cy2-_offY)/_dispScale)));
  const off=document.createElement("canvas");
  off.width=right-left;off.height=bot-top;
  off.getContext("2d").drawImage(_origImg,left,top,right-left,bot-top,0,0,right-left,bot-top);
  _cropDataUrl=off.toDataURL("image/jpeg",0.95);
  off.toBlob(b=>{
    _cropBlob=b;
    setStatus(`Crop applied successfully: ${right-left}x${bot-top} px`);
  },"image/jpeg",0.95);
}

// export_under_100kb
function exportUnder100kb(){
  if(!_origImg&&!_cropBlob){setStatus("Please upload or crop an image first");return;}
  const src=_cropDataUrl||_origDataUrl();
  if(!src){setStatus("Please upload an image first");return;}
  const img=new Image();
  img.onload=()=>{
    let w=img.width,h=img.height;
    if(w<1400){const s=Math.max(1.2,1400/Math.max(w,1));w=Math.round(w*s);h=Math.round(h*s);}
    const off=document.createElement("canvas");
    off.width=w;off.height=h;
    off.getContext("2d").drawImage(img,0,0,w,h);

    const qs=[95,90,85,80,75,70,65,60,55,50,45,40,35,30,25,20,15];
    let qi=0;
    function tryQ(){
      if(qi>=qs.length){shrink(off,qs[qs.length-1]);return;}
      const q=qs[qi++];
      off.toBlob(b=>{
        if(b.size/1024<=100)doSave(b,q);else tryQ();
      },"image/jpeg",q/100);
    }
    function shrink(canvas,q){
      let cw=canvas.width,ch=canvas.height;
      const s=document.createElement("canvas");s.width=cw;s.height=ch;
      s.getContext("2d").drawImage(canvas,0,0);
      function step(){
        s.toBlob(b=>{
          if(b.size/1024<=100||cw<400||ch<200){doSave(b,q);return;}
          cw=Math.round(cw*0.92);ch=Math.round(ch*0.92);
          const t=document.createElement("canvas");t.width=cw;t.height=ch;
          t.getContext("2d").drawImage(s,0,0,cw,ch);
          s.width=cw;s.height=ch;s.getContext("2d").drawImage(t,0,0);
          step();
        },"image/jpeg",q/100);
      }step();
    }
    function doSave(blob,q){
      const url=URL.createObjectURL(blob);
      const a=document.createElement("a");a.href=url;a.download="optimized.jpg";
      document.body.appendChild(a);a.click();document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setStatus(`Image saved successfully: ${(blob.size/1024).toFixed(1)}KB | Quality: ${q}`);
    }
    tryQ();
  };img.src=src;
}

function _origDataUrl(){
  if(!_origImg)return null;
  const c=document.createElement("canvas");
  c.width=_origImg.naturalWidth;c.height=_origImg.naturalHeight;
  c.getContext("2d").drawImage(_origImg,0,0);
  return c.toDataURL("image/jpeg",0.95);
}

// clear_crop_only
function clearCropOnly(){
  _cropBlob=null;_cropDataUrl=null;
  if(_origImg){_resetCrop();_redraw();}
  setStatus("Crop cleared");
}

// generate_seo
async function generateSeo(){
  if(!_origImg&&!_origFile){setStatus("Please upload an image first");return;}
  const kw=document.getElementById("scene-entry").value.trim()||"image SEO";
  const key=getKey();
  setStatus("⏳ Generating image SEO... (may take 10-20s)");

  // use cropped blob or original file
  let blob=_cropBlob||_origFile;
  if(!blob&&_origImg){
    blob=await new Promise(res=>{
      const c=document.createElement("canvas");
      c.width=_origImg.naturalWidth;c.height=_origImg.naturalHeight;
      c.getContext("2d").drawImage(_origImg,0,0);
      c.toBlob(b=>res(b),"image/jpeg",0.95);
    });
  }

  const fd=new FormData();
  fd.append("api_key",key);
  fd.append("keyword",kw);
  fd.append("image",blob,"image.jpg");

  try{
    const r=await fetch("/api/generate-image-seo",{method:"POST",body:fd});
    const ct=r.headers.get("content-type")||"";
    if(!ct.includes("application/json")){
      const txt=await r.text();
      setStatus("Server error: "+(r.status===502||r.status===504?"Request timeout - try smaller image":r.status+" "+r.statusText));
      return;
    }
    const d=await r.json();
    if(!d.ok){setStatus("Image SEO generation failed: "+(d.error||""));return;}
    // apply_result
    document.getElementById("alt-text").value     =d.alt_text||"";
    document.getElementById("img-title").value    =d.img_title||"";
    document.getElementById("caption-text").value =d.caption||"";
    if(d.ai){setStatus("Image SEO generated successfully");}else{const reason=d.ai_error?" ("+d.ai_error+")":"";setStatus("Generated simple image SEO without API"+reason);}
  }catch(e){setStatus("Error: "+e.message);}
}

// copy_alt / copy_title / copy_caption / copy_all
function copyImageField(which){
  const alt    =(document.getElementById("alt-text").value||"").trim();
  const title  =(document.getElementById("img-title").value||"").trim();
  const caption=(document.getElementById("caption-text").value||"").trim();
  const scene  =(document.getElementById("scene-entry").value||"").trim();

  if(which==="alt"){
    if(!alt){setStatus("No Alt Text to copy");return;}
    copyText(alt,"Copied Alt Text");
  }else if(which==="title"){
    if(!title){setStatus("No Img Title to copy");return;}
    copyText(title,"Copied Img Title");
  }else if(which==="caption"){
    if(!caption){setStatus("No Caption to copy");return;}
    copyText(caption,"Copied Caption");
  }else if(which==="all"){
    const content=`Image SEO\n\nKeyword / Scene Notes:\n${scene}\n\nAlt Text:\n${alt}\n\nImg Title:\n${title}\n\nCaption:\n${caption}`;
    copyText(content,"Copied all image SEO fields");
  }
}

// clear_fields
function clearImageFields(){
  document.getElementById("scene-entry").value="";
  document.getElementById("alt-text").value="";
  document.getElementById("img-title").value="";
  document.getElementById("caption-text").value="";
  _origImg=null;_origFile=null;_cropBlob=null;_cropDataUrl=null;
  _offX=0;_offY=0;
  document.getElementById("cp-info").textContent="No image loaded";
  _syncSize();_resetCrop();
  const c=_canvas(),ctx=_ctx();
  ctx.fillStyle="#031020";ctx.fillRect(0,0,c.width,c.height);
  setStatus("Cleared all image SEO fields");
}

// ═══════════════════════════════════════════════════════════════
// INIT
// ═══════════════════════════════════════════════════════════════
(function init(){
  const saved=localStorage.getItem("together_api_key");
  if(saved){_apiKey=saved;_sessionKey=saved;}
  updateBadge();
  // init switch states
  document.getElementById("sw-lock").classList.toggle("on",_lockRatio);
  document.getElementById("sw-safe").classList.toggle("on",_safeZone);
})();
