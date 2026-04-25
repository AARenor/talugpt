/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Static export — produces an `out/` directory of pure HTML/CSS/JS
  // that any static host (Netlify, Cloudflare Pages, GitHub Pages, S3) can serve.
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
};

module.exports = nextConfig;
