// src/app/(app)/preferences/page.js — Delivery time, interests, and sources
"use client";

import { useState, useEffect, useCallback } from "react";
import { deleteUser, GoogleAuthProvider, reauthenticateWithPopup } from "firebase/auth";
import { useAuth } from "@/context/AuthContext";
import { auth } from "@/lib/firebase";
import { getUserProfile, updateDigestTime, updateInterests, updateDigestPause, deleteAccount } from "@/lib/api";
import styles from "./page.module.css";

// IST = UTC + 5h30m (330 minutes)
function utcToIst(utcTimeStr) {
  if (!utcTimeStr) return "09:00";
  const [h, m] = utcTimeStr.split(":").map(Number);
  const totalMins = h * 60 + m + 330;
  const istMins = totalMins % 1440;
  return `${String(Math.floor(istMins / 60)).padStart(2, "0")}:${String(istMins % 60).padStart(2, "0")}`;
}

function istToUtc(istTimeStr) {
  const [h, m] = istTimeStr.split(":").map(Number);
  const totalMins = h * 60 + m - 330;
  const utcMins = ((totalMins % 1440) + 1440) % 1440;
  return `${String(Math.floor(utcMins / 60)).padStart(2, "0")}:${String(utcMins % 60).padStart(2, "0")}:00`;
}

export default function PreferencesPage() {
  const { user, logout } = useAuth();
  const [loading, setLoading] = useState(true);

  // Digest time
  const [digestTimeIst, setDigestTimeIst] = useState("09:00");
  const [savingTime, setSavingTime] = useState(false);
  const [timeMsg, setTimeMsg] = useState(null);
  const [digestPaused, setDigestPaused] = useState(false);
  const [savingPause, setSavingPause] = useState(false);
  const [pauseMsg, setPauseMsg] = useState(null);
  const [deletingAccount, setDeletingAccount] = useState(false);
  const [accountMsg, setAccountMsg] = useState(null);

  // Interests
  const [interests, setInterests] = useState("");
  const [savingInterests, setSavingInterests] = useState(false);
  const [interestsMsg, setInterestsMsg] = useState(null);

  const fetchProfile = useCallback(async () => {
    if (!user?.email) return;
    try {
      const data = await getUserProfile(user.email);
      setDigestTimeIst(utcToIst(data.digest_time ?? "09:00:00"));
      setInterests(data.interests_md ?? "");
      setDigestPaused(data.digest_paused ?? false);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => { fetchProfile(); }, [fetchProfile]);

  const handleSaveTime = async () => {
    setSavingTime(true); setTimeMsg(null);
    try {
      await updateDigestTime(user.email, istToUtc(digestTimeIst));
      setTimeMsg({ type: "success", text: `Saved! Digest will arrive at ${digestTimeIst} IST.` });
    } catch (e) {
      setTimeMsg({ type: "error", text: e.message });
    } finally { setSavingTime(false); }
  };

  const handleSaveInterests = async () => {
    setSavingInterests(true); setInterestsMsg(null);
    try {
      await updateInterests(user.email, interests);
      setInterestsMsg({ type: "success", text: "Interests saved!" });
    } catch (e) {
      setInterestsMsg({ type: "error", text: e.message });
    } finally { setSavingInterests(false); }
  };

  const handleTogglePause = async () => {
    const nextPaused = !digestPaused;
    setSavingPause(true); setPauseMsg(null);
    try {
      const data = await updateDigestPause(user.email, nextPaused);
      setDigestPaused(data.digest_paused);
      setPauseMsg({
        type: "success",
        text: data.digest_paused
          ? "Scheduled digest emails are paused."
          : "Scheduled digest emails are active again.",
      });
    } catch (e) {
      setPauseMsg({ type: "error", text: e.message });
    } finally { setSavingPause(false); }
  };

  const handleDeleteAccount = async () => {
    if (!window.confirm("Delete your account and all of your subscriptions? This cannot be undone.")) {
      return;
    }

    const currentUser = auth.currentUser;
    if (!currentUser) return;

    setDeletingAccount(true); setAccountMsg(null);
    try {
      // Firebase requires recent authentication for account deletion.
      await reauthenticateWithPopup(currentUser, new GoogleAuthProvider());
      await deleteAccount();
      await deleteUser(currentUser);
      await logout();
      window.location.assign("/");
    } catch (e) {
      setAccountMsg({ type: "error", text: e.message });
      setDeletingAccount(false);
    }
  };

  if (loading) {
    return (
      <div className="animate-fade-in">
        <div className={styles.skeletonHeader} />
        <div className={styles.skeleton} />
        <div className={styles.skeleton} />
        <div className={styles.skeleton} style={{ height: 200 }} />
      </div>
    );
  }

  return (
    <div className="animate-fade-in">
      <header className={styles.header}>
        <h1 className={styles.title}>Preferences</h1>
      </header>

      {/* ── Delivery Time ── */}
      <div className={`card ${styles.section}`}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Daily Delivery Time</h2>
        </div>
        <div className={styles.formRow}>
          <div className={styles.timeWrapper}>
            <input
              type="time"
              value={digestTimeIst}
              onChange={e => setDigestTimeIst(e.target.value)}
              className={styles.timeInput}
            />
            <span className={styles.timeBadge}>IST</span>
          </div>
          <div className={styles.utcHint}>= {istToUtc(digestTimeIst).slice(0, 5)} UTC</div>
          <button className="btn-primary" onClick={handleSaveTime} disabled={savingTime}>
            {savingTime ? <><span className="spinner" /> Saving…</> : "Save"}
          </button>
        </div>
        {timeMsg && (
          <p className={`${styles.msg} ${timeMsg.type === "error" ? styles.error : styles.success}`}>
            {timeMsg.text}
          </p>
        )}
        <div className={styles.pauseRow}>
          <div>
            <strong>{digestPaused ? "Scheduled delivery is paused" : "Scheduled delivery is active"}</strong>
            <p className={styles.sectionDesc}>
              Manual pipeline runs remain available while scheduled delivery is paused.
            </p>
          </div>
          <button className="btn-primary" onClick={handleTogglePause} disabled={savingPause}>
            {savingPause ? <><span className="spinner" /> Saving…</> : digestPaused ? "Resume" : "Pause"}
          </button>
        </div>
        {pauseMsg && (
          <p className={`${styles.msg} ${pauseMsg.type === "error" ? styles.error : styles.success}`}>
            {pauseMsg.text}
          </p>
        )}
      </div>

      {/* ── Interests ── */}
      <div className={`card ${styles.section}`}>
        <div className={styles.sectionHeader}>
          <h2 className={styles.sectionTitle}>Interests</h2>
          <p className={styles.sectionDesc}>
            Tell the AI what topics to include or skip in your digest.
          </p>
        </div>
        <textarea
          value={interests}
          onChange={e => setInterests(e.target.value)}
          className={styles.textarea}
          rows={5}
          placeholder={"# My Interests\n\nI care deeply about...\n\n## Skip\n- Crypto / NFT news\n- Celebrity gossip"}
        />
        <div className={styles.formRow}>
          <span className={styles.charCount}>{interests.length} characters</span>
          <button className="btn-primary" onClick={handleSaveInterests} disabled={savingInterests}>
            {savingInterests ? <><span className="spinner" /> Saving…</> : "Save Interests"}
          </button>
        </div>
        {interestsMsg && (
          <p className={`${styles.msg} ${interestsMsg.type === "error" ? styles.error : styles.success}`}>
            {interestsMsg.text}
          </p>
        )}
      </div>

      {/* ── Account ── */}
      <div className={`card ${styles.section} ${styles.dangerSection}`}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Delete Account</h2>
            <p className={styles.sectionDesc}>
              Permanently remove your profile and subscriptions. Shared source and article data is preserved.
            </p>
          </div>
          <button className={styles.dangerButton} onClick={handleDeleteAccount} disabled={deletingAccount}>
            {deletingAccount ? <><span className="spinner" /> Deleting…</> : "Delete account"}
          </button>
        </div>
        {accountMsg && (
          <p className={`${styles.msg} ${styles.error}`}>{accountMsg.text}</p>
        )}
      </div>
    </div>
  );
}
