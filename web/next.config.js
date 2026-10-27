/** @type {import('next').NextConfig} */
const nextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          {
            // CSP, Next.js-compatible variant: the shell carries inline
            // <script> tags (8 + self.__next_f payloads), so script-src
            // without 'unsafe-inline' would break the app. The policy
            // still buys: no framing, no plugins, connect limited to
            // our own API hosts, no foreign images/fonts/scripts.
            // connect-src lists BOTH api hosts: the live workers.dev
            // base and api.omdanny.site (package C, once its custom
            // domain exists) so that switch needs no headers change.
            key: "Content-Security-Policy",
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline'",
              "style-src 'self' 'unsafe-inline'",
              "img-src 'self' data:",
              "font-src 'self'",
              "connect-src 'self' https://radar-api.rwnliwan.workers.dev https://api.omdanny.site",
              "frame-ancestors 'none'",
              "object-src 'none'",
              "base-uri 'self'",
            ].join("; "),
          },
          // Host-scoped only: no includeSubDomains (other omdanny.site
          // subdomains untouched), no preload on first pass.
          { key: "Strict-Transport-Security", value: "max-age=31536000" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=(), usb=()",
          },
        ],
      },
    ];
  },
};

module.exports = nextConfig;
