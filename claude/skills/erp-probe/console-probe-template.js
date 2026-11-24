// Template for an ERP-proxy console probe. Copy, fill in `targets` and `run`, delete this line.
//
// Question: <what this probe settles>
// Why: <the decision or bug that made the question matter, PR numbers, live observation>
// ✅ READ-ONLY
// Usage: open <api-origin>/ping in the Chrome profile logged into Canals (not impersonating),
//   paste into the DevTools console. Results download as <name>-results.json.
//   Change pacing while running: window.probePauseMs = 1000
(async () => {
  const ORIGIN = 'https://sandbox.api.canals.ai'; // https://api.canals.ai for production
  if (location.origin !== ORIGIN) {
    throw new Error(`Open ${ORIGIN} in the Chrome profile logged into Canals (not impersonating), then run this in its console.`);
  }
  const API_ORIGIN = location.origin;
  window.probePauseMs = window.probePauseMs ?? 500;
  let cooldownUntil = 0;
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  const targets = [
    {orgId: 0, erp: 'eclipse'},
  ];
  const results = [];
  const gaps = [];

  const retryDelayMs = (response, data) => {
    const header = Number(response.headers.get('retry-after'));
    const body = Number(data?.data?.retryAfterSeconds);
    const seconds = header > 0 ? header : body > 0 ? body : undefined;
    return seconds === undefined ? undefined : seconds * 1000;
  };

  const call = async ({orgId, erp}, method, path, body) => {
    const url = `${API_ORIGIN}/erp-proxy/${orgId}/${erp}/${path}`;
    while (true) {
      await sleep(Math.max(window.probePauseMs, cooldownUntil - Date.now()));
      const response = await fetch(url, {
        method,
        credentials: 'include',
        headers: {Accept: 'application/json', ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
        body: body === undefined ? undefined : JSON.stringify(body),
        signal: AbortSignal.timeout(60000),
      });
      const text = await response.text();
      let data;
      try { data = JSON.parse(text); } catch { data = text; }
      if (response.status !== 429) return {status: response.status, data};
      const delay = retryDelayMs(response, data);
      if (delay === undefined) throw new Error(`429 from ${path} with no retry delay, stopping`);
      cooldownUntil = Date.now() + delay;
      console.warn(`429, server asked for ${delay / 1000}s`);
    }
  };

  const preview = (data) => (typeof data === 'string' ? data : JSON.stringify(data)).slice(0, 300);

  for (const target of targets) {
    console.log(`%c=== org ${target.orgId} ===`, 'font-weight:bold');
    // One section per question. Record every call, print its HTTP status, and push
    // anything denied, missing or unreadable into `gaps` so it shows as NOT CHECKED.
    const res = await call(target, 'GET', 'Auth/GetAccessibleBranches');
    results.push({orgId: target.orgId, label: 'accessible-branches', ...res});
    console.log(`GetAccessibleBranches: HTTP ${res.status}`);
    if (res.status !== 200) {
      gaps.push({orgId: target.orgId, what: 'accessible branches', status: res.status, response: preview(res.data)});
      continue;
    }
  }

  console.log('%cNOT CHECKED', 'font-weight:bold');
  if (gaps.length) console.table(gaps);
  else console.log('nothing was skipped');
  console.log('Missing records and denied reads are unknown, never zero.');

  const blob = new Blob([JSON.stringify({at: new Date().toISOString(), gaps, results}, null, 2)], {type: 'application/json'});
  const link = document.createElement('a');
  const downloadUrl = URL.createObjectURL(blob);
  link.href = downloadUrl;
  link.download = 'probe-results.json';
  link.click();
  setTimeout(() => URL.revokeObjectURL(downloadUrl), 10000);
  console.log('Read-only probe finished. Results downloaded as probe-results.json. Adjust pacing while running with: window.probePauseMs = 1000');
  return {gaps, results};
})()
