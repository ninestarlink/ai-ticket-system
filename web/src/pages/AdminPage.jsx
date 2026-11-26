import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const PRIORITY_CLASS = {
  高: "badge badge-high",
  中: "badge badge-mid",
  低: "badge badge-low",
};

const ANALYSIS_LABEL = {
  none: "未开始",
  running: "分析中",
  success: "分析完成",
  failed: "分析失败",
};

const NOTIFY_LABEL = {
  sending: "发送中",
  success: "成功",
  failed: "失败",
  unknown: "结果未知",
};

const NOTIFY_CLASS = {
  sending: "badge",
  success: "badge badge-done",
  failed: "badge badge-high",
  unknown: "badge badge-warn",
};

function formatTime(value) {
  if (!value) return "—";
  return new Date(value).toLocaleString("zh-CN", { hour12: false });
}

function JsonBlock({ value }) {
  if (value === null || value === undefined) return <span className="muted">—</span>;
  return <pre className="code">{JSON.stringify(value, null, 2)}</pre>;
}

export default function AdminPage() {
  const [filters, setFilters] = useState({ status: "", priority: "", q: "" });
  const [list, setList] = useState([]);
  const [listError, setListError] = useState("");
  const [selectedId, setSelectedId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailError, setDetailError] = useState("");
  const [busy, setBusy] = useState("");
  const [replyDraft, setReplyDraft] = useState("");
  const [toast, setToast] = useState("");
  const replyIdRef = useRef(null);
  const searchRef = useRef(null);

  const loadList = useCallback(async () => {
    try {
      const data = await api.listTickets(filters);
      setList(data.items);
      setListError("");
    } catch (err) {
      setListError(err.message);
    }
  }, [filters]);

  const loadDetail = useCallback(async (id, silent = false) => {
    if (!id) return;
    try {
      const data = await api.getAdminTicket(id);
      setDetail(data);
      setDetailError("");
      if (replyIdRef.current !== data.id) {
        replyIdRef.current = data.id;
        setReplyDraft(data.public_reply || "");
      }
    } catch (err) {
      if (!silent) setDetailError(err.message);
    }
  }, []);

  useEffect(() => {
    loadList();
    const timer = setInterval(loadList, 4000);
    return () => clearInterval(timer);
  }, [loadList]);

  useEffect(() => {
    const onKey = (event) => {
      const tag = document.activeElement && document.activeElement.tagName;
      const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(tag);
      if (event.key === "/" && !typing) {
        event.preventDefault();
        searchRef.current?.focus();
        return;
      }
      if (
        (event.key === "r" || event.key === "R") &&
        !typing &&
        !event.metaKey &&
        !event.ctrlKey &&
        !event.altKey
      ) {
        event.preventDefault();
        loadList();
        return;
      }
      if (event.key === "Escape") {
        document.activeElement?.blur();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [loadList]);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return undefined;
    }
    replyIdRef.current = null;
    loadDetail(selectedId);
    const timer = setInterval(() => loadDetail(selectedId, true), 2500);
    return () => clearInterval(timer);
  }, [selectedId, loadDetail]);

  const patch = async (payload, message) => {
    if (!selectedId || busy) return;
    setBusy("patch");
    try {
      await api.updateTicket(selectedId, payload);
      await loadDetail(selectedId, true);
      await loadList();
      if (message) {
        setToast(message);
        setTimeout(() => setToast(""), 2000);
      }
    } catch (err) {
      setDetailError(err.message);
    } finally {
      setBusy("");
    }
  };

  const reanalyze = async () => {
    if (!selectedId || busy) return;
    if (!window.confirm("确定重新分析该工单？")) return;
    setBusy("analyze");
    setDetailError("");
    try {
      await api.analyzeTicket(selectedId);
      await loadDetail(selectedId, true);
      await loadList();
    } catch (err) {
      setDetailError(err.message);
    } finally {
      setBusy("");
    }
  };

  const retryNotify = async () => {
    if (!selectedId || busy) return;
    setBusy("notify");
    setDetailError("");
    try {
      await api.retryNotification(selectedId);
      await loadDetail(selectedId, true);
      await loadList();
    } catch (err) {
      setDetailError(err.message);
    } finally {
      setBusy("");
    }
  };

  const latestNotify = detail && detail.notifications.length ? detail.notifications[0] : null;
  const canRetry =
    latestNotify && ["failed", "unknown"].includes(latestNotify.status);

  return (
    <div className="page admin-page">
      <section className="hero compact">
        <p className="eyebrow">Operations Console</p>
        <h1>工单处理台</h1>
        <p className="lede">
          查看 AI 分类、工具调用证据与通知结果；可调整负责人、状态与公开回复。
        </p>
      </section>

      <div className="card filters">
        <label className="field inline">
          <span>状态</span>
          <select
            value={filters.status}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, status: event.target.value }))
            }
          >
            <option value="">全部</option>
            <option value="待处理">待处理</option>
            <option value="处理中">处理中</option>
            <option value="已解决">已解决</option>
          </select>
        </label>
        <label className="field inline">
          <span>优先级</span>
          <select
            value={filters.priority}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, priority: event.target.value }))
            }
          >
            <option value="">全部</option>
            <option value="高">高</option>
            <option value="中">中</option>
            <option value="低">低</option>
          </select>
        </label>
        <label className="field inline grow">
          <span>搜索</span>
          <span className="search-wrap">
            <input
              ref={searchRef}
              value={filters.q}
              onChange={(event) =>
                setFilters((prev) => ({ ...prev, q: event.target.value }))
              }
              placeholder="工单号 / 姓名 / 邮箱 / 描述"
            />
            <kbd className="keycap">/</kbd>
          </span>
        </label>
        <button type="button" className="btn btn-ghost" onClick={loadList}>
          刷新 <kbd className="keycap">R</kbd>
        </button>
      </div>

      {listError ? <p className="error">{listError}</p> : null}

      <div className="admin-layout">
        <div className="card list-card">
          <div className="list-head">
            <span>工单列表</span>
            <span className="muted">{list.length} 条</span>
          </div>
          {list.length === 0 ? (
            <p className="muted empty">暂无工单</p>
          ) : (
            <div className="ticket-list">
              {list.map((item) => (
                <button
                  type="button"
                  key={item.id}
                  data-priority={item.priority || ""}
                  className={
                    selectedId === item.id ? "ticket-item active" : "ticket-item"
                  }
                  onClick={() => setSelectedId(item.id)}
                >
                  <div className="ticket-item-top">
                    <strong>{item.ticket_no}</strong>
                    <span className={PRIORITY_CLASS[item.priority] || "badge"}>
                      {item.priority || "—"}
                    </span>
                  </div>
                  <p className="ticket-item-summary">
                    {item.summary || item.description}
                  </p>
                  <div className="ticket-item-meta">
                    <span>{item.status}</span>
                    <span>{ANALYSIS_LABEL[item.analysis_state] || item.analysis_state}</span>
                    <span>{formatTime(item.created_at)}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="detail-col">
          {!detail ? (
            <div className="card placeholder">
              <div className="placeholder-mark" />
              <h3>选择左侧工单查看详情</h3>
              <p>包含原始问题、AI 分析、工具调用记录与通知结果。</p>
            </div>
          ) : (
            <div className="detail-stack">
              {toast ? <div className="toast">{toast}</div> : null}
              {detailError ? <p className="error">{detailError}</p> : null}

              <div className="card">
                <div className="detail-head">
                  <div>
                    <p className="eyebrow">工单</p>
                    <h2 className="ticket-no">{detail.ticket_no}</h2>
                  </div>
                  <div className="badge-row">
                    <span className={PRIORITY_CLASS[detail.priority] || "badge"}>
                      优先级 {detail.priority || "—"}
                    </span>
                    <span className="badge">{detail.status}</span>
                    <span className="badge">
                      {ANALYSIS_LABEL[detail.analysis_state] || detail.analysis_state}
                    </span>
                  </div>
                </div>

                <div className="meta-grid">
                  <div>
                    <span>姓名</span>
                    <strong>{detail.name}</strong>
                  </div>
                  <div>
                    <span>邮箱</span>
                    <strong>{detail.email}</strong>
                  </div>
                  <div>
                    <span>订单号</span>
                    <strong>{detail.order_id || "未识别"}</strong>
                  </div>
                  <div>
                    <span>创建时间</span>
                    <strong>{formatTime(detail.created_at)}</strong>
                  </div>
                </div>

                <div className="block">
                  <p className="eyebrow">原始问题</p>
                  <p className="description">{detail.description}</p>
                </div>
              </div>

              <div className="card">
                <div className="section-head">
                  <h3>AI 分析</h3>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={reanalyze}
                    disabled={busy === "analyze" || detail.analysis_state === "running"}
                  >
                    {detail.analysis_state === "running" ? "分析中…" : "重新分析"}
                  </button>
                </div>

                {detail.analysis_state === "running" ? (
                  <p className="muted">模型分析中，请稍候…</p>
                ) : null}

                {detail.analysis ? (
                  <>
                    {detail.analysis.status === "failed" ? (
                      <div className="alert">
                        <strong>分析失败</strong>
                        <p>{detail.analysis.error || "模型调用失败"}</p>
                        <p className="muted">工单已保留，模型恢复后可点击“重新分析”。</p>
                      </div>
                    ) : (
                      <>
                        <div className="ai-grid">
                          <div>
                            <span>类别</span>
                            <strong>{detail.analysis.category || "—"}</strong>
                          </div>
                          <div>
                            <span>优先级</span>
                            <strong>{detail.analysis.priority || "—"}</strong>
                          </div>
                          <div>
                            <span>部门 / 负责人</span>
                            <strong>
                              {detail.department || "—"} / {detail.assignee || "—"}
                            </strong>
                          </div>
                          <div>
                            <span>耗时</span>
                            <strong>
                              {detail.analysis.latency_ms
                                ? `${detail.analysis.latency_ms} ms`
                                : "—"}
                            </strong>
                          </div>
                        </div>
                        <div className="block">
                          <p className="eyebrow">摘要</p>
                          <p>{detail.analysis.summary || "—"}</p>
                        </div>
                        <div className="block">
                          <p className="eyebrow">处理建议</p>
                          <p>{detail.analysis.suggestion || "—"}</p>
                        </div>
                      </>
                    )}
                    <p className="muted small">
                      模型：{detail.analysis.model || "—"} · 分析时间：
                      {formatTime(detail.analysis.created_at)}
                    </p>
                  </>
                ) : (
                  <p className="muted">暂无分析记录</p>
                )}
              </div>

              <div className="card">
                <h3>工具调用记录</h3>
                {detail.analysis && detail.analysis.tool_calls.length ? (
                  <div className="timeline">
                    {detail.analysis.tool_calls.map((call) => (
                      <div key={call.id} className="timeline-item">
                        <div className="timeline-head">
                          <strong>{call.name}</strong>
                          <span className={call.ok ? "badge badge-done" : "badge badge-high"}>
                            {call.ok ? "成功" : "异常"}
                          </span>
                        </div>
                        <div className="call-grid">
                          <div>
                            <p className="eyebrow">入参</p>
                            <JsonBlock value={call.arguments} />
                          </div>
                          <div>
                            <p className="eyebrow">返回</p>
                            <JsonBlock value={call.result} />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="muted">本次分析未调用工具</p>
                )}
              </div>

              <div className="card">
                <div className="section-head">
                  <h3>飞书通知</h3>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={retryNotify}
                    disabled={!canRetry || busy === "notify"}
                    title={
                      canRetry
                        ? "仅失败或结果未知时可重试"
                        : "仅失败或结果未知时可重试"
                    }
                  >
                    重试通知
                  </button>
                </div>

                {detail.notifications.length === 0 ? (
                  <p className="muted">
                    该工单未发送通知（仅高优先级工单发送，且每条工单最多自动发送一次）。
                  </p>
                ) : (
                  <div className="timeline">
                    {detail.notifications.map((item) => (
                      <div key={item.id} className="timeline-item">
                        <div className="timeline-head">
                          <strong>{formatTime(item.created_at)}</strong>
                          <span className={NOTIFY_CLASS[item.status] || "badge"}>
                            {NOTIFY_LABEL[item.status] || item.status}
                          </span>
                        </div>
                        {item.error ? <p className="error small">{item.error}</p> : null}
                        {item.http_status ? (
                          <p className="muted small">HTTP {item.http_status}</p>
                        ) : null}
                        <details>
                          <summary>查看请求内容</summary>
                          <JsonBlock value={item.request_body} />
                        </details>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className="card">
                <h3>处理操作</h3>
                <div className="op-grid">
                  <label className="field">
                    <span>状态</span>
                    <select
                      value={detail.status}
                      onChange={(event) =>
                        patch({ status: event.target.value }, "状态已更新")
                      }
                      disabled={busy === "patch"}
                    >
                      <option value="待处理">待处理</option>
                      <option value="处理中">处理中</option>
                      <option value="已解决">已解决</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>负责人</span>
                    <select
                      value={detail.assignee || ""}
                      onChange={(event) =>
                        patch({ assignee: event.target.value }, "负责人已更新")
                      }
                      disabled={busy === "patch"}
                    >
                      {detail.assignee_options.map((name) => (
                        <option key={name} value={name}>
                          {name}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>

                <label className="field">
                  <span>公开回复（用户可见）</span>
                  <textarea
                    rows={4}
                    value={replyDraft}
                    maxLength={2000}
                    onChange={(event) => setReplyDraft(event.target.value)}
                    placeholder="填写后用户可在查询页看到"
                  />
                </label>
                <div className="section-head">
                  <span className="muted small">
                    AI 分析与建议仅在管理端展示，不会展示给客户。
                  </span>
                  <button
                    type="button"
                    className="btn btn-primary"
                    onClick={() =>
                      patch({ public_reply: replyDraft }, "公开回复已保存")
                    }
                    disabled={busy === "patch"}
                  >
                    保存回复
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
