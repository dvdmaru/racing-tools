(function(){
"use strict";
var CONFIG_URL="https://twtools.cc/ad-slots.json", SITE="racing", RANK={paid:0,house:1,affiliate:2};
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
