/** @type {import('next').NextConfig} */
const nextConfig = {
  // Product thumbnails are placeholder tiles from placehold.co (ponytail: swap for hosted brand
  // assets later). Allow that one remote host so next/image (if used) and plain <img> are happy.
  images: { remotePatterns: [{ protocol: "https", hostname: "placehold.co" }] },
};

export default nextConfig;
