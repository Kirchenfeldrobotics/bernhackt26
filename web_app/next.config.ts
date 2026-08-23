import type { NextConfig } from "next";

/**
 * Where the API actually runs. Override with API_ORIGIN to point a deployment
 * at a different backend; this is the only place the host is written down.
 */
const API_ORIGIN =
  process.env.API_ORIGIN ?? "https://bernhackt26.kirchenfeldrobotics.ch";

const nextConfig: NextConfig = {
  /**
   * Everything the browser sends goes to this app's own origin under /api, and
   * is forwarded from here.
   *
   * The API's CORS allowlist is localhost:3000 and nothing else, so a browser
   * on any other address -- every real deployment -- has its requests refused
   * before they are made. Forwarding server to server sidesteps that entirely:
   * the browser only ever talks to its own origin, and CORS does not apply to
   * the hop from here to the API. It also means the app behaves the same
   * wherever it is served from.
   */
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_ORIGIN}/:path*` }];
  },
};

export default nextConfig;
