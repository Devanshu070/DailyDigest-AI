// src/app/(app)/pipeline/page.js — Manual pipeline trigger with inline email preview
"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useAuth } from "@/context/AuthContext";
import { runPipeline, getRunState } from "@/lib/api";
import styles from "./page.module.css";

export default function PipelinePage() {
  const { user } = useAuth();
  const [runState, setRunState]       = useState(null);
  const [emailPreview, setEmailPreview] = useState(null); // { html, subject }
  const pollRef = useRef(null);

  const deliveryLabel = runState?.stage === "sending_email" ? "Sending Email" : "Generating Digest";
  const stageSteps = [
    { key: "fetching_articles", label: "Fetching Articles" },
    { key: "cleaning",          label: "Cleaning & Dedup" },
    { key: "summarizing",       label: "AI Summarizing" },
    { key: "assembling_digest", label: "Building Digest" },
    { key: "delivery",          label: deliveryLabel },
  ];

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      try {
        const state = await getRunState();
        setRunState(state);
        if (state.email_html) {
          setEmailPreview(prev => prev ?? { html: state.email_html, subject: state.email_subject });
        }
        if (!state.is_running) {
          clearInterval(pollRef.current);
          pollRef.current = null;
        }
      } catch (e) {
        console.error(e);
      }
    }, 2000);
  }, []);

  useEffect(() => () => clearInterval(pollRef.current), []);

  const handleRun = async () => {
    setEmailPreview(null);
    setRunState({ stage: "fetching_articles", label: "Starting…", progress_pct: 5, is_running: true });
    try {
      await runPipeline(user.email);
      startPolling();
    } catch (e) {
      setRunState({ stage: "error", label: e.message, progress_pct: 100, is_running: false });
    }
  };

  const isDone    = runState?.stage === "done";
  const isError   = runState?.stage === "error";
  const isRunning = runState?.is_running;
  const hasRun    = runState && runState.stage !== "idle";

  return (
    <div className="animate-fade-in">
      <header className={styles.header}>
        <h1 className={styles.title}>Run Pipeline</h1>
        <p className={styles.subtitle}>Manually trigger a digest run — bypasses daily schedule</p>
      </header>

      {/* ── Trigger card ── */}
      <div className={`card ${styles.triggerCard}`}>
        <div className={styles.triggerInfo}>
          <div className={styles.triggerIconWrap}>▶</div>
          <div>
            <h2 className={styles.triggerTitle}>Immediate Run</h2>
            <p className={styles.triggerDesc}>
              Fetches unread articles from your sources (reusing cached articles), AI-summarizes them, and assembles your digest on demand (emails are sent during scheduled runs).
            </p>
          </div>
        </div>
        <button className="btn-primary" onClick={handleRun} disabled={isRunning} id="run-pipeline-btn">
          {isRunning ? <><span className="spinner" /> Running…</> : "▶ Run Now"}
        </button>
      </div>

      {/* ── Live progress ── */}
      {hasRun && (
        <div className={`card ${styles.progressCard}`}>
          <span className={`${styles.progressTitle} ${isDone ? styles.titleDone : isError ? styles.titleError : styles.titleRunning}`}>
            {isDone ? "✓ Pipeline Complete" : isError ? "✗ Pipeline Failed" : "⏳ Pipeline Running"}
          </span>

          {/* Stage stepper */}
          <div className={styles.stageRow}>
            {stageSteps.map((step, i) => {
              const isDeliveryStage = (stage) => stage === "generating_digest" || stage === "sending_email" || stage === "preparing_preview";
              const currentIdx = stageSteps.findIndex(
                s => s.key === runState.stage || (s.key === "delivery" && isDeliveryStage(runState.stage))
              );
              const done    = currentIdx > i || isDone;
              const current = runState.stage === step.key || (step.key === "delivery" && isDeliveryStage(runState.stage));
              return (
                <div key={step.key} className={styles.stageStep}>
                  <div className={`${styles.stepDot}${done ? " " + styles.dotDone : ""}${current ? " " + styles.dotActive : ""}${isError && current ? " " + styles.dotError : ""}`}>
                    {done ? "✓" : i + 1}
                  </div>
                  <span className={`${styles.stepLabel}${current ? " " + styles.labelActive : ""}`}>{step.label}</span>
                  {i < stageSteps.length - 1 && (
                    <div className={`${styles.stepLine}${done ? " " + styles.lineDone : ""}`} />
                  )}
                </div>
              );
            })}
          </div>

          <div className={styles.progressTrack}>
            <div
              className={`${styles.progressFill}${isError ? " " + styles.progressError : ""}`}
              style={{ width: `${runState.progress_pct}%` }}
            />
          </div>
          <p className={styles.runLabel}>{runState.label}</p>
        </div>
      )}

      {/* ── Inline email preview ── */}
      {emailPreview && (
        <div className={styles.emailSection}>
          <div className={styles.emailSectionHeader}>
            <div>
              <p className={styles.emailMeta}>📧 Generated Email Preview</p>
              <h2 className={styles.emailSubject}>{emailPreview.subject}</h2>
            </div>
            <button className="btn-ghost" onClick={() => setEmailPreview(null)}>✕ Dismiss</button>
          </div>
          <div
            className={styles.emailBody}
            dangerouslySetInnerHTML={{ __html: emailPreview.html }}
          />
        </div>
      )}

      {/* No email note */}
      {isDone && !emailPreview && (
        <p className={styles.noEmailNote}>No email was generated in this run.</p>
      )}
    </div>
  );
}
