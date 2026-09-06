// frontend/src/components/SourceSuggestionsModal.js
"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { createPortal } from "react-dom";
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
  const [findingMore, setFindingMore] = useState(false);
  const [moreMessage, setMoreMessage] = useState("");
  const requestId = useRef(0);

  const fetchSuggestions = useCallback(async (refresh = false) => {
    if (!userEmail) return;
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    setFindingMore(false);
    setMoreMessage("");
    try {
      const res = await getSourceSuggestions(userEmail, refresh);
      if (id !== requestId.current) return;
      setSuggestions(res.suggestions || []);
      setCached(!!res.cached);

      // Pre-select all returned suggestions by default
      const initialSelected = new Set((res.suggestions || []).map(s => s.url));
      setSelectedUrls(initialSelected);
    } catch (e) {
      if (id !== requestId.current) return;
      setError(e.message || "Failed to load suggestions.");
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [userEmail]);

  useEffect(() => {
    if (isOpen) {
      // Start after the effect, and cancel stale responses on close/account change.
      const timer = setTimeout(() => {
        fetchSuggestions(false);
      }, 0);
      return () => {
        clearTimeout(timer);
        requestId.current += 1;
      };
    }
  }, [isOpen, fetchSuggestions]);

  const findMore = async () => {
    if (findingMore || adding || !userEmail) return;
    const id = ++requestId.current;
    setFindingMore(true);
    setMoreMessage("");
    try {
      const seen = new Set(suggestions.map((item) => item.url));
      const res = await getSourceSuggestions(userEmail, true, [...seen]);
      if (id !== requestId.current) return;
      const newItems = (res.suggestions || []).filter((item) => {
        if (seen.has(item.url)) return false;
        seen.add(item.url);
        return true;
      });
      setSuggestions((prev) => [...prev, ...newItems]);
      setSelectedUrls((prev) => new Set([...prev, ...newItems.map((item) => item.url)]));
      setCached(false);
      setMoreMessage(newItems.length ? `Added ${newItems.length} new suggestions.` : "No new sources found right now.");
    } catch (e) {
      if (id === requestId.current) setMoreMessage(e.message || "Could not find more sources. Please try again.");
    } finally {
      if (id === requestId.current) setFindingMore(false);
    }
  };

  if (!isOpen || typeof document === "undefined") return null;

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

  // Escape the page's animated transform so fixed positioning uses the viewport.
  return createPortal(
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
              <button
                className="btn-ghost"
                onClick={() => fetchSuggestions(true)}
              >
                Try again
              </button>
            </div>
          ) : (
            <>
              {cached && (
                <div className={styles.metaBanner}>
                  <span>✦ Served from cache</span>
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
                        <a
                          className="tag tag-purple"
                          href={item.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={(event) => event.stopPropagation()}
                          aria-label={`Preview ${item.name} on ${item.source_type === "youtube" ? "YouTube" : "its blog"} (opens in a new tab)`}
                        >
                          {TYPE_ICONS[item.source_type]} {item.source_type}
                        </a>
                      </div>
                      <a
                        className={styles.cardUrl}
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        onClick={(event) => event.stopPropagation()}
                        aria-label={`Preview ${item.name} (opens in a new tab)`}
                      >
                        {item.url} ↗
                      </a>
                      <p className={styles.cardReason}>
                        {item.recommendation_reason}
                      </p>
                    </div>
                  </div>
                );
              })}
              <div className={styles.findMore}>
                <button
                  className="btn-ghost"
                  onClick={findMore}
                  disabled={findingMore || adding}
                >
                  {findingMore ? "Finding more…" : "Find more"}
                </button>
                <p role="status" aria-live="polite">
                  {findingMore ? "Searching for more sources…" : moreMessage}
                </p>
              </div>
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
                disabled={selectedUrls.size === 0 || adding || findingMore}
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
    </div>,
    document.body
  );
}
