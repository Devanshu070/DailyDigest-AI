// src/app/(app)/dashboard/page.js — Overview dashboard
"use client";

import { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { useAuth } from "@/context/AuthContext";
import { getPipelineStatus, updateDigestPause } from "@/lib/api";
import styles from "./page.module.css";

function utcToLocal(utcTime) {
  if (!utcTime) return "—";
  const [h, m] = utcTime.split(":").map(Number);
  const totalMins = h * 60 + m + 330; // IST offset
  const istMins = totalMins % 1440;
  const hh = String(Math.floor(istMins / 60)).padStart(2, "0");
  const mm = String(istMins % 60).padStart(2, "0");
  return `${hh}:${mm} IST`;
}

function minutesUntilNext(digestTimeUtc) {
  if (!digestTimeUtc) return null;
  const [h, m] = digestTimeUtc.split(":").map(Number);
  const now = new Date();
  const target = new Date();
  target.setUTCHours(h, m, 0, 0);
  if (target <= now) target.setUTCDate(target.getUTCDate() + 1);
  return Math.round((target - now) / 60000);
}

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

export default function DashboardPage() {
  const { user } = useAuth();
  const [status, setStatus]   = useState(null);
  const [loading, setLoading] = useState(true);
  const [savingPause, setSavingPause] = useState(false);
  const [tick, setTick]       = useState(0);

  const fetchStatus = useCallback(async () => {
    if (!user?.email) return;
    try {
      const data = await getPipelineStatus(user.email);
      setStatus(data);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { fetchStatus(); }, [fetchStatus]);

  // Tick every minute to refresh countdown
  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), 60000);
    return () => clearInterval(id);
  }, []);

  const handleTogglePause = async () => {
    if (!status || !user?.email) return;
    const nextPaused = !status.digest_paused;
    setSavingPause(true);
    try {
      const data = await updateDigestPause(user.email, nextPaused);
      setStatus(prev => ({ ...prev, digest_paused: data.digest_paused }));
    } catch (e) {
      console.error("Failed to update pause state:", e);
    } finally {
      setSavingPause(false);
    }
  };

  const minsLeft = status ? minutesUntilNext(status.digest_time) : null;
  const hoursLeft = minsLeft !== null ? Math.floor(minsLeft / 60) : null;
  const minsRem   = minsLeft !== null ? minsLeft % 60 : null;
  const pct = minsLeft !== null ? Math.max(0, Math.min(100, 100 - (minsLeft / 1440) * 100)) : 0;

  const totalSources   = status?.sources?.length ?? 0;
  const healthySources = status?.sources?.filter(s => s.is_active && !s.failure_count).length ?? 0;
  const warningSources = status?.sources?.filter(s => s.failure_count > 0).length ?? 0;
  const firstName      = user?.displayName?.split(" ")[0] ?? "there";

  return (
    <div className="animate-fade-in">
      {/* ── Greeting ── */}
      <header className={styles.header}>
        <div>
          <h1 className={styles.title}>{greeting()}, {firstName} 👋</h1>
          <p className={styles.subtitle}>
            {new Date().toLocaleDateString("en-IN", { weekday: "long", day: "numeric", month: "long", year: "numeric" })}
          </p>
        </div>
        <div className={styles.headerActions}>
          {status && (
            <button
              className="btn-ghost"
              onClick={handleTogglePause}
              disabled={savingPause}
              title={status.digest_paused ? "Resume scheduled digests" : "Pause scheduled digests"}
            >
              {savingPause ? <><span className="spinner" /> Saving…</> : status.digest_paused ? "▶ Resume Digest" : "⏸ Pause Digest"}
            </button>
          )}
          <Link href="/pipeline" className="btn-primary" id="run-pipeline-link">
            ▶ Run Pipeline
          </Link>
        </div>
      </header>

      {/* ── Stats grid ── */}
      {loading ? (
        <div className={styles.statsGrid}>
          {[1, 2, 3, 4].map(i => <div key={i} className={styles.skeleton} />)}
        </div>
      ) : (
        <div className={styles.statsGrid}>
          <StatCard
            icon="📬"
            label="Last Digest"
            value={status?.last_digest_at
              ? new Date(status.last_digest_at).toLocaleString("en-IN", {
                  timeZone: "Asia/Kolkata", day: "numeric", month: "short",
                  hour: "2-digit", minute: "2-digit", hour12: false,
                })
              : "Never sent"}
            sub={status?.last_digest_at ? "Sent successfully" : "Run the pipeline to send one"}
          />
          <StatCard icon="📡" label="Sources" value={totalSources} sub={`${healthySources} healthy`} />
          <StatCard icon="✓"  label="Healthy" value={healthySources} sub="Active with no failures" accent="green" />
          <StatCard icon="⚠"  label="Warnings" value={warningSources} sub="Sources with failures" accent={warningSources > 0 ? "yellow" : ""} />
        </div>
      )}

      {/* ── Next digest countdown ── */}
      {!loading && status && (
        <div className={`card ${styles.countdownCard}`}>
          <div className={styles.countdownTop}>
            <div>
              <p className={styles.countdownLabel}>{status.digest_paused ? "Scheduled Delivery" : "Next Digest In"}</p>
              <p className={styles.countdownValue}>
                {status.digest_paused ? "Paused" : `${hoursLeft}h ${minsRem}m`}
              </p>
            </div>
            <div className={styles.scheduleInfo}>
              <span className={styles.scheduleLabel}>Scheduled at</span>
              <span className={styles.scheduleTime}>{utcToLocal(status.digest_time)}</span>
              <div className={styles.scheduleLinks}>
                <button
                  className={styles.inlinePauseBtn}
                  onClick={handleTogglePause}
                  disabled={savingPause}
                >
                  {savingPause ? "Saving…" : status.digest_paused ? "Resume delivery ›" : "Pause delivery ›"}
                </button>
                <span>•</span>
                <Link href="/preferences" className={styles.changeLink}>
                  Change schedule ›
                </Link>
              </div>
            </div>
          </div>
          <div className={styles.progressTrack}>
            <div className={styles.progressFill} style={{ width: `${pct}%` }} />
          </div>
          <p className={styles.progressCaption}>
            {status.digest_paused
              ? "Scheduled emails are paused. Manual runs remain available."
              : "Progress through current 24-hour window"}
          </p>
        </div>
      )}

      {/* ── Empty state ── */}
      {!loading && totalSources === 0 && (
        <div className={styles.emptyState}>
          <div className={styles.emptyIcon}>📡</div>
          <h2 className={styles.emptyTitle}>No sources yet</h2>
          <p className={styles.emptyDesc}>Add RSS feeds or URLs to start receiving daily digests.</p>
          <Link href="/sources" className="btn-primary" style={{ marginTop: 20 }}>
            Add your first source ›
          </Link>
        </div>
      )}
    </div>
  );
}

function StatCard({ icon, label, value, sub, accent }) {
  const accentClass = accent === "green" ? styles.accentGreen
                    : accent === "yellow" ? styles.accentYellow
                    : "";
  return (
    <div className={`card ${styles.statCard} ${accentClass}`}>
      <span className={styles.statIcon}>{icon}</span>
      <span className={styles.statValue}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
      {sub && <span className={styles.statSub}>{sub}</span>}
    </div>
  );
}
