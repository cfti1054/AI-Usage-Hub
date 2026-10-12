import { loginAction } from "@/app/actions";
import { ActionForm, SubmitButton } from "@/components/ActionForm";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <ActionForm action={loginAction} className="w-full max-w-sm space-y-3 rounded-lg border border-slate-200 bg-white p-6">
        <h1 className="text-lg font-semibold">AI Hub 로그인</h1>
        <input name="email" type="email" required placeholder="이메일" autoComplete="username" className="input" />
        <input name="password" type="password" required placeholder="비밀번호" autoComplete="current-password" className="input" />
        <SubmitButton>로그인</SubmitButton>
      </ActionForm>
    </main>
  );
}
