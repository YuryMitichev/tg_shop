import type { Metadata } from "next";
import "./globals.css";
import { Toaster } from "@/components/ui/sonner";
import { SWRProvider } from "@/components/providers/swr-provider";

export const metadata: Metadata = {
  title: "Админ-панель",
  description: "Панель управления магазином",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-muted/30">
        <SWRProvider>
          {children}
          <Toaster position="top-right" richColors />
        </SWRProvider>
      </body>
    </html>
  );
}
