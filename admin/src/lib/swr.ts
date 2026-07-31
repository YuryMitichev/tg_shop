import { api } from "./api";

export const fetcher: (url: string) => Promise<any> = (url) => api.get(url);
