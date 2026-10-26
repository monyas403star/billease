/* Pure calculations: due-date accounting, integer cents, no estimated savings. */
(function(root) {
  'use strict';
  function analyze(bills, budgets, year, comparisonYear, today) {
    const cents = n => Math.round(Number(n) * 100);
    const valid = bills.filter(b => /^\d{4}-\d{2}-\d{2}$/.test(b.due_date || '') && Number.isFinite(Number(b.amount)) && Number(b.amount) >= 0);
    const paid = b => b.is_paid === true || Number(b.is_paid) === 1;
    const sum = list => list.reduce((s,b) => s+cents(b.amount),0);
    const annual = valid.filter(b => Number(b.due_date.slice(0,4)) === year);
    const paidRows = annual.filter(paid), openRows = annual.filter(b=>!paid(b));
    const categories = new Map();
    annual.forEach(b=>categories.set(b.category || 'Other',(categories.get(b.category || 'Other')||0)+cents(b.amount)));
    const ranked = [...categories].sort((a,b)=>b[1]-a[1]);
    // Compare completed months, rather than a partial year with a complete year.
    const currentYear=Number(today.slice(0,4)), currentMonth=Number(today.slice(5,7));
    const months = year===currentYear ? currentMonth-1 : year<currentYear ? 12 : 0;
    const inPeriod=(b,y)=>Number(b.due_date.slice(0,4))===y && Number(b.due_date.slice(5,7))<=months;
    const comparisonAvailable=months>0 && comparisonYear!==year && comparisonYear<currentYear;
    const a=valid.filter(b=>inPeriod(b,year)), b=valid.filter(b=>inPeriod(b,comparisonYear));
    const current=sum(a), previous=sum(b), difference=current-previous;
    const comparison=comparisonAvailable && a.length && b.length ? {current,previous,difference,percent:previous>0?Math.round(difference/previous*1000)/10:null,months}:null;
    const monthKey=today.slice(0,7);
    const budgetRows=budgets.map(b=>{
      const used=sum(valid.filter(x=>x.category===b.category && x.due_date.slice(0,7)===monthKey));
      const limit=cents(b.monthly_limit);
      return {category:b.category,used,limit,over:Math.max(0,used-limit),remaining:Math.max(0,limit-used)};
    });
    const late=valid.filter(b=>!paid(b)&&b.due_date<today);
    const next=new Date(today+'T12:00:00Z');next.setUTCDate(next.getUTCDate()+30);
    const end=next.toISOString().slice(0,10);
    const upcoming=valid.filter(b=>!paid(b)&&b.due_date>=today&&b.due_date<=end);
    return {total:sum(annual),paid:sum(paidRows),open:sum(openRows),count:annual.length,paidCount:paidRows.length,openCount:openRows.length,
      top:ranked[0]?{category:ranked[0][0],amount:ranked[0][1]}:null,comparison,months,budgetRows,
      overTotal:budgetRows.reduce((s,b)=>s+b.over,0),late:sum(late),lateCount:late.length,upcoming:sum(upcoming),upcomingCount:upcoming.length};
  }
  if(typeof module!=='undefined'&&module.exports)module.exports={analyze};
  else root.BillInsights={analyze};
})(typeof window!=='undefined'?window:globalThis);
