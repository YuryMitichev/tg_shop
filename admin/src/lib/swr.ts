import { api, superAdminApi } from "./api";

export const fetcher = <T>(url: string): Promise<T> => api.get<T>(url);

export const superAdminFetcher = <T>(url: string): Promise<T> =>
  superAdminApi.get<T>(url);
