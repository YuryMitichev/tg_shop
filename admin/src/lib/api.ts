const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
const ADMIN_API = `${API_BASE}/api/admin`;
const SUPER_ADMIN_API = `${API_BASE}/api/super-admin`;
export const SHOP_API = `${API_BASE}/api/shop`;

export function photoUrl(photoId: number): string {
  return `${SHOP_API}/photo/${photoId}`;
}

export function channelImportMediaUrl(mediaId: number): string {
  return `${ADMIN_API}/channel-import/media/${mediaId}`;
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  base: string = ADMIN_API,
  timeoutMs: number = 30000,
): Promise<T> {
  const headers: Record<string, string> = {
    ...((options.headers as Record<string, string>) || {}),
  };

  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      ...options,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") {
      throw new Error("Превышено время ожидания сервера. Попробуйте файл поменьше.");
    }
    throw new Error("Сервер недоступен. Проверьте подключение и попробуйте позже.");
  } finally {
    clearTimeout(timer);
  }

  if (res.status === 401) {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Не авторизован");
  }

  const data = await res.json();

  if (!res.ok) {
    throw new Error(
      (data as { error?: string; detail?: string }).error ||
        (data as { detail?: string }).detail ||
        "Ошибка запроса"
    );
  }

  return data as T;
}

async function downloadFile(
  path: string,
  base: string = ADMIN_API,
): Promise<{ blob: Blob; filename: string }> {
  const headers: Record<string, string> = {};
  const res = await fetch(`${base}${path}`, {
    headers,
    credentials: "include",
  });

  if (res.status === 401) {
    if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
      window.location.href = "/login";
    }
    throw new Error("Не авторизован");
  }

  if (!res.ok) {
    throw new Error("Ошибка загрузки файла");
  }

  const disposition = res.headers.get("content-disposition") || "";
  const filenameMatch = disposition.match(/filename="?([^"]+)"?/);
  const filename = filenameMatch ? filenameMatch[1] : "download.txt";

  return { blob: await res.blob(), filename };
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown, timeoutMs?: number) =>
    request<T>(
      path,
      {
        method: "POST",
        body: body instanceof FormData ? body : body ? JSON.stringify(body) : undefined,
      },
      ADMIN_API,
      timeoutMs,
    ),
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
  download: (path: string) => downloadFile(path),
};

export const superAdminApi = {
  get: <T>(path: string) => request<T>(path, {}, SUPER_ADMIN_API),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    }, SUPER_ADMIN_API),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    }, SUPER_ADMIN_API),
  patch: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    }, SUPER_ADMIN_API),
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }, SUPER_ADMIN_API),
};
