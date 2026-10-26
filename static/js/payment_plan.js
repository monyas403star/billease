// Fixed schedules preserve every payment's amount/date; recurring bills remain a separate mode.
window.BillPaymentPlan = (() => {
  const mode = document.getElementById('payment-mode');
  const panel = document.getElementById('installment-panel');
  const count = document.getElementById('installment-count');
  const start = document.getElementById('installment-start');
  const total = document.getElementById('installment-total');
  const rows = document.getElementById('installment-rows');
  const summary = document.getElementById('installment-summary');
  const hint = document.getElementById('plan-hint');
  const form = document.getElementById('bill-form');
  const amount = form.elements.namedItem('amount');
  const due = form.elements.namedItem('due_date');
  const recurring = document.getElementById('rec-toggle');
  const period = document.getElementById('rec-period');
  const key = (globalThis.crypto?.randomUUID?.() || String(Date.now()) + '_' + Math.random().toString(36).slice(2));
  let changing = false;
  let pendingRows = [];
  const integer = v => /^\d+$/.test(String(v)) ? Number(v) : NaN;
  const limits = () => {
    const n = integer(count.value), first = integer(start.value);
    return n >= 1 && n <= 60 && first >= 1 && first <= n ? {n, first, length:n-first+1} : null;
  };
  const readRows = () => Array.from(rows.querySelectorAll('.plan-payment')).map(row => ({
    amount:row.querySelector('.plan-amount').value, due_date:row.querySelector('.plan-date').value,
  }));
  const cents = v => {
    if (!/^\d+(?:\.\d{1,2})?$/.test(String(v))) return null;
    const n = Math.round(Number(v)*100);
    return Number.isSafeInteger(n) && n > 0 ? n : null;
  };
  function updateSummary() {
    const values = readRows(), amounts = values.map(row=>cents(row.amount));
    const valid = amounts.every(value=>value!==null);
    const sum = valid ? amounts.reduce((a,b)=>a+b,0) : 0;
    summary.textContent = t('Remaining payments: {count}. Total: {total}', {
      count:values.length, total:valid ? fmtMoney(sum/100) : t('Complete the amounts'),
    });
    summary.className = total.value && valid && cents(total.value)!==sum ? 'form-msg err' : 'muted';
    if (summary.className==='form-msg err') summary.textContent += ' ' + t('The installment sum differs from the stated total.');
  }
  function render(values=[]) {
    const limit = limits();
    if (!limit) {pendingRows=values;hint.textContent=t('Check the installment count and first number.'); return;}
    start.max=String(limit.n);
    rows.replaceChildren();
    for(let i=0;i<limit.length;i++) {
      const row=document.createElement('div'); row.className='plan-row plan-payment';row.dataset.number=String(limit.first+i);
      const label=document.createElement('span');label.textContent=`${limit.first+i}/${limit.n}`;label.className='payment-number';
      const a=document.createElement('input');a.type='number';a.min='0.01';a.step='0.01';a.className='plan-amount';a.required=true;
      a.setAttribute('aria-label',t('Amount for installment {number}',{number:limit.first+i}));
      const d=document.createElement('input');d.type='date';d.className='plan-date';d.required=true;
      d.setAttribute('aria-label',t('Date for installment {number}',{number:limit.first+i}));
      a.value=values[i]?.amount ?? '';d.value=values[i]?.due_date ?? '';
      row.append(label,a,d);rows.append(row);
      for(const field of [a,d]) field.addEventListener('input',()=>{
        if(i===0) {amount.value=a.value;due.value=d.value;}
        updateSummary();
      });
    }
    if(rows.firstElementChild) {amount.value=rows.firstElementChild.querySelector('.plan-amount').value;due.value=rows.firstElementChild.querySelector('.plan-date').value;}
    updateSummary();
  }
  function updateMode(values) {
    const finite=mode.value==='installments';
    panel.classList.toggle('hidden',!finite);
    recurring.checked=mode.value==='recurring';
    period.classList.toggle('hidden',!recurring.checked);
    for(const field of [count,start,total]) field.disabled=!finite;
    for(const field of rows.querySelectorAll('input')) field.disabled=!finite;
    document.getElementById('amount-label').textContent=t(finite?'First remaining installment amount (ILS)':'סכום (ש"ח)');
    document.getElementById('due-label').textContent=t(finite?'First remaining due date':'תאריך פירעון');
    if(finite) render(values || [{amount:amount.value,due_date:due.value}]);
    if(!changing) hint.textContent=t(recurring.checked?'Repeats until you stop it. For a fixed number of payments, choose an installment plan.':finite?'Review every amount and date before saving.':'');
  }
  function monthlyDates(first,length) {
    if(!/^\d{4}-\d{2}-\d{2}$/.test(first)) return [];
    const [year,month,day]=first.split('-').map(Number);
    return Array.from({length},(_,i)=>{
      const m=month-1+i,y=year+Math.floor(m/12),monthIndex=m%12;
      const lastDay=new Date(y,monthIndex+1,0).getDate();
      return `${y}-${String(monthIndex+1).padStart(2,'0')}-${String(Math.min(day,lastDay)).padStart(2,'0')}`;
    });
  }
  function generate(fromScan=false) {
    const limit=limits();
    if(!limit || cents(amount.value)===null || !due.value || !due.checkValidity()) {
      hint.textContent=t('Enter a valid first amount, first date and installment count.');return;
    }
    if(!fromScan && readRows().slice(1).some(row=>row.amount || row.due_date) && !confirm(t('Replace the current schedule with equal monthly payments?'))) return;
    const dates=monthlyDates(due.value,limit.length);
    render(dates.map(date=>({amount:amount.value,due_date:date})));
    if(!total.value) total.value=(cents(amount.value)*limit.length/100).toFixed(2);
    updateSummary();
    hint.textContent=t('Monthly schedule generated. Adjust rows if amounts or dates differ.');
  }
  mode.addEventListener('change',()=>updateMode());
  for(const field of [count,start]) field.addEventListener('change',()=>{
    const limit=limits();if(!limit)return;
    if(pendingRows.length){const saved=pendingRows;pendingRows=[];render(saved);return;}
    const existing=new Map(Array.from(rows.children).map(row=>[Number(row.dataset.number),{amount:row.querySelector('.plan-amount').value,due_date:row.querySelector('.plan-date').value}]));
    render(Array.from({length:limit.length},(_,i)=>existing.get(limit.first+i)||(i===0?{amount:amount.value,due_date:due.value}:{})));
  });
  total.addEventListener('input',updateSummary);
  document.getElementById('generate-installments').addEventListener('click',()=>generate(false));
  for(const field of [amount,due]) field.addEventListener('input',()=>{
    if(mode.value==='installments' && rows.firstElementChild) {
      rows.firstElementChild.querySelector('.plan-amount').value=amount.value;
      rows.firstElementChild.querySelector('.plan-date').value=due.value;updateSummary();
    }
  });
  function reset() {changing=true;pendingRows=[];mode.value='single';count.value='2';start.value='1';total.value='';rows.replaceChildren();hint.textContent='';updateMode();changing=false;}
  function apply(plan) {
    if(!plan || !['recurring','installments'].includes(plan.kind)) return;
    changing=true;
    if(plan.kind==='recurring') {
      mode.value='recurring';period.value=plan.frequency || 'monthly';
      if(plan.amount_per_payment!=null) amount.value=plan.amount_per_payment;
      if(plan.first_due_date) due.value=plan.first_due_date;
      updateMode();hint.textContent=t('Repeats until you stop it. For a fixed number of payments, choose an installment plan.');
    } else {
      const values=Array.isArray(plan.payments)?plan.payments:[];
      const first=Number(plan.start_number)||1;
      const n=Math.max(Number(plan.count)||0,first+values.length-1,first);
      mode.value='installments';start.value=plan.start_number ?? '';count.value=Math.min(n,60);
      let firstAmount=values[0]?.amount ?? plan.amount_per_payment ?? null;
      // Only suggest equal installments from an explicit monthly total when division is exact.
      if(firstAmount==null && plan.frequency==='monthly' && plan.total_amount && plan.count) {
        const all=cents(String(plan.total_amount));
        if(all!==null && all%plan.count===0) firstAmount=all/plan.count/100;
      }
      amount.value=firstAmount ?? '';due.value=values[0]?.due_date || plan.first_due_date || '';
      total.value=first===1 && plan.total_amount!=null ? plan.total_amount : '';
      updateMode(values.length?values:[{amount:amount.value,due_date:due.value}]);
      if(plan.start_number && !values.length && plan.frequency==='monthly' && firstAmount!=null && due.value) generate(true);
      hint.textContent=t('An installment plan was detected. Review the full schedule and payment count.');
      if(!plan.count) hint.textContent+=' '+t('The total count was not confirmed. Check it against the document.');
    }
    changing=false;
  }
  reset();
  return {reset,apply,data:()=>mode.value==='installments'?{
    payment_mode:mode.value, installment_count:count.value, installment_start:start.value,
    installment_total:total.value, installments:readRows(), request_key:key,
  }:{payment_mode:mode.value},isFinite:()=>mode.value==='installments'};
})();
