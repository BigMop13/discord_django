/* Ephemeral notifications client.
 *
 * Opens a single WebSocket to /ws/notifications/ and listens for events
 * pushed by accounts.notify.push_to_user(...). For each unread channel/DM
 * a small badge is rendered in the sidebar (`[data-unread-target]`) and
 * a Bootstrap toast is shown.
 *
 * State is in-memory: refreshing the page resets all counters. If the user
 * is currently viewing a target (window.CURRENT_LOCATION matches), the
 * notification is silently dropped so we don't badge what they already see.
 */
(function () {
  const unread = new Map();
  let ws = null;
  let delay = 1000;

  function targetKey(kind, id) {
    return `${kind}:${id}`;
  }

  function currentKey() {
    const loc = window.CURRENT_LOCATION;
    if (!loc || !loc.type || !loc.id) return null;
    return targetKey(loc.type, loc.id);
  }

  function renderBadge(key) {
    const count = unread.get(key) || 0;
    document.querySelectorAll(`[data-unread-target="${key}"]`).forEach((el) => {
      if (count <= 0) {
        el.hidden = true;
        el.textContent = "";
      } else {
        el.hidden = false;
        el.textContent = count > 99 ? "99+" : String(count);
      }
    });
  }

  function clearKey(key) {
    if (unread.has(key)) {
      unread.delete(key);
      renderBadge(key);
    }
  }

  function ensureToastContainer() {
    let host = document.getElementById("notifToastHost");
    if (host) return host;
    host = document.createElement("div");
    host.id = "notifToastHost";
    host.className = "toast-container position-fixed bottom-0 end-0 p-3";
    host.style.zIndex = "1080";
    document.body.appendChild(host);
    return host;
  }

  function showToast(payload) {
    const host = ensureToastContainer();
    const el = document.createElement("div");
    el.className = "toast align-items-center text-bg-dark border-0 show notif-toast";
    el.setAttribute("role", "alert");
    const href =
      payload.kind === "channel" && payload.channel_slug
        ? `/channels/${payload.channel_slug}/`
        : payload.kind === "dm" && payload.conversation_id
        ? `/dm/${payload.conversation_id}/`
        : "#";
    const heading =
      payload.kind === "channel"
        ? `#${payload.channel_name || "channel"}`
        : `@${payload.author_username}`;
    el.innerHTML = `
      <div class="d-flex">
        <div class="toast-body">
          <a href="${href}" class="text-decoration-none text-reset d-block">
            <div class="fw-semibold small text-truncate">${escapeHtml(heading)}</div>
            <div class="small text-truncate"><span class="text-muted">${escapeHtml(payload.author_username)}:</span> ${escapeHtml(payload.preview || "")}</div>
          </a>
        </div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>`;
    host.appendChild(el);
    setTimeout(() => {
      el.classList.remove("show");
      setTimeout(() => el.remove(), 300);
    }, 5000);
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function handle(payload) {
    if (!payload || !payload.kind || payload.target_id == null) return;
    const key = targetKey(payload.kind, payload.target_id);
    if (key === currentKey()) return; // user is already on this page
    unread.set(key, (unread.get(key) || 0) + 1);
    renderBadge(key);
    showToast(payload);
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/notifications/`);
    ws.onopen = () => {
      delay = 1000;
    };
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === "notification") {
          handle(data.payload);
        }
      } catch (e) { /* ignore malformed */ }
    };
    ws.onclose = () => {
      setTimeout(connect, Math.min(delay, 15000));
      delay *= 2;
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }

  document.addEventListener("DOMContentLoaded", () => {
    const key = currentKey();
    if (key) clearKey(key);
  });

  connect();
})();
