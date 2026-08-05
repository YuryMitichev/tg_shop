import { api, superAdminApi } from "./api";

export const fetcher: (url: string) => Promise<any> = (url) => api.get(url);

export const superAdminFetcher: (url: string) => Promise<any> = (url) =>
  superAdminApi.get(url);
