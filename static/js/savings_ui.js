/* This scenario stays in this page only; no bill updates or account writes. */
(function() {
  'use strict';
  const host=document.getElementById('savings-list');
  if(!host)return;
  const status=document.getElementById('savings-status');
  const reload=document.getElementById('savings-reload');
  let items=[];
  const money=c=>fmtMoney(c/100);
  const safe=escapeHtml;
  function totals() {
    let annual=0,baseline=0,alternative=0,count=0;
    host.querySelectorAll('input[data-alternative]').forEach(input=>{
      const item=items[Number(input.dataset.alternative)], box=document.getElementById('saving-result-'+input.dataset.alternative);
      input.removeAttribute('aria-invalid');
      if(input.value===''){box.textContent=t('Enter an alternative price to calculate.');return;}
      const result=BillSavings.scenario(item,input.value);
      if(!result){input.setAttribute('aria-invalid','true');box.textContent=t('Enter a price from 0 up to the recorded price, with at most two decimals.');return;}
      count++;annual+=result.annual;baseline+=result.baseline;alternative+=result.alternative;
      box.textContent=t('Estimated reduction: {monthly} per month on average; {annual} per year.',{monthly:money(result.monthly),annual:money(result.annual)});
    });
    document.getElementById('savings-baseline').textContent=count?money(baseline):'—';
    document.getElementById('savings-alternative').textContent=count?money(alternative):'—';
    document.getElementById('savings-monthly').textContent=count?money(annual/12):'—';
    document.getElementById('savings-annual').textContent=count?money(annual):'—';
    document.getElementById('savings-count').textContent=t('{count} alternatives included. Only rows with a valid alternative price are counted.',{count});
  }
  function render() {
    host.replaceChildren();
    if(!items.length){status.textContent=t('No eligible recurring bills yet. Add a monthly or yearly recurring bill to explore savings. Finite installments are excluded.');totals();return;}
    status.textContent=t('Review the latest saved bill for each supplier, category and frequency. Confirm that each commitment is still active.');
    items.forEach((item,index)=>{
      const card=document.createElement('article');card.className='savings-item';
      const frequency=t(item.frequency==='monthly'?'Monthly recurring bill':'Yearly recurring bill');
      card.innerHTML=`<h3>${safe(item.supplier)}</h3><p class="muted">${safe(frequency)} · ${safe(t(item.category))}</p>
        <p>${safe(t('Latest saved due date: {date}',{date:item.dueDate}))}</p>
        <p>${safe(t('Recorded price per billing period: {amount}',{amount:money(item.current)}))}</p>
        <p>${safe(t('Annual cost if this price repeats: {amount}',{amount:money(item.annual)}))}</p>
        <label for="saving-price-${index}">${safe(t('Alternative price per same billing period (ILS)'))}</label>
        <input id="saving-price-${index}" data-alternative="${index}" type="number" inputmode="decimal" min="0" max="${item.current/100}" step="0.01" aria-describedby="saving-result-${index}" placeholder="${safe(t('Enter a price you choose'))}">
        <p class="savings-result" id="saving-result-${index}">${safe(t('Enter an alternative price to calculate.'))}</p>`;
      if(item.increase){
        const warning=document.createElement('p');warning.className='savings-warning';
        warning.textContent=t('Recorded increase of {amount} compared with {date}. Usage or billing coverage may have changed; review the bill before acting.',{amount:money(item.increase.cents),date:item.increase.date});
        card.append(warning);
      }
      host.append(card);
    });
    totals();
  }
  async function load() {
    reload.disabled=true;items=[];host.replaceChildren();totals();
    status.textContent=t('Loading recurring bills...');
    try {
      const response=await fetch('/api/bills',{credentials:'same-origin',cache:'no-store'});
      if(!response.ok)throw new Error('load');
      const data=await response.json();
      if(!data.ok||!Array.isArray(data.bills))throw new Error('load');
      items=BillSavings.opportunities(data.bills);render();
    }catch(error){status.textContent=t('Savings data could not load. Sign in and try again.');}
    finally{reload.disabled=false;}
  }
  host.addEventListener('input',event=>{if(event.target.matches('input[data-alternative]'))totals();});
  document.getElementById('savings-reset').addEventListener('click',()=>{host.querySelectorAll('input').forEach(input=>{input.value='';});totals();});
  reload.addEventListener('click',load);
  load();
})();
