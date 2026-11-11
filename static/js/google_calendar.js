(() => {
  'use strict';
  const status = document.getElementById('google-cal-status');
  const connect = document.getElementById('google-cal-connect');
  const disconnect = document.getElementById('google-cal-disconnect');
  let busy = false;
  async function load() {
    if (busy || document.hidden) return;
    try {
      const r = await apiGet('/api/calendar/google/status');
      if (!r.ok) throw new Error('status');
      connect.hidden = r.connected || !r.configured;
      disconnect.hidden = !r.connected;
      status.textContent = t(!r.configured ? 'Calendar connection is not configured yet.' :
        !r.connected ? 'Google Calendar is not connected.' :
        r.error === 'reconnect' ? 'Google access needs attention. Disconnect, remove the old BillEase calendar in Google, then reconnect.' :
        r.error ? 'Bills are saved. Google sync will retry automatically.' :
        r.pending ? 'Connected. Sending saved bills to Google...' : 'Connected. Saved bills are synced to Google.');
    } catch (_) { status.textContent = t('Unable to load the connection. Sign in again and refresh.'); }
  }
  connect.addEventListener('click', async () => {
    busy = true; connect.disabled = true;
    try {
      const r = await apiSend('/api/calendar/google/connect', 'POST', {});
      if (!r.ok || !r.url) throw new Error('connect');
      const u = new URL(r.url);
      if (u.origin !== 'https://accounts.google.com') throw new Error('url');
      window.location.assign(u.href);
    } catch (_) { status.textContent = t('Connection failed. Refresh and try again.'); }
    finally { busy = false; connect.disabled = false; }
  });
  disconnect.addEventListener('click', async () => {
    if (!confirm(t('Stop automatic calendar updates? Existing Google events will remain.'))) return;
    busy = true; disconnect.disabled = true;
    try {
      const r = await apiSend('/api/calendar/google/disconnect', 'POST', {});
      if (!r.ok) throw new Error('disconnect');
      busy = false; await load();
      if (!r.revoked) status.textContent = t('Disconnected locally. Remove BillEase access in your Google account permissions too.');
    } catch (_) { status.textContent = t('Connection failed. Refresh and try again.'); }
    finally { busy = false; disconnect.disabled = false; }
  });
  if (new URLSearchParams(location.search).get('google') === 'error') {
    status.textContent = t('Connection was not completed. Refresh and try again.');
    connect.hidden = false;
  } else load();
  setInterval(load, 10000);
})();
