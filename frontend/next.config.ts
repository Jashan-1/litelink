import type { NextConfig } from "next";

const apiOrigin = process.env.LITELINK_API_ORIGIN ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      { source: "/api/:path*", destination: `${apiOrigin}/api/:path*` },
      { source: "/login", destination: `${apiOrigin}/login` },
      { source: "/logout", destination: `${apiOrigin}/logout` },
      { source: "/auth/:path*", destination: `${apiOrigin}/auth/:path*` },
      { source: "/go/:slug", destination: `${apiOrigin}/:slug` }
    ];
  }
};

export default nextConfig;
