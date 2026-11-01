(function(root){
  'use strict';
  const pad=n=>String(n).padStart(2,'0');
  const key=date=>`${date.getFullYear()}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`;
  function parse(value){
    if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
    const[y,m,d]=value.split('-').map(Number),date=new Date(y,m-1,d,12);
    return date.getFullYear()===y&&date.getMonth()===m-1&&date.getDate()===d?date:null;
  }
  const paid=b=>b.is_paid===true||Number(b.is_paid)===1;
  function state(b,today){
    if(paid(b))return 'paid';
    if(b.due_date<today)return 'late';
    const start=parse(today),due=parse(b.due_date);
    if(!start||!due)return 'open';
    const days=Math.round((due-start)/86400000);
    return days<=7?'soon':'open';
  }
  function monthBills(bills,month,filter){
    return bills.filter(b=>parse(b.due_date)&&b.due_date.slice(0,7)===month&&(filter==='all'||(filter==='paid'?paid(b):!paid(b))))
      .slice().sort((a,b)=>a.due_date.localeCompare(b.due_date)||Number(a.bill_id)-Number(b.bill_id));
  }
  function cells(month){
    const[y,m]=month.split('-').map(Number),first=new Date(y,m-1,1,12),days=new Date(y,m,0,12).getDate();
    const values=Array(first.getDay()).fill(null);
    for(let day=1;day<=days;day++)values.push(`${month}-${pad(day)}`);
    while(values.length%7)values.push(null);
    return values;
  }
  if(typeof module!=='undefined'&&module.exports){module.exports={parse,state,monthBills,cells};return;}
  const el=id=>document.getElementById(id),picker=el('cal-month'),filter=el('cal-filter');
  const dialog=el('cal-dialog'),today=key(new Date());
  let bills=[],loaded=false,mode=matchMedia('(max-width: 600px)').matches?'list':'month';
  picker.value=today.slice(0,7);
  const labels={paid:'שולם',open:'פתוח',soon:'לתשלום בקרוב',late:'באיחור'};
  const money=list=>fmtMoney(list.reduce((sum,b)=>sum+Math.round(Number(b.amount)*100),0)/100);
  function eventHTML(b){
    const status=state(b,today);
    return `<button type="button" class="calendar-event ${status}" data-bill="${escapeHtml(b.bill_id)}"><strong>${escapeHtml(b.supplier||'')}</strong><span>${escapeHtml(fmtMoney(b.amount))}</span><span>${escapeHtml(t(labels[status]))}</span></button>`;
  }
  function render(){
    if(!picker.checkValidity()||!/^\d{4}-\d{2}$/.test(picker.value))return;
    const month=picker.value,[year,m]=month.split('-').map(Number);
    const rows=monthBills(bills,month,filter.value),groups=new Map();
    rows.forEach(b=>{if(!groups.has(b.due_date))groups.set(b.due_date,[]);groups.get(b.due_date).push(b);});
    el('cal-heading').textContent=new Intl.DateTimeFormat(uiLocale(),{year:'numeric',month:'long'}).format(new Date(year,m-1,1,12));
    el('cal-totals').textContent=t('{count} bills · Total {total} · Open {open} · Paid {paid}',{count:rows.length,total:money(rows),open:money(rows.filter(b=>!paid(b))),paid:money(rows.filter(paid))});
    const week=Array.from({length:7},(_,i)=>new Intl.DateTimeFormat(uiLocale(),{weekday:'short'}).format(new Date(2026,10,1+i,12)));
    el('cal-grid').innerHTML=week.map(day=>`<div class="calendar-weekday">${escapeHtml(day)}</div>`).join('')+cells(month).map(day=>day?
      `<div class="calendar-day ${day===today?'is-today':''}"><time class="calendar-date" datetime="${day}" ${day===today?'aria-current="date"':''}>${Number(day.slice(-2))}</time>${(groups.get(day)||[]).map(eventHTML).join('')}</div>`:
      '<div class="calendar-day is-blank" aria-hidden="true"></div>').join('');
    el('cal-agenda').innerHTML=[...groups].map(([day,list])=>`<section class="calendar-agenda-day"><h3>${escapeHtml(new Intl.DateTimeFormat(uiLocale(),{weekday:'long',year:'numeric',month:'long',day:'numeric'}).format(parse(day)))}</h3>${list.map(eventHTML).join('')}</section>`).join('');
    el('cal-month-view').hidden=mode!=='month';el('cal-agenda').hidden=mode!=='list';
    el('cal-grid-view').setAttribute('aria-pressed',String(mode==='month'));el('cal-list-view').setAttribute('aria-pressed',String(mode==='list'));
    el('cal-prev').disabled=month<=picker.min;el('cal-next').disabled=month>=picker.max;
    if(loaded)el('cal-message').textContent=rows.length?'':t('No bills match this month and filter. Try another month or show all bills.');
  }
  function showBill(id){
    const b=bills.find(item=>String(item.bill_id)===id);if(!b)return;
    el('cal-detail-title').textContent=b.supplier||t('Payment details');
    const pairs=[[t('סכום'),fmtMoney(b.amount)],[t('תאריך פירעון'),fmtDate(b.due_date)],[t('קטגוריה'),categoryLabel(b.category||'')],[t('סטטוס'),t(labels[state(b,today)])]];
    if(b.payment_plan_id)pairs.push([t('Installment'),t('{number} of {count}',{number:b.installment_number,count:b.installment_count})]);
    el('cal-detail').innerHTML='<dl>'+pairs.map(([label,value])=>`<dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd>`).join('')+'</dl>';
    dialog.showModal();
  }
  async function load(){
    el('cal-refresh').disabled=true;el('cal-message').textContent=t('טוען...');
    try{
      const res=await apiGet('/api/bills');if(!res.ok||!Array.isArray(res.bills))throw new Error('load');
      bills=res.bills;loaded=true;render();
    }catch(error){
      loaded=false;bills=[];render();el('cal-message').textContent=t('The calendar could not load. Sign in again if your session expired, then select Refresh.');
    }finally{el('cal-refresh').disabled=false;}
  }
  function move(delta){
    if(!picker.checkValidity())return;
    const[y,m]=picker.value.split('-').map(Number),value=key(new Date(y,m-1+delta,1,12)).slice(0,7);
    if(value<picker.min||value>picker.max)return;picker.value=value;render();
  }
  el('cal-prev').addEventListener('click',()=>move(-1));el('cal-next').addEventListener('click',()=>move(1));
  el('cal-today').addEventListener('click',()=>{picker.value=key(new Date()).slice(0,7);render();});
  picker.addEventListener('change',()=>{if(picker.reportValidity())render();});filter.addEventListener('change',render);
  el('cal-grid-view').addEventListener('click',()=>{mode='month';render();});el('cal-list-view').addEventListener('click',()=>{mode='list';render();});
  for(const id of ['cal-grid','cal-agenda'])el(id).addEventListener('click',event=>{const button=event.target.closest('[data-bill]');if(button)showBill(button.dataset.bill);});
  el('cal-close').addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',event=>{if(event.target===dialog){const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();}});
  el('cal-refresh').addEventListener('click',load);
  window.addEventListener('pageshow',event=>{if(event.persisted)load();});
  render();load();
})(typeof window!=='undefined'?window:globalThis);
