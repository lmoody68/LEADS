// Visitor beacon -> central collector. Bundled with the app (Vite strips raw <script> tags),
// so a side-effect import guarantees it runs. Fire-and-forget; never blocks the app.
(function(){try{const d={s:'leads',page:location.pathname,title:document.title,ref:document.referrer};const u='https://leslie-moody-ai.netlify.app/.netlify/functions/beacon';const b=JSON.stringify(d);if(navigator.sendBeacon){navigator.sendBeacon(u,new Blob([b],{type:'text/plain'}));}else{fetch(u,{method:'POST',mode:'no-cors',keepalive:true,body:b}).catch(()=>{});}}catch(e){}})();
export {};
