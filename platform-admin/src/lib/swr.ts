import { superAdminApi } from "./api";

export const superAdminFetcher: (url: string) => Promise<any> = (url) =>
  superAdminApi.get(url);

export { superAdminApi };
