import type { NextConfig } from "next";

/**
 * Where the API actually runs. Override with API_ORIGIN to point a deployment
 * at a different backend; this is the only place the host is written down.
 *
 * The default is the backend on this machine rather than its public hostname:
 * the hop is server to server anyway, so there is no reason to leave the box,
 * and it keeps working if the public name or its certificate ever lapses.
 */
const API_ORIGIN = process.env.API_ORIGIN ?? "http://127.0.0.1:8232";

const nextConfig: NextConfig = {
  /**
   * Everything the browser sends goes to this app's own origin under /backend,
   * and is forwarded from here.
   *
   * The API's CORS allowlist is localhost:3000 and nothing else, so a browser
   * on any other address -- every real deployment -- has its requests refused
   * before they are made. Forwarding server to server sidesteps that entirely:
   * the browser only ever talks to its own origin, and CORS does not apply to
   * the hop from here to the API. It also means the app behaves the same
   * wherever it is served from.
   *
   * The prefix is "/backend" and not the obvious "/api" because the nginx vhost
   * in front of this app claims "location /api/" for itself and proxies it to a
   * port nothing listens on. A rewrite here never sees those requests, so they
   * died as 502s before this app was involved. Anything outside /api reaches us
   * intact.
   */
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${API_ORIGIN}/:path*` }];
  },
};

export default nextConfig;
