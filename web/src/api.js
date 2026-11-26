async function request(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  let data = null;
  try {
    data = await response.json();
  } catch (error) {
    data = null;
  }
  if (!response.ok) {
    const detail = data && data.detail ? data.detail : `请求失败（${response.status}）`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

export const api = {
  createTicket: (payload) =>
    request("/tickets", { method: "POST", body: JSON.stringify(payload) }),
  getTicket: (ticketNo, email) =>
    request(
      `/tickets/${encodeURIComponent(ticketNo)}?email=${encodeURIComponent(email)}`
    ),
  listTickets: (filters = {}) => {
    const params = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) params.set(key, value);
    });
    const query = params.toString();
    return request(`/admin/tickets${query ? `?${query}` : ""}`);
  },
  getAdminTicket: (id) => request(`/admin/tickets/${id}`),
  updateTicket: (id, payload) =>
    request(`/admin/tickets/${id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  analyzeTicket: (id) =>
    request(`/admin/tickets/${id}/analyze`, { method: "POST" }),
  retryNotification: (id) =>
    request(`/admin/tickets/${id}/notify/retry`, { method: "POST" }),
};
