// 轻量 API 客户端；类型由 `npm run gen:api` 从后端 OpenAPI 生成（api-types.ts）
const TOKEN_KEY = 'outreach_token';

export function getToken(): string | null {
  return typeof window === 'undefined' ? null : localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(init.headers as Record<string, string>),
  };
  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const resp = await fetch(path, { ...init, headers });
  if (resp.status === 401 && typeof window !== 'undefined') {
    clearToken();
    window.location.href = '/login/';
    throw new Error('未登录');
  }
  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail.detail ?? `请求失败 (${resp.status})`);
  }
  if (resp.status === 204) return undefined as T;
  return resp.json();
}
