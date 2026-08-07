import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Playwright's default baseURL is 127.0.0.1, which Next's dev-origin check treats as
  // a different origin from localhost and blocks by default.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
