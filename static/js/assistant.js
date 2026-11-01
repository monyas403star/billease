(function(){
  'use strict';
  const el=id=>document.getElementById(id),year=el('ai-year'),month=el('ai-month'),form=el('ai-form');
  let snapshot=null,busy=false,sequence=0;
  year.value=new Date().getFullYear();
  for(let i=1;i<=12;i++)month.add(new Option(new Intl.DateTimeFormat(uiLocale(),{month:'long'}).format(new Date(2026,i-1,1)),String(i)));
  const value=f=>f.kind==='money'?fmtMoney(f.value/100):new Intl.NumberFormat(uiLocale()).format(f.value);
  const factsHTML=facts=>facts.map(f=>`<dt>${escapeHtml(f.label)}</dt><dd>${escapeHtml(value(f))}</dd>`).join('');
  function clearAnswer(){el('ai-answer-panel').hidden=true;el('ai-answer').textContent='';el('ai-references').replaceChildren();}
  function render(data){
    snapshot=data;
    const cards=['total','paid','open'].map(id=>data.facts.find(f=>f.id===id)).filter(Boolean);
    el('ai-cards').innerHTML=cards.map(f=>`<div class="assistant-card"><p>${escapeHtml(f.label)}</p><strong>${escapeHtml(value(f))}</strong></div>`).join('');
    el('ai-all-facts').innerHTML=factsHTML(data.facts);
    const period=data.month?new Intl.DateTimeFormat(uiLocale(),{month:'long',year:'numeric'}).format(new Date(data.year,data.month-1,1)):String(data.year);
    el('ai-scope').textContent=t('Selected period: {period}. Calculated as of {date}.',{period,date:fmtDate(data.as_of)});
    if(data.comparison.available){
      el('ai-scope').textContent+=' '+t('Matched comparison with {year}, through month {month}.',{year:data.comparison.previous_year,month:data.comparison.months_through});
    }else el('ai-scope').textContent+=' '+t('Not enough data for a like-for-like comparison.');
    el('ai-facts-status').textContent=data.facts.find(f=>f.id==='count')?.value===0?t('No saved bills in this period. Choose another period or add bills.'):'';
    if(data.excluded_bill_count)el('ai-facts-status').textContent+=' '+t('{count} records with invalid dates or amounts were excluded.',{count:data.excluded_bill_count});
  }
  function setBusy(value){
    busy=value;
    for(const id of ['ai-send','ai-refresh','ai-year','ai-month'])el(id).disabled=value;
    for(const button of document.querySelectorAll('[data-question]'))button.disabled=value;
    form.setAttribute('aria-busy',String(value));
  }
  function validPeriod(){return year.reportValidity();}
  async function loadFacts(){
    if(busy||!validPeriod())return;
    const request=++sequence;clearAnswer();el('ai-status').textContent='';el('ai-facts-status').textContent=t('טוען...');
    try{
      const response=await apiGet(`/api/assistant/summary?year=${encodeURIComponent(year.value)}&month=${month.value}`);
      if(request!==sequence)return;
      if(!response.ok)throw new Error(response.error||t('Could not load account facts. Refresh or sign in again.'));
      render(response.summary);
    }catch(error){
      if(request!==sequence)return;snapshot=null;el('ai-cards').replaceChildren();el('ai-all-facts').replaceChildren();el('ai-scope').textContent='';
      el('ai-facts-status').textContent=t('Could not load account facts. Refresh or sign in again.');
    }
  }
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(busy||!validPeriod())return;
    const question=el('ai-question').value.trim().replace(/\s+/g,' ');if(!question)return;
    ++sequence;setBusy(true);clearAnswer();el('ai-status').textContent=t('Analyzing your calculated account facts…');
    try{
      const res=await apiSend('/api/assistant/ask','POST',{question,year:year.value,month:month.value});
      if(!res.ok){el('ai-status').textContent=res.error||t('AI could not answer now. Try again; the calculated facts below remain available.');return;}
      render(res.summary);el('ai-answer').textContent=res.answer;
      const refs=new Set(res.fact_ids);el('ai-references').innerHTML=factsHTML(res.summary.facts.filter(f=>refs.has(f.id)));
      if(!refs.size)el('ai-references').textContent=t('No account figures were cited in this answer.');
      el('ai-answer-panel').hidden=false;el('ai-status').textContent=t('Answer ready. Review the supporting figures below.');
    }catch(error){el('ai-status').textContent=t('AI could not answer now. Try again; the calculated facts below remain available.');}
    finally{setBusy(false);}
  });
  document.querySelectorAll('[data-question]').forEach(button=>button.addEventListener('click',()=>{el('ai-question').value=button.dataset.question;el('ai-question').focus();}));
  year.addEventListener('change',loadFacts);month.addEventListener('change',loadFacts);el('ai-refresh').addEventListener('click',loadFacts);
  loadFacts();
})();
