/* WebRTC mesh client for voice channels.
 *
 * Reads its configuration from `window.VOICE_CONFIG`:
 *   {
 *     wsPath: "/ws/voice/<id>/",
 *     channelId: <number>,
 *     currentUserId: <number>,
 *     iceServers: [{urls: "stun:..."}, ...]   // optional, fallback to public STUN
 *   }
 *
 * Topology: every newcomer establishes an outbound RTCPeerConnection to
 * every existing peer; existing peers wait for incoming offers. SDP and
 * ICE are exchanged via the signaling WebSocket; audio flows P2P.
 */
(function () {
  const cfg = window.VOICE_CONFIG;
  if (!cfg) return;

  const joinBtn = document.getElementById("voiceJoinBtn");
  const leaveBtn = document.getElementById("voiceLeaveBtn");
  const muteBtn = document.getElementById("voiceMuteBtn");
  const connectedList = document.getElementById("voiceConnectedList");
  const statusBadge = document.getElementById("voiceStatus");
  const audioRoot = document.getElementById("voiceAudioRoot");

  let ws = null;
  let localStream = null;
  let isMuted = false;
  let connected = false;
  const peers = new Map();

  const ICE_SERVERS = (cfg.iceServers && cfg.iceServers.length)
    ? cfg.iceServers
    : [{ urls: "stun:stun.l.google.com:19302" }];

  function escapeHtml(s) {
    return (s || "").replace(/[&<>"']/g, (c) => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  function setStatus(text, variant) {
    if (!statusBadge) return;
    statusBadge.textContent = text;
    statusBadge.className = `badge bg-${variant || "secondary"}`;
  }

  function setUiConnected(yes) {
    connected = yes;
    if (joinBtn) joinBtn.hidden = yes;
    if (leaveBtn) leaveBtn.hidden = !yes;
    if (muteBtn) muteBtn.disabled = !yes;
  }

  function addPeerToUi(info) {
    if (!connectedList) return;
    if (connectedList.querySelector(`[data-peer-id="${info.peer_id}"]`)) return;
    const li = document.createElement("li");
    li.className = "voice-member";
    li.dataset.peerId = info.peer_id;
    const avatar = info.avatar
      ? `<img src="${info.avatar}" class="voice-member-avatar" alt="">`
      : `<span class="voice-member-avatar avatar-fallback">${escapeHtml((info.username || "?").slice(0, 2).toUpperCase())}</span>`;
    li.innerHTML = `
      ${avatar}
      <span class="voice-member-name">${escapeHtml(info.username)}</span>
      <i class="bi bi-mic-mute-fill voice-mic-mute" ${info.is_muted ? "" : "hidden"}></i>
    `;
    connectedList.appendChild(li);
  }

  function removePeerFromUi(peerId) {
    if (!connectedList) return;
    const li = connectedList.querySelector(`[data-peer-id="${peerId}"]`);
    if (li) li.remove();
  }

  function setPeerMuteUi(peerId, mutedFlag) {
    if (!connectedList) return;
    const li = connectedList.querySelector(`[data-peer-id="${peerId}"]`);
    if (!li) return;
    const icon = li.querySelector(".voice-mic-mute");
    if (icon) icon.hidden = !mutedFlag;
  }

  function wsSend(obj) {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj));
    }
  }

  function createPeerConnection(peerId) {
    const pc = new RTCPeerConnection({ iceServers: ICE_SERVERS });

    const audioEl = new Audio();
    audioEl.autoplay = true;
    audioEl.dataset.peerId = peerId;
    if (audioRoot) audioRoot.appendChild(audioEl);

    pc.ontrack = (e) => {
      audioEl.srcObject = e.streams[0];
    };
    pc.onicecandidate = (e) => {
      if (e.candidate) {
        wsSend({
          action: "signal",
          target: peerId,
          data: { type: "ice", candidate: e.candidate.toJSON() },
        });
      }
    };

    if (localStream) {
      for (const track of localStream.getTracks()) {
        pc.addTrack(track, localStream);
      }
    }

    const entry = { pc, audioEl, pendingIce: [] };
    peers.set(peerId, entry);
    return entry;
  }

  function destroyPeerConnection(peerId) {
    const entry = peers.get(peerId);
    if (!entry) return;
    try { entry.pc.close(); } catch (e) { /* ignore */ }
    if (entry.audioEl) {
      try { entry.audioEl.srcObject = null; } catch (e) { /* ignore */ }
      entry.audioEl.remove();
    }
    peers.delete(peerId);
  }

  async function callPeer(peerId) {
    const entry = createPeerConnection(peerId);
    const offer = await entry.pc.createOffer({ offerToReceiveAudio: true });
    await entry.pc.setLocalDescription(offer);
    wsSend({
      action: "signal",
      target: peerId,
      data: { type: "sdp", sdp: entry.pc.localDescription },
    });
  }

  async function handleSignal(fromPeerId, data) {
    let entry = peers.get(fromPeerId);
    if (!entry) {
      entry = createPeerConnection(fromPeerId);
    }
    const pc = entry.pc;

    if (data.type === "sdp") {
      await pc.setRemoteDescription(data.sdp);
      while (entry.pendingIce.length) {
        const c = entry.pendingIce.shift();
        try { await pc.addIceCandidate(c); } catch (e) { /* ignore stale ice */ }
      }
      if (data.sdp.type === "offer") {
        const answer = await pc.createAnswer();
        await pc.setLocalDescription(answer);
        wsSend({
          action: "signal",
          target: fromPeerId,
          data: { type: "sdp", sdp: pc.localDescription },
        });
      }
    } else if (data.type === "ice") {
      if (pc.remoteDescription && pc.remoteDescription.type) {
        try { await pc.addIceCandidate(data.candidate); } catch (e) { /* ignore */ }
      } else {
        entry.pendingIce.push(data.candidate);
      }
    }
  }

  async function joinVoice() {
    if (connected) return;
    if (!navigator.mediaDevices || !window.RTCPeerConnection) {
      alert("Voice chat is not supported in this browser.");
      return;
    }
    setStatus("Requesting microphone...", "warning");
    try {
      localStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch (e) {
      setStatus("Microphone denied", "danger");
      alert("Microphone access is required for voice channels.");
      return;
    }

    setStatus("Connecting...", "warning");
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}${cfg.wsPath}`);

    ws.onopen = () => {
      setStatus("Connected", "success");
      setUiConnected(true);
    };
    ws.onmessage = async (evt) => {
      let data;
      try { data = JSON.parse(evt.data); } catch (e) { return; }
      if (data.type === "peer.list") {
        await Promise.all((data.peers || []).map(async (peer) => {
          addPeerToUi(peer);
          try { await callPeer(peer.peer_id); } catch (e) { console.warn(e); }
        }));
      } else if (data.type === "peer.joined") {
        addPeerToUi(data.peer);
      } else if (data.type === "peer.left") {
        removePeerFromUi(data.peer_id);
        destroyPeerConnection(data.peer_id);
      } else if (data.type === "peer.muted") {
        setPeerMuteUi(data.peer_id, data.is_muted);
      } else if (data.type === "signal") {
        try { await handleSignal(data.from, data.data); } catch (e) { console.warn(e); }
      }
    };
    ws.onclose = () => { teardown(); };
    ws.onerror = () => { try { ws.close(); } catch (e) { /* ignore */ } };
  }

  function teardown() {
    setUiConnected(false);
    setStatus("Disconnected", "secondary");
    for (const peerId of Array.from(peers.keys())) {
      destroyPeerConnection(peerId);
    }
    if (connectedList) connectedList.innerHTML = "";
    if (localStream) {
      localStream.getTracks().forEach((t) => t.stop());
      localStream = null;
    }
    isMuted = false;
    if (muteBtn) {
      muteBtn.classList.remove("active");
      const icon = muteBtn.querySelector("i");
      if (icon) icon.className = "bi bi-mic-fill";
      muteBtn.title = "Mute";
    }
  }

  function leaveVoice() {
    if (ws) {
      try { ws.close(); } catch (e) { /* ignore */ }
      ws = null;
    }
    teardown();
  }

  function toggleMute() {
    if (!localStream) return;
    isMuted = !isMuted;
    for (const track of localStream.getAudioTracks()) {
      track.enabled = !isMuted;
    }
    if (muteBtn) {
      muteBtn.classList.toggle("active", isMuted);
      const icon = muteBtn.querySelector("i");
      if (icon) icon.className = isMuted ? "bi bi-mic-mute-fill" : "bi bi-mic-fill";
      muteBtn.title = isMuted ? "Unmute" : "Mute";
    }
    wsSend({ action: "mute", is_muted: isMuted });
  }

  if (joinBtn) joinBtn.addEventListener("click", joinVoice);
  if (leaveBtn) leaveBtn.addEventListener("click", leaveVoice);
  if (muteBtn) muteBtn.addEventListener("click", toggleMute);

  window.addEventListener("beforeunload", () => { leaveVoice(); });

  setUiConnected(false);
  setStatus("Disconnected", "secondary");
})();
