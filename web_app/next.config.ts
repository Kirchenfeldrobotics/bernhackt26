import type { NextConfig } from "next";

/**
 * Where the API actually runs. Override with API_ORIGIN to point a deployment
 * at a different backend; this is the only place the host is written down.
 *
 * The default is the backend on this machine rather than its public hostname:
 * the hop is server to server anyway, so there is no reason to leave the box,
 * and it keeps working if the public name or its certificate ever lapses.
 */
const API_ORIGIN = (process.env.API_ORIGIN ?? "http://127.0.0.1:8232").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  /**
   * Everything the browser sends goes to this app's own origin under /backend,
   * and is forwarded from here.
   *
   * Naming the API host in the bundle instead makes every request cross-origin,
   * and the API's CORS allowlist has to name this app's origin for the browser
   * to send it at all -- when it does not, every call fails before it leaves.
   * Forwarding server to server sidesteps that: the browser only ever talks to
   * its own origin, and CORS does not apply to the hop from here to the API.
   *
   * The prefix is "/backend" and not the obvious "/api" because the nginx vhost
   * in front of this app claims "location /api/" for itself, so a rewrite here
   * would never see those requests. Anything outside /api reaches us intact.
   */
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${API_ORIGIN}/:path*` }];
  },
};

export default nextConfig;
