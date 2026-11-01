(function(){
  'use strict';
  const el=id=>document.getElementById(id),search=el('provider-search'),category=el('provider-category'),billSelect=el('portal-bill');
  let catalog=null,bills=[],selectedProvider=null;
  const names={official_site:'Official website',payment_guidance:'Payment information',payment_page:'Payment page'};
  const categoryIcons={
    all:'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    electricity:'<path d="m13 2-9 12h7l-1 8L21 9h-8z"/>',
    gas:'<path d="M12 3c1 5-4 6-4 10 0 2 1 3 2 3-1-3 2-4 3-7 2 3 5 5 5 8a6 6 0 0 1-12 0c0-6 4-8 6-14z"/>',
    water:'<path d="M12 2C9 7 5 11 5 15a7 7 0 0 0 14 0c0-4-4-8-7-13z"/>',
    telecom:'<rect x="6" y="2" width="12" height="20" rx="3"/><path d="M10 18h4M10 6h4"/>',
    municipal:'<path d="m3 9 9-6 9 6M4 10h16M5 20h14M8 10v10M12 10v10M16 10v10M3 22h18"/>',
    insurance:'<path d="m12 2 8 4v6c0 5-4 8-8 10-4-2-8-5-8-10V6zM8 12l3 3 5-6"/>',
    health:'<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M12 7v10M7 12h10"/>',
    transport:'<path d="m5 9 2-5h10l2 5M3 10h18v8H3zM6 18v3M18 18v3M6 14h2M16 14h2"/>',
    government:'<path d="M6 2h9l4 4v16H6zM15 2v5h4M9 11h7M9 15h7M9 19h5"/>',
    education:'<path d="m2 9 10-6 10 6-10 6zM6 12v6c4 3 8 3 12 0v-6M22 9v9"/>',
    subscriptions:'<rect x="3" y="4" width="18" height="16" rx="3"/><path d="m10 8 6 4-6 4z"/>',
    banking:'<path d="m2 8 10-5 10 5H2zM5 11v7M10 11v7M14 11v7M19 11v7M3 21h18"/>',
    credit_cards:'<rect x="2" y="4" width="20" height="16" rx="3"/><path d="M2 9h20M6 15h5"/>',
    electronics:'<rect x="5" y="3" width="14" height="13" rx="1"/><path d="m5 16-3 5h20l-3-5M10 18h4"/>',
    home_retail:'<path d="m3 11 9-8 9 8M5 10v11h14V10M10 21v-7h4v7"/>',
    retail:'<path d="M2 3h3l3 13h11l3-10H6M10 21h.01M18 21h.01"/>',
    public_transport:'<rect x="5" y="2" width="14" height="18" rx="3"/><path d="M5 10h14M8 6h8M8 15h1M15 15h1M8 20v2M16 20v2"/>',
    travel:'<path d="m22 3-7 8 1 9-3 2-3-8-5 4-3-1 5-6-5-4 2-2 8 2 8-6z"/>'
  };
  function buildCategoryButtons(){
    const counts={all:catalog.providers.length};
    catalog.providers.forEach(provider=>{counts[provider.category]=(counts[provider.category]||0)+1;});
    const choices=[['all',t('All services')],...Object.entries(catalog.categories).filter(([id])=>counts[id]).map(([id,label])=>[id,t(label)])];
    el('provider-category-buttons').replaceChildren(...choices.map(([id,fullLabel])=>{
      const button=document.createElement('button');button.type='button';button.className='provider-category-button';button.dataset.category=id;
      button.title=fullLabel;button.setAttribute('aria-pressed',String(category.value===id));
      const icon=document.createElement('span');icon.className='provider-category-icon';icon.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">'+(categoryIcons[id]||categoryIcons.all)+'</svg>';icon.setAttribute('aria-hidden','true');
      const label=document.createElement('span');label.textContent=id==='all'?t('All services'):t('Category button: '+id);label.className='provider-category-label';
      // Future categories still receive their translated full title without a code change.
      if(label.textContent==='Category button: '+id)label.textContent=fullLabel;
      const count=document.createElement('span');count.className='provider-category-count';count.textContent=counts[id];
      button.append(icon,label,count);return button;
    }));
  }
  function syncCategoryButtons(){
    el('provider-category-buttons').querySelectorAll('[data-category]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.category===category.value)));
  }
  function normalize(value){return String(value||'').normalize('NFKD').replace(/[\u0591-\u05C7\u064B-\u065F\u0670\u0640\u0300-\u036f]/g,'').toLowerCase().replace(/[أإآ]/g,'ا').replace(/ى/g,'ي').replace(/[^\p{L}\p{N}]+/gu,' ').trim();}
  function render(){
    if(!catalog)return;
    syncCategoryButtons();
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
      buildCategoryButtons();
      el('provider-reviewed').textContent=t('Sources reviewed: {date}. External sites may change; this is not a live availability check.',{date:fmtDate(data.reviewed_on)});
      render();
    }catch(error){catalog=null;el('provider-category-buttons').replaceChildren();el('provider-grid').replaceChildren();el('provider-empty').hidden=true;el('provider-count').textContent=t('The provider directory is unavailable. Try again later.');}
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
  el('provider-category-buttons').addEventListener('click',event=>{
    const button=event.target.closest('[data-category]');if(!button||!catalog)return;
    category.value=button.dataset.category;search.value='';el('provider-view').value='all';render();
  });
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
