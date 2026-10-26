// UI translations only. Stored values, supplier names and OCR source text are not translated.
'use strict';
const uiSettings = JSON.parse(document.getElementById('billease-i18n').textContent);
function t(source, values = {}) {
  let text = Object.prototype.hasOwnProperty.call(uiSettings.messages, source)
    ? uiSettings.messages[source] : String(source);
  for (const [key, value] of Object.entries(values)) {
    text = text.split('{' + key + '}').join(String(value));
  }
  return text;
}
function uiLocale() { return {he: 'he-IL', ar: 'ar-IL-u-nu-latn', en: 'en-IL'}[uiSettings.locale] || 'he-IL'; }
function categoryLabel(value) { return value ? t(value) : ''; }
function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function fmtDate(value) {
  const raw = String(value || '');
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw);
  if (!match) return raw;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return new Intl.DateTimeFormat(uiLocale(), {day: '2-digit', month: '2-digit', year: 'numeric'}).format(date);
}

let uiDirty = false;
document.addEventListener('input', event => {
  const field = event.target;
  if (typeof field.setCustomValidity === 'function') field.setCustomValidity('');
  if (field.closest('form') && !field.closest('#language-form')) uiDirty = true;
});
document.addEventListener('change', event => {
  if (event.target.closest('form') && !event.target.closest('#language-form')) uiDirty = true;
});
// Browser-native validation messages otherwise follow the OS language, not the selected app language.
document.addEventListener('invalid', event => {
  const field = event.target;
  if (typeof field.setCustomValidity !== 'function') return;
  field.setCustomValidity('');
  const v = field.validity;
  let message = t('Enter a valid value.');
  if (v.valueMissing) message = t('This field is required.');
  else if (v.typeMismatch && field.type === 'email') message = t('Enter a valid email address.');
  else if (v.tooShort) message = t('Use at least {min} characters.', {min: field.minLength});
  else if (v.rangeUnderflow) message = t('Minimum value: {min}', {min: field.min});
  else if (v.rangeOverflow) message = t('Maximum value: {max}', {max: field.max});
  else if (v.patternMismatch) message = t('Use the required format.');
  field.setCustomValidity(message);
}, true);

document.addEventListener('DOMContentLoaded', () => {
  const register = document.getElementById('register-form') || document.getElementById('login-form');
  if(register && uiSettings.catalogs) {
    for(const button of register.querySelectorAll('input[name="preferred_language"]')) {
      button.addEventListener('change', () => {
        if(!button.checked || !uiSettings.catalogs[button.value])return;
        uiSettings.locale=button.value;uiSettings.messages=uiSettings.catalogs[button.value];
        document.documentElement.lang=button.value;
        document.documentElement.dir=button.value==='en'?'ltr':'rtl';
        for(const node of document.querySelectorAll('[data-i18n]'))node.textContent=t(node.dataset.i18n);
        document.title=t(register.id==='login-form'?'התחברות - BillEase':'הרשמה - BillEase');
      });
    }
  }
  const file = document.getElementById('scan-file');
  const fileName = document.getElementById('scan-file-name');
  if (file && fileName) file.addEventListener('change', () => {
    fileName.textContent = file.files[0]?.name || t('No file chosen');
    file.setCustomValidity('');
  });
});
