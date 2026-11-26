import React, { useEffect, useRef, useState } from "react";
import { api } from "../api.js";

const STATUS_FLOW = ["待处理", "处理中", "已解决"];
const IS_MAC =
  typeof navigator !== "undefined" && /Mac|iPhone|iPad/.test(navigator.userAgent);
const MOD_KEY = IS_MAC ? "⌘" : "Ctrl";

function newToken() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function StatusBadge({ status }) {
  const cls =
    status === "已解决" ? "badge badge-done" : status === "处理中" ? "badge badge-doing" : "badge";
  return <span className={cls}>{status || "待处理"}</span>;
}

function StatusSteps({ status }) {
  const index = Math.max(0, STATUS_FLOW.indexOf(status));
  return (
    <div className="steps">
      {STATUS_FLOW.map((item, i) => (
        <div key={item} className={`step ${i <= index ? "on" : ""}`}>
          <span className="dot" />
          <span>{item}</span>
        </div>
      ))}
    </div>
  );
}

function TicketCard({ ticket, note }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(ticket.ticket_no);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      setCopied(false);
    }
  };

  return (
    <div className="card ticket-card">
      <div className="ticket-head">
        <div>
          <p className="eyebrow">工单编号</p>
          <h2 className="ticket-no">{ticket.ticket_no}</h2>
        </div>
        <StatusBadge status={ticket.status} />
      </div>
      {note ? <p className="hint">{note}</p> : null}
      <StatusSteps status={ticket.status} />

      <div className="kv">
        <div>
          <span>提交时间</span>
          <strong>{new Date(ticket.created_at).toLocaleString("zh-CN")}</strong>
        </div>
        <div>
          <span>识别订单号</span>
          <strong>{ticket.order_id || "未提供"}</strong>
        </div>
      </div>

      <div className="reply-box">
        <p className="eyebrow">管理员公开回复</p>
        <p className={ticket.public_reply ? "reply-text" : "muted"}>
          {ticket.public_reply || "暂无公开回复，请稍后刷新查看。"}
        </p>
      </div>

      <div className="ticket-actions">
        <button type="button" className="btn btn-ghost" onClick={copy}>
          {copied ? "已复制" : "复制工单编号"}
        </button>
      </div>
    </div>
  );
}

export default function UserPage() {
  const [tab, setTab] = useState("submit");
  const [form, setForm] = useState({
    name: "",
    email: "",
    order_id: "",
    description: "",
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState(null);
  const [createdEmail, setCreatedEmail] = useState("");
  const [detail, setDetail] = useState(null);
  const tokenRef = useRef(newToken());

  const [query, setQuery] = useState({ ticket_no: "", email: "" });
  const [querying, setQuerying] = useState(false);
  const [queryError, setQueryError] = useState("");
  const [queryDetail, setQueryDetail] = useState(null);

  useEffect(() => {
    if (!created) return undefined;
    let active = true;
    const load = async () => {
      try {
        const data = await api.getTicket(created.ticket_no, createdEmail);
        if (active) setDetail(data);
      } catch (err) {
        // 轮询失败不打断页面
      }
    };
    load();
    const timer = setInterval(load, 3000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [created, createdEmail]);

  const update = (key) => (event) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try {
      const data = await api.createTicket({
        name: form.name.trim(),
        email: form.email.trim(),
        order_id: form.order_id.trim() || null,
        description: form.description.trim(),
        submission_token: tokenRef.current,
      });
      tokenRef.current = newToken();
      setCreated({ ticket_no: data.ticket_no, status: data.status });
      setCreatedEmail(form.email.trim().toLowerCase());
      setDetail(null);
      setForm((prev) => ({ ...prev, description: "", order_id: "" }));
      const ticket = await api.getTicket(data.ticket_no, form.email.trim().toLowerCase());
      setDetail(ticket);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const runQuery = async (event) => {
    event.preventDefault();
    if (querying) return;
    setQuerying(true);
    setQueryError("");
    setQueryDetail(null);
    try {
      const data = await api.getTicket(
        query.ticket_no.trim(),
        query.email.trim().toLowerCase()
      );
      setQueryDetail(data);
    } catch (err) {
      setQueryError(err.message);
    } finally {
      setQuerying(false);
    }
  };

  const submitShortcut = (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      submit(event);
    }
  };

  const queryShortcut = (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
      event.preventDefault();
      runQuery(event);
    }
  };

  return (
    <div className="page">
      <section className="hero">
        <p className="eyebrow">Customer Support</p>
        <h1>把问题交给我们，进度随时可查</h1>
        <p className="lede">
          提交后立即生成工单编号。AI 在后台完成分类与分派，高优先级问题会即时通知对应部门。
        </p>
      </section>

      <div className="tabs">
        <button
          type="button"
          className={tab === "submit" ? "tab active" : "tab"}
          onClick={() => setTab("submit")}
        >
          提交工单
        </button>
        <button
          type="button"
          className={tab === "query" ? "tab active" : "tab"}
          onClick={() => setTab("query")}
        >
          查询进度
        </button>
      </div>

      {tab === "submit" ? (
        <div className="user-grid">
          <form className="card form" onSubmit={submit} onKeyDown={submitShortcut}>
            <div className="palette-head">
              <div className="palette-icon">+</div>
              <div>
                <h2>新建工单</h2>
                <p>描述问题，AI 自动分类并分派</p>
              </div>
              <div className="keycaps">
                <kbd className="keycap">{MOD_KEY}</kbd>
                <kbd className="keycap">↵</kbd>
              </div>
            </div>
            <div className="form-row">
              <label className="field">
                <span>姓名</span>
                <input
                  value={form.name}
                  onChange={update("name")}
                  placeholder="请输入姓名"
                  maxLength={50}
                  required
                />
              </label>
              <label className="field">
                <span>邮箱</span>
                <input
                  type="email"
                  value={form.email}
                  onChange={update("email")}
                  placeholder="用于查询进度"
                  maxLength={120}
                  required
                />
              </label>
            </div>

            <label className="field">
              <span>订单号（可选）</span>
              <input
                value={form.order_id}
                onChange={update("order_id")}
                placeholder="例如 A1002；也可以直接写在问题描述里"
                maxLength={32}
              />
            </label>

            <label className="field">
              <span>问题描述</span>
              <textarea
                value={form.description}
                onChange={update("description")}
                placeholder="请描述遇到的问题，涉及订单时建议附上订单号"
                rows={6}
                maxLength={4000}
                required
              />
            </label>

            {error ? <p className="error">{error}</p> : null}

            <button type="submit" className="btn btn-primary" disabled={submitting}>
              {submitting ? (
                "提交中，请勿重复点击…"
              ) : (
                <>
                  提交工单 <kbd className="keycap">↵</kbd>
                </>
              )}
            </button>
            <p className="hint">
              提交过程中按钮会锁定，网络重试也不会重复建单。按 {MOD_KEY} + Enter
              也可以提交，内容相同的新提交仍会正常生成新工单。
            </p>
          </form>

          <div className="result-col">
            {detail ? (
              <TicketCard
                ticket={detail}
                note={`查询凭据：${createdEmail}，请与工单编号一起保存。`}
              />
            ) : (
              <div className="card process-card">
                <div className="palette-head">
                  <div className="palette-icon">?</div>
                  <div>
                    <h2>提交之后</h2>
                    <p>工单编号和处理进度会显示在这里</p>
                  </div>
                </div>
                <ol className="process-list">
                  <li>
                    <span className="num">1</span>
                    AI 识别问题类别与优先级
                  </li>
                  <li>
                    <span className="num">2</span>
                    自动分派到对应部门
                  </li>
                  <li>
                    <span className="num">3</span>
                    高优先级问题即时通知
                  </li>
                </ol>
                <div className="process-status">
                  <span className="status-dot" />
                  <div>
                    <strong>等待提交</strong>
                    <span>提交后显示工单编号与处理状态</span>
                  </div>
                </div>
                <p className="hint process-note">
                  工单编号 + 提交邮箱是唯一查询凭据，不会展示他人的工单。
                </p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <div className="user-grid">
          <form className="card form" onSubmit={runQuery} onKeyDown={queryShortcut}>
            <div className="palette-head">
              <div className="palette-icon">?</div>
              <div>
                <h2>查询工单</h2>
                <p>用编号和邮箱查看处理进度</p>
              </div>
              <div className="keycaps">
                <kbd className="keycap">{MOD_KEY}</kbd>
                <kbd className="keycap">↵</kbd>
              </div>
            </div>
            <label className="field">
              <span>工单编号</span>
              <input
                value={query.ticket_no}
                onChange={(event) =>
                  setQuery((prev) => ({ ...prev, ticket_no: event.target.value }))
                }
                placeholder="例如 TK-260305-1A2B3C"
                maxLength={32}
                required
              />
            </label>
            <label className="field">
              <span>提交时的邮箱</span>
              <input
                type="email"
                value={query.email}
                onChange={(event) =>
                  setQuery((prev) => ({ ...prev, email: event.target.value }))
                }
                placeholder="必须与提交时一致"
                maxLength={120}
                required
              />
            </label>
            {queryError ? <p className="error">{queryError}</p> : null}
            <button type="submit" className="btn btn-primary" disabled={querying}>
              {querying ? (
                "查询中…"
              ) : (
                <>
                  查询工单 <kbd className="keycap">↵</kbd>
                </>
              )}
            </button>
            <p className="hint">
              邮箱不匹配时无法查询，避免工单信息泄露。按 {MOD_KEY} + Enter 也可以查询。
            </p>
          </form>

          <div className="result-col">
            {queryDetail ? (
              <TicketCard ticket={queryDetail} />
            ) : (
              <div className="card placeholder">
                <div className="placeholder-mark" />
                <h3>输入工单编号与邮箱</h3>
                <p>查看当前处理状态和客服的公开回复。</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
