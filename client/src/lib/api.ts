// client/src/lib/api.ts

const BASE = "http://localhost:8000";

function getToken(): string {
  return localStorage.getItem("access_token") ?? "";
}

export async function apiGet(path: string) {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${getToken()}`,
    },
  });
  return res.json();
}

export async function apiPost(path: string, body?: unknown) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${getToken()}`,
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

export async function apiDelete(path: string) {
  const res = await fetch(`${BASE}${path}`, {
    method: "DELETE",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${getToken()}`,
    },
  });
  return res.json();
}