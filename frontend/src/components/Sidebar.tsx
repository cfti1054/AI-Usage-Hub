import Link from "next/link";
import { logoutAction } from "@/app/actions";

const NAV = [
  { href: "/", label: "대시보드" },
  { href: "/costs", label: "비용 분석" },
  { href: "/settings", label: "설정" },
];

export function Sidebar() {
  return (
    <aside className="flex w-full shrink-0 flex-row items-center gap-4 border-b border-slate-200 bg-white px-4 py-3 md:h-screen md:w-52 md:flex-col md:items-stretch md:border-r md:border-b-0 md:py-6">
      <Link href="/" className="text-lg font-bold">
        AI Hub
      </Link>
      <nav className="flex flex-1 flex-row gap-1 md:flex-col">
        {NAV.map((item) => (
          <Link key={item.href} href={item.href} className="rounded px-2 py-1.5 text-sm hover:bg-slate-100">
            {item.label}
          </Link>
        ))}
      </nav>
      <form action={logoutAction}>
        <button type="submit" className="text-xs text-slate-500 hover:text-slate-900">
          로그아웃
        </button>
      </form>
    </aside>
  );
}
