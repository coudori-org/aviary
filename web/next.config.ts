import type { NextConfig } from "next";

const apiUrl = process.env.INTERNAL_API_URL || "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    // `fallback` fires only after both filesystem AND dynamic routes are
    // checked, so App Router route handlers in src/app/api/... take
    // precedence. Long-running endpoints (e.g. the workflow assistant)
    // live as dedicated handlers to bypass the undici proxy timeout.
    return {
      beforeFiles: [],
      afterFiles: [],
      fallback: [
        {
          source: "/api/:path*",
          destination: `${apiUrl}/api/:path*`,
        },
      ],
    };
  },
  webpack: (config) => {
    config.watchOptions = {
      poll: 1000,
      aggregateTimeout: 300,
    };
    return config;
  },
};

export default nextConfig;
