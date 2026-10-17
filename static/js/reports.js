// reports page - charts + budgets + month drill-down
const MONTH_LABELS = ["ינו'","פבר'","מרץ","אפר'","מאי","יוני",
                      "יולי","אוג'","ספט'","אוק'","נוב'","דצמ'"];

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

Chart.defaults.font.family = '"Heebo", sans-serif';

async function loadReport() {
  currentYear = parseInt(yearInput.value || new Date().getFullYear());
  const year2 = year2Input.value || (currentYear - 1);

  const [summary, compare, bills] = await Promise.all([
    apiGet(`/api/reports/summary?year=${currentYear}`),
    apiGet(`/api/reports/compare?year1=${currentYear}&year2=${year2}`),
    apiGet("/api/bills"),
  ]);
  if (!summary.ok) return;

  if (bills.ok) allBills = bills.bills;

  // monthly bar with click handler
  const monthCtx = document.getElementById("month-chart").getContext("2d");
  if (monthChart) monthChart.destroy();
  monthChart = new Chart(monthCtx, {
    type: "bar",
    data: {
      labels: MONTH_LABELS,
      datasets: [{
        label: "הוצאות",
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
  const catNames = Object.keys(summary.categories);
  const catValues = Object.values(summary.categories);
  const colors = ["#4f46e5","#06b6d4","#f59e0b","#ef4444",
                  "#8b5cf6","#10b981","#6366f1","#f97316",
                  "#ec4899","#6b7280"];
  catChart = new Chart(catCtx, {
    type: "doughnut",
    data: { labels: catNames, datasets: [{ data: catValues, backgroundColor: colors }] },
    options: { responsive: true, maintainAspectRatio: false }
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

  loadBudgets();
}

async function openDrill(year, month) {
  drillTitle.textContent = `חשבונות לחודש ${MONTH_LABELS[month - 1]} ${year}`;
  drillBody.innerHTML = '<tr><td colspan="5" class="muted">טוען...</td></tr>';
  modal.classList.remove("hidden");
  const res = await apiGet(`/api/bills/by-month?year=${year}&month=${month}`);
  if (!res.ok || res.bills.length === 0) {
    drillBody.innerHTML = '<tr><td colspan="5" class="muted">אין חשבונות בחודש זה</td></tr>';
    return;
  }
  drillBody.innerHTML = res.bills.map(b => `
    <tr>
      <td>${b.supplier}</td>
      <td>${fmtMoney(b.amount)}</td>
      <td>${b.category || ""}</td>
      <td>${b.due_date}</td>
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
    budCat.innerHTML = res.categories.map(c => `<option value="${c}">${c}</option>`).join("");
  }
}

async function loadBudgets() {
  const res = await apiGet("/api/budgets");
  if (!res.ok) return;
  if (res.budgets.length === 0) {
    budgetBody.innerHTML = '<tr><td colspan="5" class="muted">לא הוגדרו תקציבים</td></tr>';
    return;
  }
  const now = new Date();
  const month = now.getMonth();
  const year = now.getFullYear();
  budgetBody.innerHTML = res.budgets.map(b => {
    const spent = allBills
      .filter(x => {
        const d = new Date(x.due_date);
        return x.category === b.category && d.getMonth() === month && d.getFullYear() === year;
      })
      .reduce((s, x) => s + x.amount, 0);
    const over = spent > b.monthly_limit;
    const near = !over && spent > b.monthly_limit * 0.8;
    const badge = over ? '<span class="badge late">חריגה</span>'
                  : near ? '<span class="badge warn">קרוב לתקרה</span>'
                  : '<span class="badge ok">בסדר</span>';
    return `
      <tr>
        <td>${b.category}</td>
        <td>${fmtMoney(b.monthly_limit)}</td>
        <td>${fmtMoney(spent)}</td>
        <td>${badge}</td>
        <td><button class="btn small danger" data-bdel="${b.category}">מחיקה</button></td>
      </tr>`;
  }).join("");
}

budgetForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const data = { category: budCat.value, monthly_limit: budAmt.value };
  const res = await apiSend("/api/budgets", "POST", data);
  if (res.ok) {
    budAmt.value = "";
    loadBudgets();
  }
});

budgetBody.addEventListener("click", async (e) => {
  const cat = e.target.getAttribute("data-bdel");
  if (!cat) return;
  if (!confirm("למחוק את התקציב לקטגוריה זו?")) return;
  await apiSend(`/api/budgets/${encodeURIComponent(cat)}`, "DELETE");
  loadBudgets();
});

loadBtn.addEventListener("click", loadReport);
yearInput.value = new Date().getFullYear();
year2Input.value = new Date().getFullYear() - 1;
loadCategoriesForBudget();
loadReport();
