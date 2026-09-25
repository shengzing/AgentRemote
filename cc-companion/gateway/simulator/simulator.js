(() => {
  "use strict";

  const PROTOCOL_VERSION = 1;
  const TOKEN_STORAGE_PREFIX = "cc-companion-simulator-token:";
  const SESSION_KEY_PREFIX = "cc-companion-injected-session:";
  const INJECT_PRESETS = {
    permission: {
      hook_event_name: "Notification",
      message: "Claude is asking for your permission to run Bash: ls",
    },
    await_input: {
      hook_event_name: "Notification",
      message: "Assistant is waiting for your input",
    },
    working: {
      hook_event_name: "PreToolUse",
      message: "Read auth.py",
    },
    done: {
      hook_event_name: "Stop",
      message: "任务完成",
    },
    error: {
      hook_event_name: "Stop",
      message: "测试失败: assertion error",
    },
  };

  const elements = {
    connectionLight: document.querySelector("#connection-light"),
    connectionLabel: document.querySelector("#connection-label"),
    connectForm: document.querySelector("#connect-form"),
    deviceId: document.querySelector("#device-id"),
    pairingCode: document.querySelector("#pairing-code"),
    connectButton: document.querySelector("#connect-button"),
    screenTarget: document.querySelector("#screen-target"),
    screenNetwork: document.querySelector("#screen-network"),
    screenRows: document.querySelector("#screen-rows"),
    revision: document.querySelector("#revision-label"),
    nextButton: document.querySelector("#next-button"),
    recordButton: document.querySelector("#record-button"),
    deviceButton: document.querySelector("#device-button"),
    transcriptPanel: document.querySelector("#transcript-panel"),
    draftTarget: document.querySelector("#draft-target"),
    draftText: document.querySelector("#draft-text"),
    sendButton: document.querySelector("#send-button"),
    cancelButton: document.querySelector("#cancel-button"),
    rerecordButton: document.querySelector("#rerecord-button"),
    retargetButton: document.querySelector("#retarget-button"),
    recordingProgress: document.querySelector(".recording-progress"),
    recordingProgressBar: document.querySelector("#recording-progress-bar"),
    recordingStatus: document.querySelector("#recording-status"),
    recordingStatusText: document.querySelector("#recording-status-text"),
    eventLog: document.querySelector("#event-log"),
    detailView: document.querySelector("#detail-view"),
    detailHeader: document.querySelector("#detail-header"),
    detailRows: document.querySelector("#detail-rows"),
    detailScrollHint: document.querySelector("#detail-scroll-hint"),
    detailList: document.querySelector("#detail-list"),
    detailRecording: document.querySelector("#detail-recording"),
    detailTranscribing: document.querySelector("#detail-transcribing"),
    detailReady: document.querySelector("#detail-ready"),
    detailResult: document.querySelector("#detail-result"),
    dndIndicator: document.querySelector("#dnd-indicator"),
    recTargetCode: document.querySelector("#rec-target-code"),
    recBarFill: document.querySelector("#rec-bar-fill"),
    recTimer: document.querySelector("#rec-timer"),
    trTargetCode: document.querySelector("#tr-target-code"),
    readyTargetCode: document.querySelector("#ready-target-code"),
    readyText: document.querySelector("#ready-text"),
    resultHead: document.querySelector("#result-head"),
    resultText: document.querySelector("#result-text"),
    injectToggle: document.querySelector("#inject-toggle"),
    injectDrawer: document.querySelector("#inject-drawer"),
    injectClose: document.querySelector("#inject-close"),
    injectPresets: document.querySelector("#inject-presets"),
    injectForm: document.querySelector("#inject-form"),
    injectCc: document.querySelector("#inject-cc"),
    injectCcPreview: document.querySelector("#inject-cc-preview"),
    injectSession: document.querySelector("#inject-session"),
    injectEvent: document.querySelector("#inject-event"),
    injectMessage: document.querySelector("#inject-message"),
    injectReset: document.querySelector("#inject-reset"),
    targetPicker: document.querySelector("#target-picker"),
    pickerList: document.querySelector("#picker-list"),
    pickerNetwork: document.querySelector("#picker-network"),
  };

  const model = {
    socket: null,
    connected: false,
    rows: [],
    revision: 0,
    selectedCode: null,
    awaitingAck: false,
    reconnectDelay: 1000,
    reconnectTimer: null,
    recording: false,
    recordingTimer: null,
    recordingStartedAt: 0,
    recordingInterval: null,
    recordingMaxMs: 1500,
    transcribingTimer: null,
    pickerOpen: false,
    pickerCursor: 0,
    drawerOpen: false,
    lastDoubleClickAt: 0,
    lastClickAt: 0,
    lastClickAt2: 0,
    tripleClickPending: false,
    viewMode: "list",
    detailCcCode: null,
    detailScroll: 0,
    detailHistory: {},
    detailSubmode: "list",
    dnd: false,
    pendingAttentions: [],  // DND 期间缓存的高优先级 cc_code 列表
    singlePressStack: [],   // 撤销栈：每次单击保存状态，三连击触发时弹出
    singlePressClearTimer: null,
    _bottomWarned: false,
    _lastSendOk: null,
    _lastSendError: null,
  };

  function captureViewState() {
    return {
      selectedCode: model.selectedCode,
      detailCcCode: model.detailCcCode,
      detailScroll: model.detailScroll,
      viewMode: model.viewMode,
      detailSubmode: model.detailSubmode,
    };
  }

  function restoreViewState(s) {
    model.selectedCode = s.selectedCode;
    model.detailCcCode = s.detailCcCode;
    model.detailScroll = s.detailScroll;
    model.viewMode = s.viewMode;
    model.detailSubmode = s.detailSubmode;
    render();
  }

  function wsUrl() {
    return `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws`;
  }

  function tokenKey() {
    return `${TOKEN_STORAGE_PREFIX}${elements.deviceId.value.trim()}`;
  }

  function sessionStorageKey(ccCode) {
    return `${SESSION_KEY_PREFIX}${ccCode}`;
  }

  function readToken() { return localStorage.getItem(tokenKey()); }
  function saveToken(token) { localStorage.setItem(tokenKey(), token); }
  function readStoredSession(ccCode) { return localStorage.getItem(sessionStorageKey(ccCode)); }
  function saveStoredSession(ccCode, sid) { localStorage.setItem(sessionStorageKey(ccCode), sid); }
  function clearStoredSessions() {
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const k = localStorage.key(i);
      if (k && k.startsWith(SESSION_KEY_PREFIX)) localStorage.removeItem(k);
    }
  }

  function log(message, tone = "") {
    const item = document.createElement("li");
    const stamp = document.createElement("time");
    stamp.textContent = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    const content = document.createElement("span");
    content.textContent = message;
    content.className = tone;
    item.append(stamp, content);
    elements.eventLog.prepend(item);
    while (elements.eventLog.children.length > 12) elements.eventLog.lastElementChild.remove();
  }

  function setConnected(connected, label) {
    model.connected = connected;
    elements.connectionLight.classList.toggle("online", connected);
    elements.connectionLight.classList.toggle("offline", !connected);
    elements.connectionLabel.textContent = label;
    elements.screenNetwork.textContent = connected ? "ONLINE" : "OFFLINE";
    elements.pickerNetwork.textContent = connected ? "ONLINE" : "OFFLINE";
    elements.nextButton.disabled = !connected || model.rows.length === 0;
    elements.recordButton.disabled = !connected || model.selectedCode === null;
    render();
    if (!connected) closeTargetPicker();
  }

  function sortRows() {
    model.rows.sort((left, right) => left.cc_code - right.cc_code);
  }

  function selectValidTarget() {
    if (!model.rows.some((row) => row.cc_code === model.selectedCode)) {
      model.selectedCode = model.rows.length ? model.rows[0].cc_code : null;
    }
  }

  function stateMarker(state) {
    return { WORKING: "▶", AWAITING_CONFIRMATION: "❓", AWAITING_INPUT: "…", DONE: "✓", ERROR: "✗", IDLE: "·" }[state] || "·";
  }

  function beep(pattern = "alert") {
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      const ctx = model._audioCtx || new AudioCtx();
      model._audioCtx = ctx;
      if (ctx.state === "suspended") ctx.resume();
      const playTone = (startAt, freq, dur) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.frequency.value = freq;
        osc.type = "square";
        gain.gain.setValueAtTime(0, startAt);
        gain.gain.linearRampToValueAtTime(0.18, startAt + 0.01);
        gain.gain.linearRampToValueAtTime(0, startAt + dur);
        osc.connect(gain).connect(ctx.destination);
        osc.start(startAt);
        osc.stop(startAt + dur + 0.02);
      };
      const t0 = ctx.currentTime + 0.02;
      if (pattern === "alert") {
        playTone(t0, 880, 0.10);
        playTone(t0 + 0.18, 880, 0.10);
      } else if (pattern === "send") {
        playTone(t0, 660, 0.08);
      } else if (pattern === "cancel") {
        playTone(t0, 330, 0.10);
      }
    } catch (error) {
      /* ignore */
    }
  }

  function vibrate(pattern) {
    if (typeof navigator.vibrate !== "function") return;
    try { navigator.vibrate(pattern); } catch (_) { /* ignore */ }
  }

  function alertAttention() {
    beep("alert");
    vibrate([200, 80, 200]);
  }

  function render() {
    elements.revision.textContent = `REV ${model.revision}`;
    if (model.viewMode === "detail") {
      renderDetailView();
      return;
    }
    renderListView();
  }

  function renderListView() {
    elements.screenTarget.textContent = model.selectedCode === null ? "CC --" : `CC ->#${model.selectedCode}`;
    if (elements.detailView) elements.detailView.classList.add("hidden");
    elements.screenRows.classList.remove("hidden");
    elements.screenRows.replaceChildren();
    if (!model.rows.length) {
      const empty = document.createElement("p");
      empty.className = "empty-state";
      empty.textContent = model.connected ? "暂无 CC 状态" : "等待网关连接";
      elements.screenRows.append(empty);
      if (model.pickerOpen) renderPicker();
      return;
    }
    for (const row of model.rows) {
      const line = document.createElement("div");
      line.className = "screen-row";
      line.dataset.cc = String(row.cc_code);
      if (row.cc_code === model.selectedCode) line.classList.add("selected");
      if (row.state === "ERROR") line.classList.add("error");
      else if (row.state === "DONE") line.classList.add("done");
      if (row.priority === "high" && String(row.state).startsWith("AWAITING")) line.classList.add("attention");
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = `#${row.cc_code}`;
      const state = document.createElement("span");
      state.className = "state";
      state.textContent = stateMarker(row.state);
      const summary = document.createElement("span");
      summary.className = "summary";
      summary.textContent = row.summary || row.state;
      line.append(badge, state, summary);
      elements.screenRows.append(line);
    }
    scrollSelectedIntoView();
    if (model.pickerOpen) renderPicker();
  }

  function renderDetailView() {
    const row = model.rows.find((r) => r.cc_code === model.detailCcCode);
    if (!row) {
      leaveDetailView();
      return;
    }
    elements.screenTarget.textContent = `→#${row.cc_code}`;
    elements.screenRows.classList.add("hidden");
    elements.detailView.classList.remove("hidden");
    elements.detailView.dataset.cc = String(row.cc_code);
    renderDetailHeader(row);
    renderDetailSubmode(row);
  }

  function renderDetailHeader(row) {
    elements.detailHeader.replaceChildren();
    const tag = document.createElement("span");
    tag.className = "detail-tag";
    tag.textContent = `#${row.cc_code}`;
    const state = document.createElement("span");
    state.className = "detail-state";
    state.textContent = stateMarker(row.state);
    const title = document.createElement("span");
    title.className = "detail-title";
    title.textContent = row.summary || row.state;
    elements.detailHeader.append(tag, state, title);
  }

  function setDnd(on) {
    model.dnd = !!on;
    if (elements.dndIndicator) elements.dndIndicator.classList.toggle("hidden", !model.dnd);
    log(model.dnd ? "已开启 DND（不再蜂鸣/闪屏，但状态照常更新）。" : "已退出 DND。");
    if (!model.dnd && model.pendingAttentions.length) {
      // 退出 DND：按 cc_code 顺序逐个触发报警
      const codes = model.pendingAttentions.slice();
      model.pendingAttentions = [];
      codes.forEach((code, i) => {
        setTimeout(() => {
          const row = model.rows.find(r => r.cc_code === code);
          if (row && row.priority === "high" && String(row.state).startsWith("AWAITING")) {
            alertAttention();
            log(`补播 DND 期间缓存的 #${code} 提醒。`, "ok");
          }
        }, i * 400);
      });
    }
  }

  function setDetailSubmode(mode) {
    const map = {
      list: elements.detailList,
      recording: elements.detailRecording,
      transcribing: elements.detailTranscribing,
      ready: elements.detailReady,
      result: elements.detailResult,
    };
    model.detailSubmode = mode;
    Object.entries(map).forEach(([k, el]) => {
      if (!el) return;
      el.classList.toggle("hidden", k !== mode);
    });
  }

  function renderDetailSubmode(row) {
    if (model.detailSubmode === "recording") {
      if (elements.recTargetCode) elements.recTargetCode.textContent = String(row.cc_code);
      if (elements.recBarFill) elements.recBarFill.style.width = "0%";
      if (elements.recTimer) elements.recTimer.textContent = `0.0s / ${(model.recordingMaxMs/1000).toFixed(1)}s`;
      setDetailSubmode("recording");
      return;
    }
    if (model.detailSubmode === "transcribing") {
      if (elements.trTargetCode) elements.trTargetCode.textContent = String(row.cc_code);
      setDetailSubmode("transcribing");
      return;
    }
    if (model.detailSubmode === "ready") {
      if (elements.readyTargetCode) elements.readyTargetCode.textContent = String(row.cc_code);
      const text = (elements.draftText.value || "").trim();
      if (elements.readyText) elements.readyText.textContent = text || "—";
      setDetailSubmode("ready");
      return;
    }
    if (model.detailSubmode === "result") {
      const ok = model._lastSendOk !== false;
      if (elements.resultHead) {
        elements.resultHead.textContent = ok ? "✓ 已发送" : "✗ 发送失败";
        elements.resultHead.classList.toggle("ok", ok);
        elements.resultHead.classList.toggle("err", !ok);
      }
      if (elements.resultText) {
        elements.resultText.textContent = ok ? (elements.draftText.value || "") : (model._lastSendError || "未知错误");
      }
      setDetailSubmode("result");
      return;
    }
    // 默认 list 子视图
    const hist = (model.detailHistory[row.cc_code] || []).slice().reverse();
    elements.detailRows.replaceChildren();
    if (!hist.length) {
      const empty = document.createElement("p");
      empty.className = "detail-empty";
      empty.textContent = "无历史记录";
      elements.detailRows.append(empty);
    } else {
      hist.forEach((h, i) => {
        const line = document.createElement("div");
        line.className = "detail-row";
        if (i === 0) line.classList.add("latest");
        const stamp = document.createElement("span");
        stamp.className = "detail-stamp";
        const dt = new Date(h.ts * 1000);
        stamp.textContent = `${String(dt.getHours()).padStart(2,"0")}:${String(dt.getMinutes()).padStart(2,"0")}`;
        const ic = document.createElement("span");
        ic.className = "detail-icon";
        ic.textContent = stateMarker(h.state);
        const txt = document.createElement("span");
        txt.className = "detail-text";
        txt.textContent = h.summary || h.state;
        line.append(stamp, ic, txt);
        elements.detailRows.append(line);
      });
    }
    const maxScroll = Math.max(0, hist.length - 5);
    if (model.detailScroll > maxScroll) model.detailScroll = maxScroll;
    elements.detailRows.style.transform = `translateY(${-model.detailScroll * 11}px)`;
    if (elements.detailScrollHint) {
      elements.detailScrollHint.textContent = hist.length > 5
        ? `第 ${model.detailScroll + 1} / ${hist.length} 行 · 短按滚 · 三连击返回`
        : `${hist.length} 条 · 三连击返回`;
    }
  }



  function scrollSelectedIntoView() {
    if (model.selectedCode === null) return;
    const node = elements.screenRows.querySelector(`.screen-row[data-cc="${model.selectedCode}"]`);
    if (node) node.scrollIntoView({ block: "nearest", inline: "nearest" });
  }

  function renderPicker() {
    elements.pickerList.replaceChildren();
    const rows = model.rows.slice().sort((a, b) => a.cc_code - b.cc_code);
    rows.forEach((row, index) => {
      const li = document.createElement("li");
      if (index === model.pickerCursor) li.classList.add("cursor");
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = `#${row.cc_code}`;
      const state = document.createElement("span");
      state.textContent = stateMarker(row.state);
      const summary = document.createElement("span");
      summary.className = "summary";
      summary.textContent = row.summary || row.state;
      li.append(badge, state, summary);
      elements.pickerList.append(li);
    });
  }

  function openTargetPicker() {
    if (!model.rows.length) return;
    model.pickerOpen = true;
    model.pickerCursor = Math.max(0, model.rows.findIndex((r) => r.cc_code === model.selectedCode));
    elements.targetPicker.classList.remove("hidden");
    renderPicker();
    log("已打开目标选择（↑↓/数字键/Enter）。");
  }

  function closeTargetPicker() {
    if (!model.pickerOpen) return;
    model.pickerOpen = false;
    elements.targetPicker.classList.add("hidden");
  }

  function pickerMove(delta) {
    if (!model.rows.length) return;
    model.pickerCursor = (model.pickerCursor + delta + model.rows.length) % model.rows.length;
    renderPicker();
  }

  function pickerConfirm() {
    const row = model.rows[model.pickerCursor];
    if (!row) return;
    model.selectedCode = row.cc_code;
    closeTargetPicker();
    render();
    log(`已切换目标到 #${model.selectedCode}。`);
  }

  function send(socket, message) {
    if (socket !== model.socket || socket.readyState !== WebSocket.OPEN) {
      log("网关未连接，无法发送。", "error");
      return false;
    }
    socket.send(JSON.stringify({ version: PROTOCOL_VERSION, ...message }));
    return true;
  }

  function connect() {
    const deviceId = elements.deviceId.value.trim();
    if (!deviceId) {
      log("请输入设备 ID。", "error");
      elements.deviceId.focus();
      return;
    }
    clearTimeout(model.reconnectTimer);
    model.reconnectTimer = null;
    if (model.socket) {
      model.socket._manualClose = true;
      model.socket.close();
    }
    setConnected(false, "连接中");
    elements.connectButton.disabled = true;
    const socket = new WebSocket(wsUrl());
    model.socket = socket;
    socket.addEventListener("open", () => {
      if (socket !== model.socket) return;
      const token = readToken();
      if (token) {
        send(socket, { type: "device.hello", device_id: deviceId, token });
        log("使用已保存 token 连接设备。");
      } else {
        const code = elements.pairingCode.value.trim();
        if (!/^\d{6}$/.test(code)) {
          log("请输入网关终端显示的 6 位配对码。", "error");
          socket._manualClose = true;
          socket.close();
          return;
        }
        send(socket, { type: "pair.complete", device_id: deviceId, code });
        log("发送配对请求。");
      }
    });
    socket.addEventListener("message", ({ data }) => {
      if (socket !== model.socket) return;
      try { handleMessage(JSON.parse(data), socket); }
      catch (_) { log("收到无法解析的网关消息。", "error"); }
    });
    socket.addEventListener("close", () => {
      if (socket !== model.socket) return;
      elements.connectButton.disabled = false;
      const manuallyClosed = socket._manualClose;
      model.socket = null;
      if (model.connected && !manuallyClosed) log("Gateway 已断开，等待重连。", "error");
      setConnected(false, "已断开");
      if (!manuallyClosed) scheduleReconnect();
    });
    socket.addEventListener("error", () => {
      if (socket === model.socket) log("WebSocket 连接错误。", "error");
    });
  }

  function scheduleReconnect() {
    if (!readToken() || model.reconnectTimer) return;
    const delay = model.reconnectDelay;
    model.reconnectDelay = Math.min(model.reconnectDelay * 2, 60000);
    model.reconnectTimer = setTimeout(() => {
      model.reconnectTimer = null;
      connect();
    }, delay);
  }

  function handleMessage(message, socket) {
    if (message.type === "pair.complete" && message.ok) {
      saveToken(message.token);
      log("配对成功，正在认证设备。", "ok");
      send(socket, { type: "device.hello", device_id: elements.deviceId.value.trim(), token: message.token });
      return;
    }
    if (message.type === "device.ready") {
      model.reconnectDelay = 1000;
      elements.connectButton.disabled = false;
      setConnected(true, "已连接");
      log("设备认证成功。", "ok");
      return;
    }
    if (message.type === "cc.snapshot") {
      model.revision = message.revision;
      model.rows = Array.isArray(message.sessions) ? message.sessions : [];
      sortRows();
      selectValidTarget();
      model.detailHistory = {};
      for (const s of model.rows) {
        model.detailHistory[s.cc_code] = [{ ts: s.ts || Date.now()/1000, state: s.state, summary: s.summary || "", priority: s.priority || "normal" }];
      }
      render();
      log(`同步 ${model.rows.length} 个 CC 状态。`, "ok");
      return;
    }
    if (message.type === "cc.state") {
      if (message.revision <= model.revision) return;
      const index = model.rows.findIndex((row) => row.cc_code === message.cc_code);
      if (index === -1) model.rows.push(message);
      else model.rows[index] = message;
      model.revision = message.revision;
      sortRows();
      selectValidTarget();
      elements.nextButton.disabled = false;
      elements.recordButton.disabled = false;
      const hist = model.detailHistory[message.cc_code] || [];
      hist.push({ ts: message.ts || Date.now()/1000, state: message.state, summary: message.summary || "", priority: message.priority || "normal" });
      if (hist.length > 16) hist.shift();
      model.detailHistory[message.cc_code] = hist;
      render();
      log(`#${message.cc_code} -> ${message.state}: ${message.summary || ""}`);
      if (message.priority === "high" && String(message.state).startsWith("AWAITING")) {
        if (model.dnd) {
          if (!model.pendingAttentions.includes(message.cc_code)) model.pendingAttentions.push(message.cc_code);
          log(`DND 模式：#${message.cc_code} 提醒已缓存。`);
        } else {
          alertAttention();
        }
      }
      return;
    }
    if (message.type === "message.ack") {
      model.awaitingAck = false;
      elements.sendButton.disabled = false;
      if (message.ok) {
        log(`已发送至 #${message.cc_code}。`, "ok");
        beep("send");
        finishRecordingUI("sent", `已发送至 #${message.cc_code}（${message.text || ""}）`);
        model._lastSendOk = true;
        model._lastSendError = null;
        // 直接更新屏幕 result 视图内容
        if (elements.resultHead) {
          elements.resultHead.textContent = "✓ 已发送";
          elements.resultHead.classList.add("ok");
          elements.resultHead.classList.remove("err");
        }
        if (elements.resultText) elements.resultText.textContent = message.text || elements.draftText.value || "";
        setDetailSubmode("result");
        setTimeout(() => {
          closeTranscript();
          if (model.viewMode !== "detail") enterDetailView();
        }, 1500);
      } else {
        log(`发送失败：${message.error || "未知错误"}。草稿已保留。`, "error");
        beep("cancel");
        setRecordingUI("transcribing", `发送失败：${message.error || ""}，三连击取消`);
        model._lastSendOk = false;
        model._lastSendError = message.error || "未知错误";
        if (elements.resultHead) {
          elements.resultHead.textContent = "✗ 发送失败";
          elements.resultHead.classList.add("err");
          elements.resultHead.classList.remove("ok");
        }
        if (elements.resultText) elements.resultText.textContent = message.error || "未知错误";
        setDetailSubmode("result");
      }
      return;
    }
    if (message.type === "pong") return;
    if (message.type === "device.error") {
      log(`设备错误：${message.error}。`, "error");
      return;
    }
    log(`收到 ${message.type || "未知"} 消息。`);
  }

  function selectNext(delta = 1) {
    if (!model.rows.length) return;
    const currentIndex = model.rows.findIndex((row) => row.cc_code === model.selectedCode);
    const next = (currentIndex + delta + model.rows.length) % model.rows.length;
    model.selectedCode = model.rows[next].cc_code;
    closeTargetPicker();
    render();
    log(`已选择 #${model.selectedCode}。`);
  }

  /* ===== Recording / Transcribing flow ===== */
  function startRecording() {
    if (!model.connected || model.selectedCode === null) return;
    if (model.recording) return;
    model.recording = true;
    model.recordingStartedAt = performance.now();
    elements.transcriptPanel.classList.remove("hidden");
    elements.transcriptPanel.classList.add("is-recording");
    elements.transcriptPanel.classList.remove("is-transcribing");
    elements.draftTarget.textContent = `-> #${model.selectedCode}`;
    elements.draftText.value = "";
    elements.draftText.disabled = true;
    elements.recordingProgress.classList.remove("done", "cancelled");
    elements.recordingProgressBar.style.width = "0%";
    elements.recordingStatus.classList.remove("transcribing", "sent");
    setRecordingUI("recording", `录音中 #${model.selectedCode} (≤${(model.recordingMaxMs/1000).toFixed(1)}s)`);
    if (model.viewMode !== "detail") enterDetailView();
    setDetailSubmode("recording");
    log(`开始录音（目标 #${model.selectedCode}）。`);
    const tick = () => {
      const elapsed = performance.now() - model.recordingStartedAt;
      const ratio = Math.min(1, elapsed / model.recordingMaxMs);
      elements.recordingProgressBar.style.width = `${(ratio * 100).toFixed(1)}%`;
      if (elements.recBarFill) elements.recBarFill.style.width = `${(ratio * 100).toFixed(1)}%`;
      if (elements.recTimer) elements.recTimer.textContent = `${(elapsed/1000).toFixed(1)}s / ${(model.recordingMaxMs/1000).toFixed(1)}s`;
      if (ratio >= 1) {
        stopRecording();
        return;
      }
      model.recordingInterval = requestAnimationFrame(tick);
    };
    model.recordingInterval = requestAnimationFrame(tick);
  }

  function stopRecording() {
    if (!model.recording) return;
    model.recording = false;
    if (model.recordingInterval) cancelAnimationFrame(model.recordingInterval);
    model.recordingInterval = null;
    const elapsed = performance.now() - model.recordingStartedAt;
    const tooShort = elapsed < 500;
    elements.recordingProgress.classList.add("done");
    elements.transcriptPanel.classList.remove("is-recording");
    if (tooShort) {
      beep("cancel");
      elements.recordingProgress.classList.add("cancelled");
      setRecordingUI("transcribing", "录音太短 (<0.5s)，已取消。请再试一次。");
      log("录音太短，已取消。", "error");
      setTimeout(() => closeTranscript(), 900);
      return;
    }
    setRecordingUI("transcribing", "Whisper 转写中…");
    setDetailSubmode("transcribing");
    log(`录音完成 (${Math.round(elapsed)}ms)，等待 Whisper 转写。`);
    clearTimeout(model.transcribingTimer);
    model.transcribingTimer = setTimeout(() => {
      const draft = elements.draftText.value || "允许";
      elements.draftText.value = draft;
      elements.draftText.disabled = false;
      setRecordingUI("transcribing", `转写就绪，请确认 → #${model.selectedCode}`);
      setDetailSubmode("ready");
      // 同步显示到屏幕（识别结果文本）
      if (elements.readyText) elements.readyText.textContent = draft;
      if (elements.readyTargetCode) elements.readyTargetCode.textContent = String(model.selectedCode);
      elements.draftText.focus();
      elements.sendButton.focus();
    }, 700);
  }

  function setRecordingUI(kind, text) {
    elements.recordingStatus.classList.remove("transcribing", "sent");
    if (kind === "transcribing") elements.recordingStatus.classList.add("transcribing");
    else if (kind === "sent") elements.recordingStatus.classList.add("sent");
    elements.recordingStatusText.textContent = text;
  }

  function finishRecordingUI(kind, text) {
    setRecordingUI(kind, text);
  }

  function closeTranscript() {
    cancelRecording();
    elements.transcriptPanel.classList.remove("is-recording", "is-transcribing");
    elements.transcriptPanel.classList.add("hidden");
    elements.draftText.value = "";
    elements.draftText.disabled = false;
    elements.recordingProgressBar.style.width = "0%";
    elements.recordingProgress.classList.remove("done", "cancelled");
    model.awaitingAck = false;
    elements.sendButton.disabled = false;
    if (model.viewMode === "detail") model.detailSubmode = "list";
  }

  function cancelRecording() {
    if (model.recording) {
      model.recording = false;
      if (model.recordingInterval) cancelAnimationFrame(model.recordingInterval);
    }
    clearTimeout(model.transcribingTimer);
  }

  function openTranscript() {
    if (model.selectedCode === null || !model.connected) return;
    startRecording();
  }

  function rerecord() {
    if (elements.transcriptPanel.classList.contains("hidden")) return;
    log("手动重录。");
    startRecording();
  }

  function retarget() {
    closeTranscript();
    openTargetPicker();
  }

  function sendDraft() {
    const text = elements.draftText.value.trim();
    if (!text) {
      log("请输入模拟转写文本。", "error");
      elements.draftText.focus();
      return;
    }
    if (model.awaitingAck) return;
    model.awaitingAck = send(model.socket, { type: "message.send", cc_code: model.selectedCode, text });
    elements.sendButton.disabled = model.awaitingAck;
    if (model.awaitingAck) setRecordingUI("transcribing", `已发送至 #${model.selectedCode}，等待 ack…`);
  }

  /* ===== Inject panel ===== */
  function openDrawer() {
    model.drawerOpen = true;
    elements.injectDrawer.classList.add("open");
    elements.injectDrawer.setAttribute("aria-hidden", "false");
    elements.injectToggle.setAttribute("aria-expanded", "true");
    populateCcSelector();
  }

  function closeDrawer() {
    model.drawerOpen = false;
    elements.injectDrawer.classList.remove("open");
    elements.injectDrawer.setAttribute("aria-hidden", "true");
    elements.injectToggle.setAttribute("aria-expanded", "false");
  }

  function populateCcSelector() {
    const current = elements.injectCc.value || "1";
    elements.injectCc.replaceChildren();
    for (let i = 1; i <= 8; i++) {
      const opt = document.createElement("option");
      opt.value = String(i);
      opt.textContent = `#${i}`;
      elements.injectCc.append(opt);
    }
    elements.injectCc.value = current;
    elements.injectCcPreview.textContent = elements.injectCc.value;
    elements.injectSession.value = readStoredSession(elements.injectCc.value) || `browser-injected-${elements.injectCc.value}`;
  }

  async function injectEvent(payload) {
    try {
      const res = await fetch("/hook", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await res.json().catch(() => ({}));
      log(`注入 ${payload.hook_event_name} -> #${body.cc_code ?? "?"} (${body.state ?? "?"})。`, "ok");
      return body;
    } catch (error) {
      log(`注入失败：${error.message || error}`, "error");
      return null;
    }
  }

  async function resetAllSessions() {
    for (let i = 1; i <= 8; i++) saveStoredSession(i, `browser-injected-${i}`);
    clearStoredSessions();
    log("已清空浏览器注入的 session_id 绑定（重新注入将分配新 cc_code）。", "ok");
  }

  async function injectPreset(presetKey) {
    const preset = INJECT_PRESETS[presetKey];
    if (!preset) return;
    const cc = elements.injectCc.value;
    const session = elements.injectSession.value.trim() || `browser-injected-${cc}`;
    saveStoredSession(cc, session);
    await injectEvent({
      session_id: session,
      hook_event_name: preset.hook_event_name,
      cwd: `/repo/injected/${session}`,
      message: preset.message,
    });
  }

  async function injectCustom(event) {
    event.preventDefault();
    const cc = elements.injectCc.value;
    const session = elements.injectSession.value.trim();
    const hook = elements.injectEvent.value;
    const message = elements.injectMessage.value.trim() || hook;
    if (!session) { log("请填写 session_id。", "error"); return; }
    saveStoredSession(cc, session);
    await injectEvent({ session_id: session, hook_event_name: hook, cwd: `/repo/injected/${session}`, message });
  }

  /* ===== Device button: short press / long press / double click ===== */
  function enterDetailView() {
    if (model.selectedCode === null) return;
    model.viewMode = "detail";
    model.detailCcCode = model.selectedCode;
    model.detailScroll = 0;
    render();
    log(`进入 #${model.detailCcCode} 详情视图。`);
  }

  function detailScrollDown() {
    if (model.viewMode !== "detail") return;
    const hist = (model.detailHistory[model.detailCcCode] || []);
    const maxScroll = Math.max(0, hist.length - 5);
    if (model.detailScroll < maxScroll) {
      model.detailScroll += 1;
      render();
    } else if (!model._bottomWarned) {
      log("已到底部。");
      model._bottomWarned = true;
    }
  }

  function leaveDetailView() {
    if (model.viewMode !== "detail") return;
    model.viewMode = "list";
    model.detailCcCode = null;
    model.detailScroll = 0;
    model._bottomWarned = false;
    model.detailSubmode = "list";
    render();
    log("返回列表视图。");
  }

  function deviceTripleClick() {
    if (model.pickerOpen) { closeTargetPicker(); return; }
    if (!elements.transcriptPanel.classList.contains("hidden")) {
      closeTranscript();
      beep("cancel");
      log("三连击：取消转写面板。", "ok");
      return;
    }
    if (model.viewMode === "detail") {
      leaveDetailView();
      return;
    }
    if (model.drawerOpen) { closeDrawer(); return; }
  }

  function deviceShortPress() {
    if (model.pickerOpen) { pickerMove(1); return; }
    if (model.viewMode === "detail") { detailScrollDown(); return; }
    selectNext(1);
  }

  function deviceLongPress(pressDownAt = 0) {
    if (model.pickerOpen) closeTargetPicker();
    if (model.viewMode === "detail") {
      openTranscript(pressDownAt);
      return;
    }
    enterDetailView();
  }

  function deviceDoubleClick() {
    if (model.pickerOpen) {
      pickerConfirm();
      return;
    }
    openTargetPicker();
  }

  function bindDeviceButtonPress(el) {
    let pressTimer = null;
    let pressStart = 0;
    let longFired = false;
    el.addEventListener("pointerdown", (event) => {
      if (event.button !== undefined && event.button !== 0) return;
      pressStart = performance.now();
      longFired = false;
      pressTimer = setTimeout(() => {
        longFired = true;
        deviceLongPress(pressStart);
      }, 500);
    });
    const release = (event) => {
      if (pressTimer) { clearTimeout(pressTimer); pressTimer = null; }
      if (longFired) {
        if (typeof stopRecording === "function") stopRecording();
        return;
      }
      const now = performance.now();
      const gap1 = now - model.lastClickAt;
      const gap2 = model.lastClickAt - model.lastClickAt2;
      if (model.lastClickAt > 0 && gap1 < 250 && model.lastClickAt2 > 0 && gap2 < 250) {
        model.lastClickAt = 0;
        model.lastClickAt2 = 0;
        // 三连击：撤销前两次单击（恢复状态），再执行三连击动作
        while (model.singlePressStack.length > 0) restoreViewState(model.singlePressStack.pop());
        if (model.singlePressClearTimer) clearTimeout(model.singlePressClearTimer);
        model.singlePressClearTimer = null;
        deviceTripleClick();
        return;
      }
      model.lastClickAt2 = model.lastClickAt;
      model.lastClickAt = now;
      // 单击：保存当前状态到栈后立即执行（不延迟）
      model.singlePressStack.push(captureViewState());
      if (model.singlePressClearTimer) clearTimeout(model.singlePressClearTimer);
      model.singlePressClearTimer = setTimeout(() => {
        model.singlePressStack = [];
        model.singlePressClearTimer = null;
      }, 250);
      deviceShortPress();
    };
    el.addEventListener("pointerup", release);
    el.addEventListener("pointercancel", release);
    el.addEventListener("pointerleave", (e) => { if (e.buttons === 0) release(e); });
  }

  /* ===== Wire up DOM ===== */
  elements.connectForm.addEventListener("submit", (event) => { event.preventDefault(); connect(); });
  elements.nextButton.addEventListener("click", () => selectNext(1));
  elements.recordButton.addEventListener("click", openTranscript);
  bindDeviceButtonPress(elements.deviceButton);
  elements.sendButton.addEventListener("click", sendDraft);
  elements.rerecordButton.addEventListener("click", rerecord);
  elements.retargetButton.addEventListener("click", retarget);
  elements.cancelButton.addEventListener("click", closeTranscript);
  elements.injectToggle.addEventListener("click", () => (model.drawerOpen ? closeDrawer() : openDrawer()));
  elements.injectClose.addEventListener("click", closeDrawer);
  elements.injectReset.addEventListener("click", resetAllSessions);
  elements.injectCc.addEventListener("change", populateCcSelector);
  elements.injectForm.addEventListener("submit", injectCustom);
  elements.injectPresets.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-preset]");
    if (button) injectPreset(button.dataset.preset);
  });

  window.addEventListener("keydown", (event) => {
    const target = event.target;
    const panelOpen = !elements.transcriptPanel.classList.contains("hidden");
    if (target && target.matches && target.matches("input, textarea, select") && !(panelOpen && target === elements.draftText)) return;
    if (model.pickerOpen) {
      if (event.key === "ArrowDown" || event.key === "j") { pickerMove(1); event.preventDefault(); return; }
      if (event.key === "ArrowUp") { pickerMove(-1); event.preventDefault(); return; }
      if (event.key === "Enter") { pickerConfirm(); event.preventDefault(); return; }
      return;
    }
    if (event.key === "f" || event.key === "F") {
      if (model.viewMode === "detail") {
        setDnd(!model.dnd);
        event.preventDefault();
        return;
      }
    }
    if (panelOpen) {
      if (event.key === "Enter" && !event.shiftKey) { sendDraft(); event.preventDefault(); return; }
      if (event.key === "r" || event.key === "R") { rerecord(); event.preventDefault(); return; }
      return;
    }
    if (event.key.toLowerCase() === "j") {
      const now = performance.now();
      const gap1 = now - model.lastClickAt;
      const gap2 = model.lastClickAt - model.lastClickAt2;
      if (model.lastClickAt > 0 && gap1 < 250 && model.lastClickAt2 > 0 && gap2 < 250) {
        model.lastClickAt = 0; model.lastClickAt2 = 0;
        while (model.singlePressStack.length > 0) restoreViewState(model.singlePressStack.pop());
        if (model.singlePressClearTimer) clearTimeout(model.singlePressClearTimer);
        model.singlePressClearTimer = null;
        deviceTripleClick();
        return;
      }
      model.lastClickAt2 = model.lastClickAt;
      model.lastClickAt = now;
      model.singlePressStack.push(captureViewState());
      if (model.singlePressClearTimer) clearTimeout(model.singlePressClearTimer);
      model.singlePressClearTimer = setTimeout(() => {
        model.singlePressStack = [];
        model.singlePressClearTimer = null;
      }, 250);
      if (model.viewMode === "detail") detailScrollDown();
      else selectNext(1);
    }
    else if (event.key.toLowerCase() === "r") {
      if (model.viewMode === "detail") openTranscript();
      else enterDetailView();
    }
  });

  window.addEventListener("beforeunload", () => {
    cancelRecording();
    if (model.socket) {
      model.socket._manualClose = true;
      model.socket.close();
    }
  });

  populateCcSelector();
  render();

  // 自动重连：刷新页面后如果 localStorage 已有 token 且当前没有 socket，直接 connect
  if (readToken() && !model.socket) {
    log("检测到已配对 token，正在自动连接…");
    setTimeout(connect, 200);
  }
})();
