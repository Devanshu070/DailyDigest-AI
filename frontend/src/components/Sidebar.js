// src/components/Sidebar.js — Navigation sidebar
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import styles from "./Sidebar.module.css";

const navItems = [
  { href: "/dashboard",   label: "Dashboard",   icon: "⬡" },
  { href: "/pipeline",    label: "Pipeline",    icon: "▶" },
  { href: "/sources",     label: "Sources",     icon: "⊕" },
  { href: "/articles",    label: "Articles",    icon: "◈" },
  { href: "/preferences", label: "Preferences", icon: "⚙" },
];

export default function Sidebar() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  return (
    <aside className={styles.sidebar}>
      {/* Logo */}
      <div className={styles.logo}>
        <span className={styles.logoIcon}>✦</span>
        <span className={styles.logoText}>DailyDigest</span>
      </div>

      {/* Nav */}
      <nav className={styles.nav}>
        {navItems.map(({ href, label, icon }) => (
          <Link
            key={href}
            href={href}
            className={`${styles.navItem} ${pathname === href ? styles.active : ""}`}
          >
            <span className={styles.navIcon}>{icon}</span>
            <span>{label}</span>
          </Link>
        ))}
      </nav>

      {/* User info */}
      <div className={styles.userSection}>
        {user?.photoURL && (
          <img src={user.photoURL} alt="avatar" className={styles.avatar} />
        )}
        <div className={styles.userInfo}>
          <span className={styles.userName}>{user?.displayName?.split(" ")[0]}</span>
          <span className={styles.userEmail}>{user?.email}</span>
        </div>
        <button className={styles.logoutBtn} onClick={logout} title="Sign out">
          ⎋
        </button>
      </div>
    </aside>
  );
}
