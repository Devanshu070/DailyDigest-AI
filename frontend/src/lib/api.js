// src/lib/api.js — All FastAPI calls. Automatically injects Firebase ID token.

// In local dev: empty string → Next.js proxy forwards /api/* to localhost:8000
// In production: set NEXT_PUBLIC_API_URL to the full Render URL
const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

async function authFetch(url, options = {}) {
  const { getAuth } = await import("firebase/auth");
  const auth = getAuth();
  const user = auth.currentUser;

  const token = user ? await user.getIdToken() : null;

  const headers = {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  };

  const response = await fetch(`${BASE_URL}${url}`, { ...options, headers });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "API request failed");
  }

  return response.json();
}

// ── Health ──────────────────────────────────────────────────────────────────
export const getHealth = () => authFetch("/api/v1/health");
export const getPipelineStatus = (email) =>
  authFetch(`/api/v1/health/status?email=${encodeURIComponent(email)}`);

// ── Users ───────────────────────────────────────────────────────────────────
export const getUserProfile = (email) =>
  authFetch(`/api/v1/users/me?email=${encodeURIComponent(email)}`);

export const updateDigestTime = (email, digest_time) =>
  authFetch(`/api/v1/users/me/digest-time?email=${encodeURIComponent(email)}`, {
    method: "PATCH",
    body: JSON.stringify({ digest_time }),
  });

export const updateInterests = (email, interests_md) =>
  authFetch(`/api/v1/users/me/interests?email=${encodeURIComponent(email)}`, {
    method: "PATCH",
    body: JSON.stringify({ interests_md }),
  });

// ── Sources ─────────────────────────────────────────────────────────────────
export const getSources = (email) =>
  authFetch(`/api/v1/sources?email=${encodeURIComponent(email)}`);

export const createSource = (email, sources) =>
  authFetch(`/api/v1/sources?email=${encodeURIComponent(email)}`, {
    method: "POST",
    body: JSON.stringify({ sources }),
  });

export const deleteSource = (email, sourceId) =>
  authFetch(`/api/v1/sources/${sourceId}?email=${encodeURIComponent(email)}`, {
    method: "DELETE",
  }).catch(() => null); // 204 No Content — no JSON body

// ── Articles ─────────────────────────────────────────────────────────────────
export const getArticles = (email, limit = 20, offset = 0) =>
  authFetch(
    `/api/v1/articles?email=${encodeURIComponent(email)}&limit=${limit}&offset=${offset}`
  );

export const getArticleDetail = (email, articleId) =>
  authFetch(`/api/v1/articles/${articleId}?email=${encodeURIComponent(email)}`);

// ── Pipeline ─────────────────────────────────────────────────────────────────
export const runPipeline = (email) =>
  authFetch(`/api/v1/pipeline/run?email=${encodeURIComponent(email)}&manual=true`, {
    method: "POST",
  });

export const getRunState = () =>
  authFetch("/api/v1/pipeline/run-state");
