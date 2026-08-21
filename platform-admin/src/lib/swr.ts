import { superAdminApi } from "./api";

export const superAdminFetcher = <T>(url: string): Promise<T> =>
  superAdminApi.get<T>(url);

export { superAdminApi };
