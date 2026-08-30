import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: { root: process.cwd() },
  output: "standalone",
  poweredByHeader: false,
  images: {
    unoptimized: true,
  },
};

export default nextConfig;
