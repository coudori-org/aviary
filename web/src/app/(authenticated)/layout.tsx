import { AuthGuard } from "@/features/auth/components/auth-guard";
import { AppShell } from "@/features/layout/components/app-shell";

export default function AuthenticatedLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <AppShell>{children}</AppShell>
    </AuthGuard>
  );
}
