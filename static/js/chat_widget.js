/* Presentation only: the server still authorizes and computes each answer. */
(async function() {
  'use strict';
  const prefix='billease-chat-v1:', el=id=>document.getElementById(id), widget=el('chat-widget');
  function purge(except=null){try{for(let i=sessionStorage.length-1;i>=0;i--){const key=sessionStorage.key(i);if(key.startsWith(prefix)&&key!==except)sessionStorage.removeItem(key);}}catch(error){/* Storage may be blocked. */}}
  if(!widget){purge();return;}
  let storageKey=null,storageOK=false;
  try{
    const owner=[widget.dataset.owner,widget.dataset.version,widget.dataset.locale].join('|');
    const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(owner));
    storageKey=prefix+Array.from(new Uint8Array(hash),n=>n.toString(16).padStart(2,'0')).join('');
    purge(storageKey);sessionStorage.setItem(storageKey+':probe','1');sessionStorage.removeItem(storageKey+':probe');storageOK=true;
  }catch(error){purge();}
  const panel=el('chat-panel'),launcher=el('chat-launcher'),history=el('chat-history'),form=el('chat-form');
  const year=el('chat-year'),month=el('chat-month'),question=el('chat-question'),status=el('chat-status');
  const now=new Date();let turns=[],busy=false,controller=null,open=false;
  year.value=String(now.getFullYear());
  for(let i=1;i<=12;i++)month.add(new Option(new Intl.DateTimeFormat(uiLocale(),{month:'long'}).format(new Date(2026,i-1,1)),String(i)));
  function save(){if(!storageOK)return;try{sessionStorage.setItem(storageKey,JSON.stringify({turns:turns.slice(-10),year:year.value,month:month.value,draft:question.value.slice(0,700),open}));}catch(error){storageOK=false;}}
  function failure(message){const error=new Error(message);error.displayMessage=message;return error;}
  const periodValid=(y,m)=>Number.isInteger(Number(y))&&Number(y)>=2000&&Number(y)<=2300&&Number.isInteger(Number(m))&&Number(m)>=0&&Number(m)<=12;
  try{
    const saved=storageOK?JSON.parse(sessionStorage.getItem(storageKey)||'null'):null;
    if(saved&&Array.isArray(saved.turns)){
      turns=saved.turns.filter(x=>x&&typeof x.question==='string'&&x.question.length<=700&&periodValid(x.year,x.month)).slice(-10).map(x=>({question:x.question,year:Number(x.year),month:Number(x.month),time:typeof x.time==='string'?x.time.slice(0,40):'',answer:typeof x.answer==='string'?x.answer.slice(0,12000):null,error:typeof x.error==='string'?x.error.slice(0,1000):null,refs:Array.isArray(x.refs)?x.refs.slice(0,20).filter(f=>f&&typeof f.label==='string'&&Number.isFinite(f.value)).map(f=>({label:f.label.slice(0,200),value:f.value,kind:f.kind==='money'?'money':'number'})):[]}));
      for(const turn of turns)if(!turn.answer&&!turn.error)turn.error=t('The previous request was interrupted. Send your question again if needed.');
      if(periodValid(saved.year,saved.month)){year.value=String(saved.year);month.value=String(saved.month);}
      question.value=typeof saved.draft==='string'?saved.draft.slice(0,700):'';open=saved.open===true;
    }
  }catch(error){turns=[];}
  function node(tag,text,className){const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(className)n.className=className;return n;}
  function render(){
    history.replaceChildren();
    if(!turns.length)history.append(node('p',t('Ask about your saved bills, spending categories and budget alerts.')));
    turns.forEach(turn=>{
      const article=node('article',undefined,'chat-turn');
      const period=turn.month?new Intl.DateTimeFormat(uiLocale(),{month:'long',year:'numeric'}).format(new Date(turn.year,turn.month-1,1)):String(turn.year);
      const timestamp=new Date(turn.time);const stamp=Number.isFinite(timestamp.getTime())?new Intl.DateTimeFormat(uiLocale(),{dateStyle:'short',timeStyle:'short'}).format(timestamp):'';
      article.append(node('p',t('Answer period: {period}',{period})+(stamp?' · '+stamp:''),'chat-meta'));
      const user=node('div',undefined,'chat-bubble chat-bubble-user');user.append(node('strong',t('You')),node('p',turn.question));article.append(user);
      const reply=node('div',undefined,'chat-bubble');reply.append(node('strong',t('AI assistant')),node('p',turn.answer||turn.error||t('Analyzing your calculated account facts…')));
      if(turn.answer){
        const details=node('details',undefined,'chat-evidence');details.append(node('summary',t('Calculated facts used in this answer')));
        const facts=node('dl');
        for(const fact of turn.refs){facts.append(node('dt',fact.label),node('dd',fact.kind==='money'?fmtMoney(fact.value/100):new Intl.NumberFormat(uiLocale()).format(fact.value)));}
        details.append(turn.refs.length?facts:node('p',t('No account figures were cited in this answer.')));reply.append(details);
      }
      article.append(reply);history.append(article);
    });
    history.scrollTop=history.scrollHeight;
  }
  function setOpen(value,focus=true){open=value;panel.hidden=!value;launcher.setAttribute('aria-expanded',String(value));save();if(focus)(value?question:launcher).focus();}
  function setBusy(value){busy=value;form.setAttribute('aria-busy',String(value));for(const id of ['chat-send','chat-year','chat-month','chat-clear','chat-question'])el(id).disabled=value;widget.querySelectorAll('[data-chat-question]').forEach(b=>b.disabled=value);}
  launcher.addEventListener('click',()=>setOpen(!open));el('chat-close').addEventListener('click',()=>setOpen(false));
  widget.addEventListener('keydown',event=>{if(event.key==='Escape'&&open){event.preventDefault();setOpen(false);}});
  for(const field of [question,year,month])field.addEventListener('input',save);
  el('chat-clear').addEventListener('click',()=>{if(busy)return;turns=[];question.value='';status.textContent='';render();save();question.focus();});
  widget.querySelectorAll('[data-chat-question]').forEach(button=>button.addEventListener('click',()=>{question.value=button.dataset.chatQuestion;save();question.focus();}));
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!year.reportValidity()||!question.reportValidity())return;
    const text=question.value.trim().replace(/\s+/g,' ');if(!text)return;
    const turn={question:text,year:Number(year.value),month:Number(month.value),time:new Date().toISOString(),answer:null,error:null,refs:[]};
    turns.push(turn);turns=turns.slice(-10);question.value='';setBusy(true);render();save();status.textContent=t('Analyzing your calculated account facts…');
    controller=new AbortController();const requestController=controller;const timer=setTimeout(()=>requestController.abort(),40000);
    let expired=false;
    try{
      const response=await fetch('/api/assistant/ask',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({question:text,year:turn.year,month:turn.month}),signal:requestController.signal});
      if(response.status===401){expired=true;purge();storageOK=false;turns=[];throw failure(t('Your session ended. Sign in again to ask the assistant.'));}
      const data=await response.json();
      if(!response.ok||!data.ok)throw failure(typeof data.error==='string'?data.error:t('AI could not answer now. Try again; the calculated facts below remain available.'));
      if(typeof data.answer!=='string'||!Array.isArray(data.fact_ids)||!Array.isArray(data.summary?.facts))throw failure(t('Chat could not get an answer. Please try again.'));
      turn.answer=data.answer.slice(0,12000);const ids=new Set(data.fact_ids);
      turn.refs=data.summary.facts.filter(f=>ids.has(f.id)&&typeof f.label==='string'&&Number.isFinite(f.value)).slice(0,20).map(f=>({label:f.label.slice(0,200),value:f.value,kind:f.kind}));
      status.textContent=t('Answer ready. Review the supporting figures below.');
    }catch(error){const message=error.name==='AbortError'?t('The request timed out. Try again in a moment.'):error.displayMessage;turn.error=message||t('Chat could not get an answer. Please try again.');status.textContent=turn.error;question.value=text;}
    finally{clearTimeout(timer);controller=null;setBusy(false);render();if(!expired)save();}
  });
  function clearOnLogout(){controller?.abort();purge();storageOK=false;turns=[];question.value='';render();setOpen(false,false);widget.hidden=true;}
  document.addEventListener('click',event=>{const link=event.target.closest('a[href]');if(link&&new URL(link.href,location.href).pathname==='/logout')clearOnLogout();});
  window.addEventListener('pagehide',()=>{save();controller?.abort();});
  window.addEventListener('pageshow',async event=>{
    if(!event.persisted)return;
    // A back/forward cache must not reveal the previous account's chat after logout.
    widget.hidden=true;
    try{const res=await fetch('/api/profile',{credentials:'same-origin',cache:'no-store'});const data=await res.json();if(!res.ok||!data.ok||String(data.user?.user_id)!==widget.dataset.owner){clearOnLogout();return;}widget.hidden=false;}
    catch(error){clearOnLogout();}
  });
  render();setOpen(open,false);
  if(!storageOK)status.textContent=t('Tab storage is unavailable. Chat will reset when you change pages.');
})();
