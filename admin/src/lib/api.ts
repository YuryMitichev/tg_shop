const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const ADMIN_API = `${API_BASE}/api/admin`;
const SUPER_ADMIN_API = `${API_BASE}/api/super-admin`;
export const SHOP_API = `${API_BASE}/api/shop`;

export function photoUrl(photoId: number): string {
  return `${SHOP_API}/photo/${photoId}`;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  base: string = ADMIN_API,
): Promise<T> {
  const headers: Record<string, string> = {
    ...((options.headers as Record<string, string>) || {}),
  };

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${base}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (res.status === 401) {
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
    throw new Error("Не авторизован");
  }

  const data = await res.json();

  if (!res.ok) {
    throw new Error((data as { error?: string }).error || "Ошибка запроса");
  }

  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
    }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    }),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    }),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  upload: <T>(path: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<T>(path, {
      method: "POST",
      body: formData,
    });
  },
};

export const superAdminApi = {
  get: <T>(path: string) => request<T>(path, {}, SUPER_ADMIN_API),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }, SUPER_ADMIN_API),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    }, SUPER_ADMIN_API),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }, SUPER_ADMIN_API),
};
