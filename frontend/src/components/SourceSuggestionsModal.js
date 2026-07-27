// frontend/src/components/SourceSuggestionsModal.js
"use client";

import { useState, useEffect, useCallback } from "react";
import { getSourceSuggestions } from "@/lib/api";
import styles from "./SourceSuggestionsModal.module.css";

const TYPE_ICONS = { blog: "✍", youtube: "▶" };

export default function SourceSuggestionsModal({
  userEmail,
  isOpen,
  onClose,
  onAddSelected,
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [suggestions, setSuggestions] = useState([]);
  const [cached, setCached] = useState(false);
  const [selectedUrls, setSelectedUrls] = useState(new Set());
  const [adding, setAdding] = useState(false);

  const fetchSuggestions = useCallback(async (refresh = false) => {
    if (!userEmail) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getSourceSuggestions(userEmail, refresh);
      setSuggestions(res.suggestions || []);
      setCached(!!res.cached);

      // Pre-select all returned suggestions by default
      const initialSelected = new Set((res.suggestions || []).map(s => s.url));
      setSelectedUrls(initialSelected);
    } catch (e) {
      setError(e.message || "Failed to load suggestions.");
    } finally {
      setLoading(false);
    }
  }, [userEmail]);

  useEffect(() => {
    if (isOpen) {
      fetchSuggestions(false);
    }
  }, [isOpen, fetchSuggestions]);

  if (!isOpen) return null;

  const toggleSelect = (url) => {
    setSelectedUrls((prev) => {
      const next = new Set(prev);
      if (next.has(url)) {
        next.delete(url);
      } else {
        next.add(url);
      }
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedUrls.size === suggestions.length) {
      setSelectedUrls(new Set());
    } else {
      setSelectedUrls(new Set(suggestions.map((s) => s.url)));
    }
  };

  const handleAdd = async () => {
    const selected = suggestions.filter((s) => selectedUrls.has(s.url));
    if (selected.length === 0) return;
    setAdding(true);
    try {
      await onAddSelected(selected);
      onClose();
    } catch (e) {
      setError(e.message || "Failed to add selected sources.");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerContent}>
            <h2 className={styles.title}>Suggested Sources</h2>
            <p className={styles.subtitle}>
              Discover RSS feeds & YouTube channels matching your interests.
            </p>
          </div>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {/* Body */}
        <div className={styles.body}>
          {loading ? (
            <div className={styles.loadingState}>
              <div className="spinner" style={{ width: 24, height: 24 }} />
              <p>Analyzing interests & searching for relevant sources…</p>
            </div>
          ) : error ? (
            <div className={styles.errorState}>
              <p>⚠️ {error}</p>
              <button
                className="btn-ghost"
                onClick={() => fetchSuggestions(true)}
              >
                Try again
              </button>
            </div>
          ) : suggestions.length === 0 ? (
            <div className={styles.emptyState}>
              <p style={{ fontSize: 24 }}>🔍</p>
              <p>No new source suggestions found right now.</p>
              <p style={{ fontSize: 12, color: "var(--text-muted)" }}>
                Make sure your interest profile is filled out in Preferences.
              </p>
            </div>
          ) : (
            <>
              {cached && (
                <div className={styles.metaBanner}>
                  <span>✦ Served from cache</span>
                  <button
                    className={styles.refreshLink}
                    onClick={() => fetchSuggestions(true)}
                  >
                    Refresh suggestions
                  </button>
                </div>
              )}

              {suggestions.map((item) => {
                const isChecked = selectedUrls.has(item.url);
                return (
                  <div
                    key={item.url}
                    className={`${styles.card} ${
                      isChecked ? styles.cardSelected : ""
                    }`}
                    onClick={() => toggleSelect(item.url)}
                  >
                    <div className={styles.checkboxContainer}>
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => {}} // handled by parent onClick
                        className={styles.checkbox}
                      />
                    </div>
                    <div className={styles.cardContent}>
                      <div className={styles.cardHeader}>
                        <span className={styles.cardName}>{item.name}</span>
                        <span className="tag tag-purple">
                          {TYPE_ICONS[item.source_type]} {item.source_type}
                        </span>
                      </div>
                      <span className={styles.cardUrl}>{item.url}</span>
                      <p className={styles.cardReason}>
                        {item.recommendation_reason}
                      </p>
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>

        {/* Footer */}
        {!loading && suggestions.length > 0 && (
          <div className={styles.footer}>
            <button className={styles.selectAllBtn} onClick={toggleSelectAll}>
              {selectedUrls.size === suggestions.length
                ? "Deselect all"
                : "Select all"}
            </button>
            <div className={styles.footerActions}>
              <button className="btn-ghost" onClick={onClose}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleAdd}
                disabled={selectedUrls.size === 0 || adding}
              >
                {adding ? (
                  <>
                    <span className="spinner" /> Adding…
                  </>
                ) : (
                  `Add Selected (${selectedUrls.size})`
                )}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
