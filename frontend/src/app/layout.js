// src/app/layout.js — Root layout: fonts, auth provider, metadata
import "./globals.css";
import { AuthProvider } from "@/context/AuthContext";

export const metadata = {
  title: "DailyDigest AI",
  description: "Your personalized AI-powered daily briefing dashboard.",
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body suppressHydrationWarning>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
