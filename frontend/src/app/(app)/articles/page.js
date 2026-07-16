// src/app/(app)/articles/page.js — Article feed with summary drawer
"use client";

import { useState, useEffect, useCallback } from "react";
import { useAuth } from "@/context/AuthContext";
import { getArticles, getArticleDetail } from "@/lib/api";
import styles from "./page.module.css";

const PAGE_SIZE = 20;

export default function ArticlesPage() {
  const { user } = useAuth();
  const [articles, setArticles] = useState([]);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);   // article detail
  const [detailLoading, setDetailLoading] = useState(false);

  const fetchArticles = useCallback(async (reset = false) => {
    if (!user?.email) return;
    const currentOffset = reset ? 0 : offset;
    setLoading(true);
    try {
      const data = await getArticles(user.email, PAGE_SIZE, currentOffset);
      setArticles(prev => reset ? data : [...prev, ...data]);
      setHasMore(data.length === PAGE_SIZE);
      setOffset(currentOffset + data.length);
    } catch (e) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [user, offset]);

  useEffect(() => { fetchArticles(true); }, [user]);  // eslint-disable-line

  const openDetail = async (article) => {
    setSelected({ ...article, loading: true });
    setDetailLoading(true);
    try {
      const detail = await getArticleDetail(user.email, article.id);
      setSelected(detail);
    } catch (e) {
      console.error(e);
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <>
      <div className="animate-fade-in">
        <header className={styles.header}>
        <h1 className={styles.title}>Articles</h1>
        <p className={styles.subtitle}>Recent articles from your subscribed sources</p>
      </header>

      {loading && articles.length === 0 ? (
        <div className={styles.skeletonGrid}>
          {Array.from({length: 6}).map((_, i) => <div key={i} className={styles.skeleton} />)}
        </div>
      ) : articles.length === 0 ? (
        <div className={styles.empty}>
          <p>No articles yet — run the pipeline to fetch some!</p>
        </div>
      ) : (
        <>
          <div className={styles.grid}>
            {articles.map(article => (
              <button
                key={article.id}
                className={`card ${styles.articleCard}`}
                onClick={() => openDetail(article)}
              >
                <div className={styles.articleMeta}>
                  {(() => {
                    const isVideo = article.url?.includes("youtube.com") || article.url?.includes("youtu.be");
                    return (
                      <span className={`tag ${isVideo ? "tag-purple" : "tag-green"}`}>
                        {isVideo ? "Video" : "Article"}
                      </span>
                    );
                  })()}
                  <span className={styles.date}>
                    {new Date(article.published_at).toLocaleDateString("en-US", {
                      month: "short", day: "numeric"
                    })}
                  </span>
                </div>
                <h3 className={styles.articleTitle}>{article.title}</h3>
                <span className={styles.readMore}>Read summary →</span>
              </button>
            ))}
          </div>

          {hasMore && (
            <button
              className={`btn-ghost ${styles.loadMore}`}
              onClick={() => fetchArticles(false)}
              disabled={loading}
            >
              {loading ? <><span className="spinner" /> Loading…</> : "Load more"}
            </button>
          )}
        </>
      )}
      </div>

      {/* Detail Drawer */}
      {selected && (
        <div className={styles.drawerOverlay} onClick={() => setSelected(null)}>
          <div className={styles.drawer} onClick={e => e.stopPropagation()}>
            <button className={styles.closeBtn} onClick={() => setSelected(null)}>✕</button>

            {detailLoading ? (
              <div className={styles.drawerLoading}><div className="spinner" style={{width:28,height:28}}/></div>
            ) : (
              <>
                <p className={styles.drawerDate}>
                  {new Date(selected.published_at).toLocaleDateString("en-US", {
                    weekday: "long", year: "numeric", month: "long", day: "numeric"
                  })}
                </p>
                <h2 className={styles.drawerTitle}>{selected.title}</h2>

                {selected.summary ? (
                  <div className={styles.drawerSummary}>
                    <h3>Summary</h3>
                    <p>{selected.summary}</p>
                  </div>
                ) : (
                  <p className={styles.noSummary}>No summary available yet.</p>
                )}

                {selected.url && (
                  <a
                    href={selected.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="btn-primary"
                    style={{display:"inline-flex", marginTop:24}}
                  >
                    Read Original Article ↗
                  </a>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </>
  );
}
