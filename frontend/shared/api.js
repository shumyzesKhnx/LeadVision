// All requests use this server and the existing backend contracts.
export class ApiError extends Error {
  constructor(message, status, details = []) { super(message); this.status = status; this.details = details; }
}
export async function api(path, {method = 'GET', body, revision, key} = {}) {
  const headers = {Accept: 'application/json'};
  if (revision !== undefined) headers['If-Match'] = `"${revision}"`;
  if (key) headers['Idempotency-Key'] = key;
  if (body !== undefined && !(body instanceof FormData)) headers['Content-Type'] = 'application/json';
  let response;
  try { response = await fetch(`/api/v1${path}`, {method, headers, body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body)}); }
  catch { throw new ApiError('Cannot connect right now. Please refresh the page or try again shortly.', 0); }
  if (response.status === 204) return null;
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(data?.error?.message || `Request failed (${response.status}).`, response.status, data?.error?.details || []);
  return data;
}
export async function all(path) {
  const items = [];
  for (let page = 1; ; page++) {
    const result = await api(`${path}${path.includes('?') ? '&' : '?'}page_size=100&page=${page}`);
    items.push(...result.items);
    if (items.length >= result.total || !result.items.length) return items;
  }
}
export const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
export const errorText = error => [error.message, ...(error.details || []).map(item => `${item.field}: ${item.reason}`)].join(' ');
