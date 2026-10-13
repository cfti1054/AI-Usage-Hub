import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // CSV 업로드(서버 액션) 허용 크기. 백엔드 한도(약 5MB)와 맞춘다
    serverActions: { bodySizeLimit: "6mb" },
  },
};

export default nextConfig;
