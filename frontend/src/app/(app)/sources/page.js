// src/app/(app)/sources/page.js — Manage Sources
"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { getSources, createSource, deleteSource } from "@/lib/api";
import styles from "./page.module.css";

const SOURCE_TYPES = ["blog", "youtube"];
const TYPE_LABELS = { blog: "Blog / Article", youtube: "YouTube" };
const TYPE_ICONS = { blog: "✍", youtube: "▶" };

export default function SourcesPage() {
  const { user } = useAuth();
  const [sources, setSources] = useState([]);
  const [sourcesLoading, setSourcesLoading] = useState(true);
  const [deletingId, setDeletingId] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ name: "", type: "blog", url: "" });
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState(null);

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

  useEffect(() => { fetchSources(); }, [fetchSources]);

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

  return (
    <div className="animate-fade-in">
      <header className={styles.header}>
        <h1 className={styles.title}>Sources</h1>
      </header>

      <div className={`card ${styles.section}`}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Manage Sources</h2>
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
                    <option key={t} value={t}>{TYPE_ICONS[t]} {TYPE_LABELS[t]}</option>
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
                  <span className={styles.sourceName}>{source.display_name}</span>
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
