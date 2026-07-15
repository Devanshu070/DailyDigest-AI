import { fileURLToPath } from "url";
import { dirname } from "path";

const __dirname = dirname(fileURLToPath(import.meta.url));

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Silence the multiple-lockfile workspace root warning.
  turbopack: {
    root: __dirname,
  },
  // Allow local network devices (e.g. phone on same WiFi) to access the dev server.
  allowedDevOrigins: ["192.168.1.7"],
  // Proxy all /api requests to the local FastAPI server in development.
  // In production, NEXT_PUBLIC_API_URL should point to the Render URL.
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;

