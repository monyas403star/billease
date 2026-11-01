// reports page - charts + budgets + month drill-down
const MONTH_LABELS = Array.from({length: 12}, (_, month) => new Intl.DateTimeFormat(uiLocale(), {month: 'short'}).format(new Date(2024, month, 1)));

const yearInput = document.getElementById("year-input");
const year2Input = document.getElementById("year2-input");
const loadBtn = document.getElementById("load-btn");

const budgetForm = document.getElementById("budget-form");
const budCat = document.getElementById("bud-cat");
const budAmt = document.getElementById("bud-amt");
const budgetBody = document.getElementById("budget-body");

const modal = document.getElementById("drill-modal");
const modalClose = document.getElementById("drill-close");
const drillTitle = document.getElementById("drill-title");
const drillBody = document.getElementById("drill-body");

let monthChart = null;
let catChart = null;
let compareChart = null;
let allBills = [];
let currentYear = new Date().getFullYear();

if (typeof Chart !== 'undefined') {
  Chart.defaults.animation = false;
  Chart.defaults.locale = uiLocale();
  Chart.defaults.plugins.legend.rtl = uiSettings.locale !== 'en';
  Chart.defaults.plugins.legend.textDirection = uiSettings.locale === 'en' ? 'ltr' : 'rtl';
  Chart.defaults.font.family = '"Heebo", sans-serif';
}
let reportBusy = false;
let currentBudgets = [];
function localToday() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
}
function renderInsights() {
  const d = BillInsights.analyze(allBills, currentBudgets, currentYear, Number(year2Input.value), localToday());
  const money = cents => fmtMoney(cents/100);
  document.getElementById('annual-total').textContent=money(d.total);
  document.getElementById('annual-paid').textContent=money(d.paid);
  document.getElementById('annual-open').textContent=money(d.open);
  document.getElementById('annual-count').textContent=t('{count} saved bills',{count:d.count});
  document.getElementById('annual-change').textContent=d.comparison ? money(d.comparison.difference) : '—';
  document.getElementById('comparison-period').textContent=d.comparison
    ? t('Months 1–{months}: {year} vs {previous}',{months:d.months,year:currentYear,previous:year2Input.value})
    : t('Not enough data for a like-for-like comparison.');
  const insights=[];
  if(d.top)insights.push([t('Largest category'),t('{category}: {amount}. Review supplier plans and compare offers.',{category:categoryLabel(d.top.category),amount:money(d.top.amount)})]);
  if(d.comparison)insights.push([t('Change in bills due'),d.comparison.difference>0
    ? t('Bills increased by {amount}. Check the category chart to understand the change.',{amount:money(d.comparison.difference)})
    : d.comparison.difference<0 ? t('Bills decreased by {amount}. This reflects recorded bills, not verified savings.',{amount:money(-d.comparison.difference)})
    : t('The recorded total is unchanged.')]);
  insights.push([t('Next 30 days'),t('{count} open bills totaling {amount}. Reserve this amount in your payment plan.',{count:d.upcomingCount,amount:money(d.upcoming)})]);
  if(d.lateCount)insights.push([t('Overdue bills'),t('{count} overdue bills totaling {amount}. Check payment status to help avoid possible late charges.',{count:d.lateCount,amount:money(d.late)})]);
  for(const row of d.budgetRows.filter(x=>x.over>0))insights.push([t('Budget alert'),t('{category} exceeds this month’s limit by {amount}. Review the bills and adjust optional spending.',{category:categoryLabel(row.category),amount:money(row.over)})]);
  if(!currentBudgets.length)insights.push([t('Set your first budget'),t('Choose a monthly limit below to see exactly how much remains or exceeds your limit.')]);
  if(!d.count)insights.unshift([t('No bills in selected year'),t('Add bills or select another year. No expenses or savings are inferred from missing data.')]);
  document.getElementById('money-insights').innerHTML=insights.map(([title,text])=>`<article class="insight-item"><h3>${escapeHtml(title)}</h3><p>${escapeHtml(text)}</p></article>`).join('');
}

function categoryShares(categories) {
  const entries=Object.entries(categories).map(([name,amount])=>({name,cents:Math.round(Number(amount)*100)})).filter(row=>Number.isFinite(row.cents)&&row.cents>0);
  const total=entries.reduce((sum,row)=>sum+row.cents,0);
  return entries.map(row=>({...row,amount:row.cents/100,share:row.cents/total}));
}
function shareLabel(share) {
  return new Intl.NumberFormat(uiLocale(),{style:'percent',maximumFractionDigits:1}).format(share);
}
function renderCategoryShares(categories) {
  const rows=categoryShares(categories);
  document.getElementById('category-share-body').innerHTML=rows.length
    ? rows.map(row=>`<tr><td>${escapeHtml(categoryLabel(row.name))}</td><td>${escapeHtml(fmtMoney(row.amount))}</td><td>${escapeHtml(shareLabel(row.share))}</td></tr>`).join('')
    : `<tr><td colspan="3" class="muted">${escapeHtml(t('No category amounts in selected year.'))}</td></tr>`;
  return rows;
}
// Labels are local to this chart; no additional external plugin is required.
const categoryPercentPlugin={
  id:'categoryPercentLabels',
  afterDatasetsDraw(chart) {
    const values=chart.data.datasets[0].data;
    const total=values.reduce((sum,value)=>sum+Number(value),0);
    if(!total)return;
    const ctx=chart.ctx;ctx.save();
    ctx.textAlign='center';ctx.textBaseline='middle';ctx.font='bold 13px Heebo, sans-serif';
    chart.getDatasetMeta(0).data.forEach((arc,index)=>{
      if(!chart.getDataVisibility(index))return;
      const share=Number(values[index])/total;
      if(share<0.04 || arc.circumference<0.18)return; // Small slices remain in the table and tooltip.
      const angle=(arc.startAngle+arc.endAngle)/2;
      const radius=(arc.innerRadius+arc.outerRadius)/2;
      const x=arc.x+Math.cos(angle)*radius,y=arc.y+Math.sin(angle)*radius;
      const label=shareLabel(share);
      ctx.lineWidth=3;ctx.strokeStyle='rgba(15,23,42,.85)';ctx.strokeText(label,x,y);
      ctx.fillStyle='#fff';ctx.fillText(label,x,y);
    });
    ctx.restore();
  }
};

async function loadReport() {
  if(reportBusy)return;
  if(!yearInput.checkValidity() || !year2Input.checkValidity()) {yearInput.reportValidity();year2Input.reportValidity();return;}
  reportBusy=true;loadBtn.disabled=true;
  const error=document.getElementById('report-error');error.textContent='';
  try {
  currentYear = parseInt(yearInput.value || new Date().getFullYear());
  const year2 = year2Input.value || (currentYear - 1);

  const [summary, compare, bills] = await Promise.all([
    apiGet(`/api/reports/summary?year=${currentYear}`),
    apiGet(`/api/reports/compare?year1=${currentYear}&year2=${year2}`),
    apiGet("/api/bills"),
  ]);
  if (!summary.ok || !bills.ok) throw new Error('report');

  if (bills.ok) allBills = bills.bills;

  const categoryRows=renderCategoryShares(summary.categories);
  if(typeof Chart !== 'undefined') {
  // monthly bar with click handler
  const monthCtx = document.getElementById("month-chart").getContext("2d");
  if (monthChart) monthChart.destroy();
  monthChart = new Chart(monthCtx, {
    type: "bar",
    data: {
      labels: MONTH_LABELS,
      datasets: [{
        label: t("הוצאות"),
        data: summary.months,
        backgroundColor: "#4f46e5",
        borderRadius: 6,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      onClick: (evt, items) => {
        if (items.length === 0) return;
        const monthIdx = items[0].index;
        openDrill(currentYear, monthIdx + 1);
      },
    }
  });

  // category donut
  const catCtx = document.getElementById("cat-chart").getContext("2d");
  if (catChart) catChart.destroy();
  const catValues = categoryRows.map(row=>row.amount);
  const colors = ["#4f46e5","#06b6d4","#f59e0b","#ef4444",
                  "#8b5cf6","#10b981","#6366f1","#f97316",
                  "#ec4899","#6b7280"];
  catChart = new Chart(catCtx, {
    type: "doughnut",
    data: { labels: categoryRows.map(row=>`${categoryLabel(row.name)} — ${shareLabel(row.share)}`), datasets: [{ data: catValues, backgroundColor: colors }] },
    plugins:[categoryPercentPlugin],
    options: { responsive: true, maintainAspectRatio: false,
      plugins:{tooltip:{callbacks:{label:context=>{
        const row=categoryRows[context.dataIndex];
        return `${categoryLabel(row.name)}: ${fmtMoney(row.amount)} (${shareLabel(row.share)})`;
      }}}}
    }
  });

  // year-over-year line
  if (compare.ok) {
    const cmpCtx = document.getElementById("compare-chart").getContext("2d");
    if (compareChart) compareChart.destroy();
    compareChart = new Chart(cmpCtx, {
      type: "line",
      data: {
        labels: MONTH_LABELS,
        datasets: [
          { label: String(compare.year1), data: compare.data1,
            borderColor: "#4f46e5", backgroundColor: "rgba(79,70,229,.1)",
            tension: 0.3, fill: true },
          { label: String(compare.year2), data: compare.data2,
            borderColor: "#06b6d4", backgroundColor: "rgba(6,182,212,.1)",
            tension: 0.3, fill: true },
        ]
      },
      options: { responsive: true, maintainAspectRatio: false }
    });
  }

  } else error.textContent=t('Charts could not load. The summary and budget analysis are still available.');
  await loadBudgets();
  } catch(error) {
    document.getElementById('report-error').textContent=t('Reports could not load. Please try again.');
    for(const id of ['annual-total','annual-paid','annual-open','annual-change'])document.getElementById(id).textContent='—';
    document.getElementById('money-insights').replaceChildren();
    document.getElementById('category-share-body').replaceChildren();
  } finally {reportBusy=false;loadBtn.disabled=false;}
}

async function openDrill(year, month) {
  drillTitle.textContent = t("חשבונות לחודש {month} {year}", {month: MONTH_LABELS[month - 1], year});
  drillBody.innerHTML = `<tr><td colspan="5" class="muted">${t("טוען...")}</td></tr>`;
  modal.classList.remove("hidden");
  const res = await apiGet(`/api/bills/by-month?year=${year}&month=${month}`);
  if (!res.ok || res.bills.length === 0) {
    drillBody.innerHTML = `<tr><td colspan="5" class="muted">${t("אין חשבונות בחודש זה")}</td></tr>`;
    return;
  }
  drillBody.innerHTML = res.bills.map(b => `
    <tr>
      <td>${escapeHtml(b.supplier || "")} ${installmentBadge(b)}</td>
      <td>${fmtMoney(b.amount)}</td>
      <td>${escapeHtml(categoryLabel(b.category || ""))}</td>
      <td>${escapeHtml(fmtDate(b.due_date))}</td>
      <td>${statusBadge(b)}</td>
    </tr>`).join("");
}

modalClose.addEventListener("click", () => modal.classList.add("hidden"));
modal.addEventListener("click", (e) => {
  if (e.target === modal) modal.classList.add("hidden");
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") modal.classList.add("hidden");
});

async function loadCategoriesForBudget() {
  const res = await apiGet("/api/categories");
  if (res.ok) {
    budCat.replaceChildren(...res.categories.map(c => new Option(categoryLabel(c), c)));
  }
}

async function loadBudgets() {
  const res = await apiGet("/api/budgets");
  if (!res.ok) throw new Error("budgets");
  currentBudgets=res.budgets;
  renderInsights();
  if (res.budgets.length === 0) {
    budgetBody.innerHTML = `<tr><td colspan="6" class="muted">${t("לא הוגדרו תקציבים")}</td></tr>`;
    return;
  }
  const analyzed=BillInsights.analyze(allBills,currentBudgets,currentYear,Number(year2Input.value),localToday());
  budgetBody.innerHTML = res.budgets.map((b,index) => {
    const spent=analyzed.budgetRows[index].used/100;
    const over = spent > b.monthly_limit;
    const near = !over && spent > b.monthly_limit * 0.8;
    const badge = over ? `<span class="badge late">${t("חריגה")}</span>`
                  : near ? `<span class="badge warn">${t("קרוב לתקרה")}</span>`
                  : `<span class="badge ok">${t("בסדר")}</span>`;
    return `
      <tr>
        <td>${escapeHtml(categoryLabel(b.category))}</td>
        <td>${fmtMoney(b.monthly_limit)}</td>
        <td>${fmtMoney(spent)}</td>
        <td>${fmtMoney(Math.max(0,spent-Number(b.monthly_limit)))}</td>
        <td>${badge}</td>
        <td><button class="btn small danger" data-bdel="${escapeHtml(b.category)}">${t("מחיקה")}</button></td>
      </tr>`;
  }).join("");
}

budgetForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const data = { category: budCat.value, monthly_limit: budAmt.value };
    const res = await apiSend("/api/budgets", "POST", data);
    if(!res.ok)throw new Error(res.error || t('Reports could not load. Please try again.'));
    budAmt.value = "";
    await loadBudgets();
  } catch(error) {document.getElementById('report-error').textContent=error.message || t('Reports could not load. Please try again.');}
});

budgetBody.addEventListener("click", async (e) => {
  const cat = e.target.getAttribute("data-bdel");
  if (!cat) return;
  if (!confirm(t("למחוק את התקציב לקטגוריה זו?"))) return;
  try {
    const res=await apiSend(`/api/budgets/${encodeURIComponent(cat)}`, "DELETE");
    if(!res.ok)throw new Error(res.error || t('Reports could not load. Please try again.'));
    await loadBudgets();
  } catch(error) {document.getElementById('report-error').textContent=error.message || t('Reports could not load. Please try again.');}
});

loadBtn.addEventListener("click", loadReport);
yearInput.value = new Date().getFullYear();
year2Input.value = new Date().getFullYear() - 1;
loadCategoriesForBudget().catch(()=>{document.getElementById('report-error').textContent=t('Reports could not load. Please try again.');});
loadReport();
