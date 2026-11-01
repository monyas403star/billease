(function(){
  'use strict';
  const el=id=>document.getElementById(id),search=el('provider-search'),category=el('provider-category'),billSelect=el('portal-bill');
  let catalog=null,bills=[],selectedProvider=null;
  const names={official_site:'Official website',payment_guidance:'Payment information',payment_page:'Payment page'};
  function normalize(value){return String(value||'').normalize('NFKD').replace(/[\u0591-\u05C7\u064B-\u065F\u0670\u0640\u0300-\u036f]/g,'').toLowerCase().replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/[^\p{L}\p{N}]+/gu,' ').trim();}
  function render(){
    if(!catalog)return;
    const tokens=normalize(search.value).split(' ').filter(Boolean);
    const providers=catalog.providers.filter(p=>{
      const hay=normalize([...Object.values(p.name),...p.aliases,...Object.values(catalog.category_names[p.category]),new URL(p.url).hostname].join(' '));
      const view=el('provider-view').value;
      return (category.value==='all'||p.category===category.value)&&tokens.every(token=>hay.includes(token))
        &&(view!=='favorites'||catalog.favorites.includes(p.id))&&(view!=='recent'||catalog.recent.some(r=>r.provider_id===p.id))&&(view!=='payment'||p.kind!=='official_site');
    }).sort((a,b)=>el('provider-view').value==='recent'?catalog.recent.findIndex(r=>r.provider_id===a.id)-catalog.recent.findIndex(r=>r.provider_id===b.id):a.name[uiSettings.locale].localeCompare(b.name[uiSettings.locale],uiLocale()));
    el('provider-count').textContent=t('{shown} of {total} destinations',{shown:providers.length,total:catalog.providers.length});
    el('provider-empty').hidden=providers.length>0;
    const view=el('provider-view').value;
    el('provider-empty-title').textContent=t(view==='favorites'?'No favorites yet':view==='recent'?'No recent destinations yet':'Provider not listed?');
    el('provider-empty-text').textContent=t(view==='favorites'?'Browse all destinations and add the providers you use to your favorites.':view==='recent'?'Destinations you request to open will appear here. This is not a payment history.':'This directory does not cover every provider. For rent, private lessons, shops or another business, request its official payment channel directly. Do not choose a different provider just because the category matches.');
    el('provider-grid').innerHTML=providers.map(p=>`<article class="provider-card"><span class="provider-kind-badge">${escapeHtml(t(catalog.categories[p.category]))}</span><h3>${escapeHtml(p.name[uiSettings.locale]||p.name.he)}</h3><p class="provider-host">${escapeHtml(new URL(p.url).hostname)}</p><p class="muted">${escapeHtml(t(names[p.kind]))}</p><button type="button" class="btn small provider-favorite" data-favorite="${escapeHtml(p.id)}" aria-pressed="${catalog.favorites.includes(p.id)}">${escapeHtml(t(catalog.favorites.includes(p.id)?'Remove favorite':'Add favorite'))}</button><button type="button" class="btn" data-provider="${escapeHtml(p.id)}">${escapeHtml(t('View destination'))} ↗</button></article>`).join('');
  }
  function selectBill(){
    const bill=bills.find(b=>String(b.bill_id)===billSelect.value),box=el('portal-bill-details');
    if(!bill){box.hidden=true;box.textContent='';return;}
    box.textContent=t('{supplier} · {amount} · Due {date} · {status}',{supplier:bill.supplier,amount:fmtMoney(bill.amount),date:fmtDate(bill.due_date),status:t(bill.is_paid?'שולם':'לא שולמו')});box.hidden=false;
    // No automatic destination selection from category, OCR, city or an invoice URL.
  }
  function openProvider(id){
    const provider=catalog?.providers.find(p=>p.id===id);if(!provider)return;selectedProvider=id;
    el('provider-dialog-title').textContent=provider.name[uiSettings.locale]||provider.name.he;
    el('provider-kind').textContent=t(names[provider.kind]);el('provider-destination').textContent=provider.url;
    el('provider-outbound').href=provider.url;el('provider-dialog').showModal();
  }
  async function load(){
    el('provider-retry').disabled=true;el('provider-count').textContent=t('טוען...');
    try{
      const data=await apiGet('/api/payment-providers');if(!data.ok)throw new Error('catalog');
      catalog=data;
      const previous=category.value;category.replaceChildren(new Option(t('All services'),'all'));
      for(const[key,label]of Object.entries(data.categories))category.add(new Option(t(label),key));
      if([...category.options].some(option=>option.value===previous))category.value=previous;
      el('provider-reviewed').textContent=t('Sources reviewed: {date}. External sites may change; this is not a live availability check.',{date:fmtDate(data.reviewed_on)});
      render();
    }catch(error){catalog=null;el('provider-grid').replaceChildren();el('provider-empty').hidden=true;el('provider-count').textContent=t('The provider directory is unavailable. Try again later.');}
    finally{el('provider-retry').disabled=false;}
  }
  async function loadBills(){
    try{
      const data=await apiGet('/api/bills');if(!data.ok)return;bills=data.bills;
      for(const b of bills)billSelect.add(new Option(`${b.supplier} — ${fmtMoney(b.amount)} — ${fmtDate(b.due_date)}`,String(b.bill_id)));
      const id=new URLSearchParams(location.search).get('bill_id');
      if(bills.some(b=>String(b.bill_id)===id)){billSelect.value=id;selectBill();}
    }catch(error){/* Provider browsing remains available if account bill loading fails. */}
  }
  search.addEventListener('input',render);category.addEventListener('change',render);billSelect.addEventListener('change',selectBill);
  el('provider-clear').addEventListener('click',()=>{search.value='';category.value='all';el('provider-view').value='all';render();});
  el('provider-retry').addEventListener('click',load);
  el('provider-view').addEventListener('change',render);
  el('provider-grid').addEventListener('click',async event=>{
    const button=event.target.closest('[data-provider]');if(button)openProvider(button.dataset.provider);
    const favorite=event.target.closest('[data-favorite]');if(!favorite)return;
    const id=favorite.dataset.favorite,enabled=!catalog.favorites.includes(id);favorite.disabled=true;
    try{
      const response=await apiSend('/api/payment-providers/favorite','POST',{provider_id:id,enabled});
      if(!response.ok)throw new Error('favorite');
      if(enabled)catalog.favorites.push(id);else catalog.favorites=catalog.favorites.filter(item=>item!==id);render();
    }catch(error){favorite.disabled=false;el('provider-count').textContent=t('Could not save your preference. Try again.');}
  });
  el('provider-outbound').addEventListener('click',()=>{
    if(!selectedProvider)return;
    const id=selectedProvider;
    // This records a requested navigation only. It never marks any bill paid.
    fetch('/api/payment-providers/visit',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({provider_id:id}),keepalive:true})
      .then(r=>r.json()).then(res=>{if(res.ok){catalog.recent=[{provider_id:id},...catalog.recent.filter(r=>r.provider_id!==id)].slice(0,8);if(el('provider-view').value==='recent')render();}}).catch(()=>{});
  });
  el('provider-close').addEventListener('click',()=>el('provider-dialog').close());
  el('provider-dialog').addEventListener('click',event=>{if(event.target===el('provider-dialog')){const r=event.target.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)event.target.close();}});
  load();loadBills();
})();
