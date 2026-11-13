(() => {
  const select = document.getElementById('feedback-problem');
  const issue = document.getElementById('feedback-issue');
  const wrap = document.getElementById('feedback-issue-wrap');
  const form = document.querySelector('.feedback-form');
  function update() { wrap.hidden = select.value !== '1'; issue.required = select.value === '1'; }
  select.addEventListener('change', update);
  update();
  form.addEventListener('submit', () => { form.querySelector('button[type="submit"]').disabled = true; });
  window.addEventListener('pageshow', () => { form.querySelector('button[type="submit"]').disabled = false; });
})();
