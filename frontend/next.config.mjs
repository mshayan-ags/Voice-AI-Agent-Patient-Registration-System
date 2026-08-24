/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: every page here is a client component fetching from the
  // FastAPI backend at request time, so there's nothing that needs Next's
  // server runtime. This lets the whole dashboard deploy to plain static
  // hosting (Firebase Hosting's free Spark tier) instead of a paid Cloud
  // Run / serverless setup that dynamic SSR routes would require.
  output: "export",
};

export default nextConfig;
