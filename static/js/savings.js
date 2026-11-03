/* What-if calculations only. Never edits bills or claims a supplier quote. */
(function(root) {
  'use strict';
  function cents(value) {
    if (typeof value !== 'number' && typeof value !== 'string') return null;
    const raw=String(value).trim();
    if(!/^\d{1,9}(?:\.\d{1,2})?$/.test(raw)) return null;
    const [whole,fraction='']=raw.split('.');
    const n=Number(whole)*100+Number(fraction.padEnd(2,'0'));
    return Number.isSafeInteger(n) ? n : null;
  }
  function validDate(value) {
    if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;
    const date=new Date(value+'T12:00:00Z');
    return Number.isFinite(date.getTime())&&date.toISOString().slice(0,10)===value;
  }
  function normalized(value) {return String(value||'').normalize('NFKC').trim().replace(/\s+/g,' ').toLowerCase();}
  function opportunities(bills) {
    const groups=new Map();
    for(const bill of bills) {
      if(!(bill.is_recurring===true||bill.is_recurring===1||bill.is_recurring==='1'))continue;
      // A finite debt is not a subscription that can be cancelled for savings.
      if(bill.payment_plan_id||Number(bill.installment_count)>0||Number(bill.installment_number)>0)continue;
      if(!['monthly','yearly'].includes(bill.recurrence)||!validDate(bill.due_date))continue;
      const amount=cents(bill.amount), supplier=String(bill.supplier||'').trim();
      if(amount===null||amount<=0||!supplier)continue;
      const key=JSON.stringify([normalized(supplier),normalized(bill.category),bill.recurrence]);
      if(!groups.has(key))groups.set(key,[]);
      groups.get(key).push({...bill,amountCents:amount});
    }
    return [...groups].map(([key,rows])=>{
      rows.sort((a,b)=>b.due_date.localeCompare(a.due_date)||Number(b.bill_id)-Number(a.bill_id));
      const latest=rows[0],previous=rows.find(b=>b.due_date<latest.due_date);
      const multiplier=latest.recurrence==='monthly'?12:1;
      return {key,supplier:latest.supplier,category:latest.category||'',frequency:latest.recurrence,
        dueDate:latest.due_date,current:latest.amountCents,annual:latest.amountCents*multiplier,
        increase:previous&&latest.amountCents>previous.amountCents?{
          cents:latest.amountCents-previous.amountCents,previous:previous.amountCents,date:previous.due_date}:null};
    }).sort((a,b)=>b.annual-a.annual||a.key.localeCompare(b.key));
  }
  function scenario(item,alternative) {
    const target=cents(alternative);
    if(target===null||target>item.current)return null;
    const multiplier=item.frequency==='monthly'?12:1;
    const annual=(item.current-target)*multiplier;
    return {baseline:item.current*multiplier,alternative:target*multiplier,annual,monthly:annual/12};
  }
  const api={cents,opportunities,scenario};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else root.BillSavings=api;
})(typeof window!=='undefined'?window:globalThis);
