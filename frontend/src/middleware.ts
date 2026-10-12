import { NextResponse, type NextRequest } from "next/server";

// 공개 URL 에 인증 없이 노출하지 않는다 (기획서 10장). 토큰 검증 자체는 백엔드가 한다.
export function middleware(request: NextRequest) {
  if (!request.cookies.has("aihub_token")) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!login|_next/static|_next/image|favicon.ico).*)"],
};
