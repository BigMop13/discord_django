/* Real-time chat client used by both channel and DM pages.
 *
 * Reads its configuration from `window.CHAT_CONFIG`:
 *   {
 *     type: "channel" | "dm",
 *     id:   <number>,            // channel id or conversation id
 *     wsPath: "/ws/...",
 *     uploadUrl: "/.../upload/", // multipart endpoint for images/audio
 *     currentUserId: <number>,
 *     isModerator: <bool>,
 *   }
 *
 * Responsibilities:
 *   - open a WebSocket with auto-reconnect
 *   - send / receive plain text messages
 *   - upload images (file picker) and voice messages (MediaRecorder)
 *   - toggle emoji reactions
 *   - soft-delete via WS (mod or author)
 */
(function () {
  const cfg = window.CHAT_CONFIG;
  if (!cfg) return;

  const list = document.getElementById("messageList");
  const composerForm = document.getElementById("composerForm");
  const composerText = document.getElementById("composerText");
  const imageInput = document.getElementById("imageInput");
  const attachImageBtn = document.getElementById("attachImageBtn");
  const recordBtn = document.getElementById("recordAudioBtn");
  const stopRecordBtn = document.getElementById("stopRecordBtn");
  const cancelRecordBtn = document.getElementById("cancelRecordBtn");
  const recordingBar = document.getElementById("recordingBar");
  const recTime = document.getElementById("recTime");
  const emojiToggleBtn = document.getElementById("emojiToggleBtn");
  const emojiPicker = document.getElementById("emojiPicker");

  let ws = null;
  let reconnectDelay = 1000;
  let pendingReactionTarget = null;

  function csrfToken() {
    const m = document.querySelector('meta[name="csrf-token"]');
    if (m) return m.content;
    const inp = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return inp ? inp.value : "";
  }

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function fmtTime(iso) {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function scrollToBottom() {
    if (list) list.scrollTop = list.scrollHeight;
  }

  function renderMessage(m) {
    if (!list) return;
    if (list.querySelector(`[data-message-id="${m.id}"]`)) return;
    const node = document.createElement("div");
    node.className = "message";
    node.dataset.messageId = m.id;
    node.dataset.authorId = m.author_id;

    const canDelete = cfg.isModerator || cfg.currentUserId === m.author_id;
    const avatar = m.author_avatar
      ? `<img src="${m.author_avatar}" alt="">`
      : `<span class="avatar-fallback">${(m.author_username || "?").slice(0, 2).toUpperCase()}</span>`;

    let media = "";
    if (m.kind === "image" && m.attachment_url) {
      media = `<a href="${m.attachment_url}" target="_blank" rel="noopener"><img src="${m.attachment_url}" alt="" class="message-image"></a>`;
    } else if (m.kind === "audio" && m.attachment_url) {
      media = `<audio controls preload="metadata" src="${m.attachment_url}" class="message-audio"></audio>`;
    }

    node.innerHTML = `
      <div class="message-avatar">${avatar}</div>
      <div class="message-body">
        <div class="message-meta">
          <span class="message-author">${escapeHtml(m.author_username)}</span>
          <span class="message-time">${fmtTime(m.created_at)}</span>
          <span class="message-actions">
            <button type="button" class="msg-action" data-react="${m.id}" title="Add reaction"><i class="bi bi-emoji-smile"></i></button>
            ${canDelete ? `<button type="button" class="msg-action text-danger" data-delete="${m.id}" title="Delete"><i class="bi bi-trash"></i></button>` : ""}
          </span>
        </div>
        ${m.is_deleted
          ? `<div class="message-deleted"><i class="bi bi-trash3"></i> message deleted</div>`
          : `${m.body ? `<div class="message-text">${escapeHtml(m.body).replace(/\n/g, "<br>")}</div>` : ""}${media}<div class="message-reactions" data-reactions-for="${m.id}"></div>`}
      </div>`;
    list.appendChild(node);
    scrollToBottom();
  }

  function applyDeleted(messageId) {
    const node = list.querySelector(`[data-message-id="${messageId}"]`);
    if (!node) return;
    const body = node.querySelector(".message-body");
    body.querySelectorAll(".message-text, .message-image, .message-audio, .message-reactions, .message-actions").forEach((n) => n.remove());
    if (!body.querySelector(".message-deleted")) {
      const d = document.createElement("div");
      d.className = "message-deleted";
      d.innerHTML = '<i class="bi bi-trash3"></i> message deleted';
      body.appendChild(d);
    }
  }

  function applyReaction(payload) {
    const wrap = list.querySelector(`[data-reactions-for="${payload.message_id}"]`);
    if (!wrap) return;
    wrap.innerHTML = "";
    Object.entries(payload.counts || {}).forEach(([emoji, count]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "reaction-pill";
      btn.dataset.react = payload.message_id;
      btn.dataset.emoji = emoji;
      btn.innerHTML = `<span>${emoji}</span> <span class="reaction-count">${count}</span>`;
      wrap.appendChild(btn);
    });
  }

  function connect() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}${cfg.wsPath}`);
    ws.onopen = () => {
      reconnectDelay = 1000;
    };
    ws.onmessage = (evt) => {
      let data;
      try { data = JSON.parse(evt.data); } catch (e) { return; }
      if (data.type === "message.new" || data.type === "dm.new") {
        renderMessage(data.message);
      } else if (data.type === "message.deleted" || data.type === "dm.deleted") {
        applyDeleted(data.message_id);
      } else if (data.type === "reaction.changed") {
        applyReaction(data.reaction);
      }
    };
    ws.onclose = () => {
      setTimeout(connect, Math.min(reconnectDelay, 15000));
      reconnectDelay *= 2;
    };
    ws.onerror = () => { try { ws.close(); } catch (e) {} };
  }

  function sendText(body) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ action: "send", body }));
  }

  function sendDelete(messageId) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ action: "delete", message_id: Number(messageId) }));
  }

  function sendReact(messageId, emoji) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    if (cfg.type !== "channel") return; // reactions are channel-only
    ws.send(JSON.stringify({ action: "react", message_id: Number(messageId), emoji }));
  }

  async function uploadFile(file, kind) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("kind", kind);
    const resp = await fetch(cfg.uploadUrl, {
      method: "POST",
      headers: { "X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest" },
      body: fd,
      credentials: "same-origin",
    });
    if (!resp.ok) {
      const err = await resp.json().catch(() => ({}));
      alert(err.detail || "Upload failed.");
    }
  }

  if (composerForm) {
    composerForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const body = composerText.value.trim();
      if (!body) return;
      sendText(body);
      composerText.value = "";
      composerText.focus();
    });
  }

  if (attachImageBtn && imageInput) {
    attachImageBtn.addEventListener("click", () => imageInput.click());
    imageInput.addEventListener("change", () => {
      if (imageInput.files && imageInput.files[0]) {
        uploadFile(imageInput.files[0], "image");
        imageInput.value = "";
      }
    });
  }

  let mediaRecorder = null;
  let audioChunks = [];
  let recStart = 0;
  let recTimer = null;

  async function startRecording() {
    if (!navigator.mediaDevices) {
      alert("Audio recording not supported in this browser.");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunks = [];
      mediaRecorder = new MediaRecorder(stream);
      mediaRecorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) audioChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(audioChunks, { type: mediaRecorder.mimeType || "audio/webm" });
        const ext = blob.type.includes("ogg") ? "ogg" : "webm";
        const file = new File([blob], `voice-${Date.now()}.${ext}`, { type: blob.type });
        await uploadFile(file, "audio");
      };
      mediaRecorder.start();
      recStart = Date.now();
      recordingBar.hidden = false;
      recTimer = setInterval(() => {
        const s = Math.floor((Date.now() - recStart) / 1000);
        recTime.textContent = `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
      }, 250);
    } catch (e) {
      alert("Could not access the microphone.");
    }
  }

  function stopRecording(send) {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      if (!send) mediaRecorder.onstop = null;
      mediaRecorder.stop();
      if (!send && mediaRecorder.stream) {
        mediaRecorder.stream.getTracks().forEach((t) => t.stop());
      }
    }
    clearInterval(recTimer);
    recordingBar.hidden = true;
    recTime.textContent = "0:00";
  }

  if (recordBtn) recordBtn.addEventListener("click", startRecording);
  if (stopRecordBtn) stopRecordBtn.addEventListener("click", () => stopRecording(true));
  if (cancelRecordBtn) cancelRecordBtn.addEventListener("click", () => stopRecording(false));

  if (emojiToggleBtn && emojiPicker) {
    emojiToggleBtn.addEventListener("click", () => {
      pendingReactionTarget = null; // emoji from composer = insert into text
      emojiPicker.hidden = !emojiPicker.hidden;
    });
    emojiPicker.addEventListener("click", (e) => {
      const btn = e.target.closest(".emoji-btn");
      if (!btn) return;
      const emoji = btn.dataset.emoji;
      if (pendingReactionTarget) {
        sendReact(pendingReactionTarget, emoji);
      } else {
        composerText.value = (composerText.value || "") + emoji;
        composerText.focus();
      }
      emojiPicker.hidden = true;
      pendingReactionTarget = null;
    });
  }

  if (list) {
    list.addEventListener("click", (e) => {
      const del = e.target.closest("[data-delete]");
      if (del) {
        sendDelete(del.dataset.delete);
        return;
      }
      const reactBtn = e.target.closest("[data-react]");
      if (reactBtn) {
        const emoji = reactBtn.dataset.emoji;
        if (emoji) {
          sendReact(reactBtn.dataset.react, emoji);
        } else {
          pendingReactionTarget = reactBtn.dataset.react;
          if (emojiPicker) emojiPicker.hidden = false;
        }
      }
    });
  }

  scrollToBottom();
  connect();
})();
