import React from "react";
import UserPage from "./pages/UserPage.jsx";
import AdminPage from "./pages/AdminPage.jsx";

export default function App() {
  const isAdmin =
    typeof window !== "undefined" && window.location.pathname.startsWith("/admin");

  return (
    <div className={isAdmin ? "app-shell app-shell-admin" : "app-shell"}>
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-mark" />
          <span className="brand-text">
            AI Ticket
            <em>智能工单 · 自动分派</em>
          </span>
        </a>
        <nav className="nav">
          <a className={isAdmin ? "" : "active"} href="/">
            用户端
          </a>
          <a className={isAdmin ? "active" : ""} href="/admin">
            管理端
          </a>
        </nav>
      </header>
      <main>{isAdmin ? <AdminPage /> : <UserPage />}</main>
      <footer className="footer">
        AI 分析仅在管理端展示 · 用户凭工单编号与邮箱查询
      </footer>
    </div>
  );
}
