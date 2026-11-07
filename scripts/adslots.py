"""站群自有版位（2026-11-07，Charlie 裁定；規格 CoWork/Charlie/2026-11-07/site-ad-slots/site-ad-slots-spec.md）。

三種版位，只放首頁與文章相關頁，百科／數據頁一律不放：
  home_hero    首頁主推位（「下一站」卡正下方）
  native_list  列表原生（首頁「深度文章」格、/articles/ 的第 3 張）
  native_end   文末原生（文章頁內文結束、上下篇導覽之前）

⚠️ 本站站規原本是「100% 靜態、零 client fetch」。Charlie 11/7 裁定「版位例外」：
   內容仍零 client fetch；只有版位會在瀏覽器端讀 twtools.cc/ad-slots.json。
   百科／數據頁的「零 client fetch」測試一律不動，版位也絕不放進那些頁面。

為什麼 HTML 只放預設卡、廣告本身在瀏覽器端換上：
  - 換檔要準時，不能等 racing 每週一次的重建；
  - 廣告文字不進 AI 讀到的 HTML，AI 不會把廣告當成本站內容引用。

讀不到設定檔（網路、404、格式錯）→ 保留 build 時寫好的預設卡；預設卡尺寸與廣告卡一致，不跳版。
"""
import hashlib
import html as html_lib
import pathlib

SITE_KEY = "racing"                       # ad-slots.json 的 sites 欄位用這個值
CONFIG_URL = "https://twtools.cc/ad-slots.json"

# 預設卡：讀不到設定檔時顯示。文字直接取 racinglib.SISTER_SITES（不另外編文案）。
FALLBACK = {
    "home_hero": ("@baseball — 中職 CPBL＋MLB 深度戰報", "https://baseball.twtools.cc/"),
    "native_list": ("籃球數據誌 — NBA・台灣職籃・HBL 戰績與數據", "https://basketball.twtools.cc/"),
    "native_end": ("籃球數據誌 — NBA・台灣職籃・HBL 戰績與數據", "https://basketball.twtools.cc/"),
}

AD_CSS = """
.ad-slot{position:relative;display:block;text-decoration:none;color:inherit;border:1px solid var(--line);
  border-radius:var(--radius);background:var(--surface);overflow:hidden}
.ad-slot:hover,.ad-slot:focus-visible{border-color:var(--accent-line)}
.ad-label{position:absolute;top:8px;right:8px;z-index:1;font-size:11px;line-height:1;padding:4px 7px;
  border-radius:4px;background:rgba(0,0,0,.62);color:#fff;letter-spacing:1px}
.ad-media{display:block;width:100%;aspect-ratio:1200/630;object-fit:cover;
  background:linear-gradient(135deg,var(--accent-soft),var(--surface))}
.ad-media-fb{display:flex;align-items:center;justify-content:center;padding:12px;text-align:center;
  font-weight:800;font-size:15px;color:var(--fg-soft)}
.ad-t{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
  font-size:16px;line-height:1.45;font-weight:800;margin:0}
.ad-d{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;
  color:var(--dim);font-size:13px;line-height:1.7;margin:4px 0 0}
.ad-cta{color:var(--accent);font-size:13px;font-weight:700;margin-top:6px;display:block}
.ad-body{display:block}
/* 橫式（主推位、文末）：固定高度，換卡不跳版；標籤壓在左側圖上，不擋文字 */
.ad-row{display:flex}
.ad-row .ad-label{left:8px;right:auto}
.ad-row .ad-media{flex:0 0 auto;aspect-ratio:auto;height:100%}
.ad-row .ad-body{min-width:0;display:flex;flex-direction:column;justify-content:center}
.ad-hero{height:132px;margin:14px 0 6px}
.ad-hero .ad-media{width:251px}
.ad-hero .ad-body{padding:14px 18px}
.ad-end{height:112px;max-width:560px;margin:28px 0 8px}
.ad-end .ad-media{width:213px}
.ad-end .ad-body{padding:12px 16px}
@media (max-width:719px){
  .ad-hero{height:120px}
  .ad-hero .ad-media,.ad-end .ad-media{width:120px}
  .ad-row .ad-body{padding:10px 12px}
  .ad-hero .ad-t{font-size:15px}
  .ad-row .ad-d{-webkit-line-clamp:1}
}
/* 列表原生：外觀跟文章卡一樣 */
.ad-native .ad-body{padding:14px 16px 16px}
"""

_JS = r"""(function(){
"use strict";
var CONFIG_URL=%(url)s, SITE=%(site)s, RANK={paid:0,house:1,affiliate:2};
var slots=[].slice.call(document.querySelectorAll('.ad-slot[data-ad-slot]'));
if(!slots.length)return;
function ga(name,s){
  if(typeof window.gtag!=='function')return;
  var p={promotion_id:s.dataset.adId,promotion_name:s.dataset.adName,
         creative_name:s.dataset.adCreative,creative_slot:s.dataset.adSlot};
  p.items=[{item_id:p.promotion_id,item_name:p.promotion_name,promotion_id:p.promotion_id,
            promotion_name:p.promotion_name,creative_name:p.creative_name,creative_slot:p.creative_slot}];
  window.gtag('event',name,p);
}
// 曝光：一半以上進畫面、停留滿 1 秒才算；同一次瀏覽每個版位只算一次。分頁在背景不計時。
function watch(s){
  if(s._adWatched)return; s._adWatched=true;
  s.addEventListener('click',function(){ga('select_promotion',s);});
  if(!('IntersectionObserver' in window))return;
  var t=null, done=false;
  var io=new IntersectionObserver(function(es){
    es.forEach(function(e){
      if(done)return;
      if(e.isIntersecting&&e.intersectionRatio>=0.5&&!document.hidden){
        if(!t)t=setTimeout(function(){done=true;io.disconnect();ga('view_promotion',s);},1000);
      }else if(t){clearTimeout(t);t=null;}
    });
  },{threshold:[0,0.5,1]});
  io.observe(s);
  document.addEventListener('visibilitychange',function(){if(document.hidden&&t){clearTimeout(t);t=null;}});
}
function okUrl(u){try{var x=new URL(u);return x.protocol==='https:'?x:null;}catch(e){return null;}}
function withUtm(x,slot,id){
  if(!x.searchParams.has('utm_source')){
    x.searchParams.set('utm_source',SITE);x.searchParams.set('utm_medium',slot);x.searchParams.set('utm_campaign',id);
  }
  return x.toString();
}
function apply(s,c){
  var x=okUrl(c.url); if(!x)return false;
  var img=c.image?okUrl(c.image):null;
  var label=c.tier==='paid'?'贊助':'推廣';
  s.querySelector('.ad-label').textContent=label;
  s.querySelector('.ad-t').textContent=c.title;
  s.querySelector('.ad-d').textContent=c.desc||'';
  var cta=s.querySelector('.ad-cta'); if(cta)cta.textContent=(c.cta||'去看看')+' →';
  var m=s.querySelector('.ad-media');
  if(img){
    var im=document.createElement('img');
    im.className='ad-media';im.alt='';im.loading='lazy';im.src=img.toString();
    m.parentNode.replaceChild(im,m);
  }else{
    m.className='ad-media ad-media-fb';m.textContent=c.media_text||c.title;
  }
  s.href=withUtm(x,s.dataset.adSlot,c.id);
  var ext=x.host!==location.host;
  s.target=ext?'_blank':''; if(!ext)s.removeAttribute('target');
  s.rel=c.tier==='paid'?'sponsored noopener':'noopener';
  s.dataset.adId=c.id;s.dataset.adName=c.title;s.dataset.adCreative=c.creative||c.id;
  return true;
}
function valid(c,now){
  if(!c||typeof c.id!=='string'||typeof c.title!=='string'||!c.title||typeof c.url!=='string')return false;
  if(!(c.tier in RANK))return false;
  if(!Array.isArray(c.sites)||c.sites.indexOf(SITE)<0)return false;
  if(!Array.isArray(c.slots))return false;
  var a=Date.parse(c.start), b=Date.parse(c.end);
  return !isNaN(a)&&!isNaN(b)&&a<=now&&now<b;
}
function run(cfg){
  var now=Date.now(), used={};
  var list=(cfg&&Array.isArray(cfg.campaigns)?cfg.campaigns:[]).filter(function(c){return valid(c,now);});
  list.sort(function(p,q){return (RANK[p.tier]-RANK[q.tier])||(Date.parse(q.start)-Date.parse(p.start));});
  slots.forEach(function(s){
    var slot=s.dataset.adSlot;
    for(var i=0;i<list.length;i++){
      var c=list[i];
      if(c.slots.indexOf(slot)<0||used[c.id])continue;   // 同一則不在同一頁出現兩次
      if(apply(s,c)){used[c.id]=true;break;}
    }
    watch(s);
  });
}
var done=false;
function fallback(){if(done)return;done=true;slots.forEach(watch);}
try{
  var ctl=('AbortController' in window)?new AbortController():null;
  var to=setTimeout(function(){if(ctl)ctl.abort();fallback();},4000);
  fetch(CONFIG_URL,{credentials:'omit',signal:ctl?ctl.signal:undefined})
    .then(function(r){if(!r.ok)throw new Error('http '+r.status);return r.json();})
    .then(function(cfg){clearTimeout(to);if(done)return;done=true;run(cfg);})
    .catch(function(){clearTimeout(to);fallback();});
}catch(e){fallback();}
})();
"""

JS_TEXT = _JS % {"url": '"' + CONFIG_URL + '"', "site": '"' + SITE_KEY + '"'}


def script_href(pub: pathlib.Path) -> str:
    """版位程式落地到 public-racing/assets/ad-<hash>.js（比照 shared_css_href：內容 hash 當檔名，
    只留新版＋前一版兩份，防部署切版時舊頁引用 404）。"""
    assets_dir = pathlib.Path(pub) / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    content = JS_TEXT.encode("utf-8")
    fname = f"ad-{hashlib.sha256(content).hexdigest()[:10]}.js"
    fpath = assets_dir / fname
    if not fpath.exists():
        fpath.write_bytes(content)
        others = sorted((p for p in assets_dir.glob("ad-*.js") if p.name != fname),
                        key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in others[1:]:
            stale.unlink()
    return f"/assets/{fname}"


def script_tag(pub: pathlib.Path) -> str:
    return f'<script src="{script_href(pub)}" defer></script>'


def slot_html(slot: str) -> str:
    """版位外殼＋預設卡。廣告內容由 ad-*.js 在瀏覽器端換上；讀不到就維持預設卡。"""
    if slot not in FALLBACK:
        raise ValueError(f"unknown ad slot: {slot}")
    title, url = FALLBACK[slot]
    t = html_lib.escape(title)
    short = html_lib.escape(title.split(" — ")[0])
    fid = f"fallback-{SITE_KEY}-{slot}"
    kind = {"home_hero": "ad-row ad-hero", "native_list": "ad-native", "native_end": "ad-row ad-end"}[slot]
    extra = ""
    cta = '<span class="ad-cta">去看看 →</span>' if slot == "home_hero" else ''
    return (f'<a class="ad-slot {kind}{extra}" data-ad-slot="{slot}" data-ad-id="{fid}" '
            f'data-ad-name="{t}" data-ad-creative="{fid}" href="{url}" rel="noopener">'
            f'<span class="ad-label">推廣</span>'
            f'<span class="ad-media ad-media-fb">{short}</span>'
            f'<span class="ad-body"><span class="ad-t">{t}</span>'
            f'<span class="ad-d">姊妹站</span>{cta}</span></a>')
