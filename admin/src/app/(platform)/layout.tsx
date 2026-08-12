import { DashboardShell } from "@/components/layout/dashboard-shell";

export default function PlatformLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <DashboardShell requireSuperAdmin>{children}</DashboardShell>
  );
}
