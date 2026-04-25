/* Lightweight presence client.
 *
 * Opens a single WebSocket to /ws/presence/ and toggles each `.status-dot`
 * element's CSS class based on the user_id encoded in its data attribute.
 *
 * Reconnects on close with exponential backoff so that a tab left open
 * across a server restart still recovers automatically.
 */
(function () {
  let ws = null;
  let delay = 1000;

  function applyStatus(userId, status) {
    document
      .querySelectorAll(`[data-presence-user="${userId}"]`)
      .forEach((el) => {
        el.classList.remove("online", "away", "offline");
        el.classList.add(status);
      });
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws/presence/`);
    ws.onopen = () => {
      delay = 1000;
    };
    ws.onmessage = (evt) => {
      try {
        const data = JSON.parse(evt.data);
        if (data.type === "presence") {
          applyStatus(data.user_id, data.status);
        }
      } catch (e) { /* ignore malformed */ }
    };
    ws.onclose = () => {
      setTimeout(connect, Math.min(delay, 15000));
      delay *= 2;
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }

  // Heartbeat every 30s so the server keeps last_seen fresh.
  setInterval(() => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "ping" }));
    }
  }, 30000);

  connect();
})();
