// src/app/(app)/preferences/page.js — Delivery time, interests, and sources
"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { getUserProfile, updateDigestTime, updateInterests, getSources, createSource, deleteSource } from "@/lib/api";
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

const SOURCE_TYPES = ["blog", "youtube", "reddit", "twitter", "rss", "podcast", "other"];
const TYPE_ICONS = { blog: "✍", youtube: "▶", reddit: "⬆", twitter: "✦", rss: "◎", podcast: "🎙", other: "⊕" };

export default function PreferencesPage() {
  const { user } = useAuth();
  const [loading, setLoading] = useState(true);

  // Digest time
  const [digestTimeIst, setDigestTimeIst] = useState("09:00");
  const [savingTime, setSavingTime] = useState(false);
  const [timeMsg, setTimeMsg] = useState(null);

  // Interests
  const [interests, setInterests] = useState("");
  const [savingInterests, setSavingInterests] = useState(false);
  const [interestsMsg, setInterestsMsg] = useState(null);

  // Sources
  const [sources, setSources] = useState([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", type: "blog", url: "" });
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);

  const fetchProfile = useCallback(async () => {
    if (!user?.email) return;
    try {
      const data = await getUserProfile(user.email);
      setDigestTimeIst(utcToIst(data.digest_time ?? "09:00:00"));
      setInterests(data.interests_md ?? "");
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [user]);

  const fetchSources = useCallback(async () => {
    if (!user?.email) return;
    setSourcesLoading(true);
    try {
      const data = await getSources(user.email);
      setSources(data);
    } catch (e) {
      console.error(e);
    } finally {
      setSourcesLoading(false);
    }
  }, [user]);

  useEffect(() => { fetchProfile(); fetchSources(); }, [fetchProfile, fetchSources]);

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

  const handleDelete = async (sourceId) => {
    setDeletingId(sourceId);
    try {
      await deleteSource(user.email, sourceId);
      setSources(prev => prev.filter(s => s.id !== sourceId));
    } catch (e) {
      console.error(e);
    } finally { setDeletingId(null); }
  };

  const handleAdd = async (e) => {
    e.preventDefault();
    setAdding(true); setAddError(null);
    try {
      const created = await createSource(user.email, [form]);
      setSources(prev => {
        const existingIds = new Set(prev.map(s => s.id));
        return [...prev, ...created.filter(s => !existingIds.has(s.id))];
      });
      setForm({ name: "", type: "blog", url: "" });
      setShowForm(false);
    } catch (e) {
      setAddError(e.message);
    } finally { setAdding(false); }
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
          rows={2}
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

      {/* ── Sources ── */}
      <div className={`card ${styles.section}`}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Sources</h2>
            <p className={styles.sectionDesc}>Content sources included in your daily digest.</p>
          </div>
          <button className="btn-primary" onClick={() => setShowForm(v => !v)}>
            {showForm ? "✕ Cancel" : "+ Add Source"}
          </button>
        </div>

        {/* Add form */}
        {showForm && (
          <form className={styles.addForm} onSubmit={handleAdd}>
            <div className={styles.formGrid}>
              <div className={styles.field}>
                <label>Display Name</label>
                <input
                  required
                  placeholder="e.g. Fireship, Anthropic Blog"
                  value={form.name}
                  onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
                  className={styles.input}
                />
              </div>
              <div className={styles.field}>
                <label>Type</label>
                <select
                  value={form.type}
                  onChange={e => setForm(f => ({ ...f, type: e.target.value }))}
                  className={styles.input}
                >
                  {SOURCE_TYPES.map(t => (
                    <option key={t} value={t}>{TYPE_ICONS[t]} {t.charAt(0).toUpperCase() + t.slice(1)}</option>
                  ))}
                </select>
              </div>
              <div className={`${styles.field} ${styles.fullWidth}`}>
                <label>URL / Feed Link</label>
                <input
                  required
                  type="url"
                  placeholder="https://..."
                  value={form.url}
                  onChange={e => setForm(f => ({ ...f, url: e.target.value }))}
                  className={styles.input}
                />
              </div>
            </div>
            {addError && <p className={styles.error}>{addError}</p>}
            <div className={styles.formActions}>
              <button type="submit" className="btn-primary" disabled={adding}>
                {adding ? <><span className="spinner" /> Adding…</> : "Add Source"}
              </button>
            </div>
          </form>
        )}

        {/* Sources list */}
        {sourcesLoading ? (
          <div className={styles.list}>
            {[1, 2].map(i => <div key={i} className={styles.sourceSkeleton} />)}
          </div>
        ) : sources.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.emptyIcon}>⊕</p>
            <p>No sources yet</p>
            <p className={styles.emptyHint}>Add your first source using the button above.</p>
          </div>
        ) : (
          <div className={styles.list}>
            {sources.map(source => (
              <div key={source.id} className={styles.sourceCard}>
                <div className={styles.sourceIcon}>{TYPE_ICONS[source.type] ?? "⊕"}</div>
                <div className={styles.sourceInfo}>
                  <span className={styles.sourceName}>{source.name}</span>
                  <span className={styles.sourceUrl}>{source.url}</span>
                  <div className={styles.sourceMeta}>
                    <span className="tag tag-purple">{source.type}</span>
                    {source.last_fetched_at && (
                      <span className={styles.lastFetched}>
                        Last fetched: {new Date(source.last_fetched_at).toLocaleDateString("en-IN", {
                          day: "numeric", month: "short", year: "numeric"
                        })}
                      </span>
                    )}
                    {source.failure_count > 0 && (
                      <span className="tag tag-red">⚠ {source.failure_count} errors</span>
                    )}
                  </div>
                </div>
                <button
                  className={styles.deleteBtn}
                  onClick={() => handleDelete(source.id)}
                  disabled={deletingId === source.id}
                  title="Unsubscribe"
                >
                  {deletingId === source.id
                    ? <span className="spinner" style={{ width: 14, height: 14 }} />
                    : "✕"}
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
