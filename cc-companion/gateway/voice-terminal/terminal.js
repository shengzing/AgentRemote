"use strict";

const PROTOCOL_VERSION = 1;

const elements = {
    status: document.getElementById("status"),
    ccCount: document.getElementById("cc-count"),
    refreshBtn: document.getElementById("refresh-btn"),
    feedback: document.getElementById("feedback"),
    wakeBtn: document.getElementById("wake-btn"),
    ccList: document.getElementById("cc-list"),
    ccRows: document.getElementById("cc-rows"),
    ccEmpty: document.getElementById("cc-empty"),
    textSection: document.getElementById("text-section"),
    selectedTarget: document.getElementById("selected-target"),
    micBtn: document.getElementById("mic-btn"),
    speechStatus: document.getElementById("speech-status"),
    commandInput: document.getElementById("command-input"),
    confirmBtn: document.getElementById("confirm-btn"),
    backBtn: document.getElementById("back-btn"),
    resultSection: document.getElementById("result-section"),
    resultMessage: document.getElementById("result-message"),
    newRoundBtn: document.getElementById("new-round-btn"),
};

const state = {
    ws: null,
    deviceId: null,
    token: null,
    authenticated: false,
    sessions: [],
    selectedCcCode: null,
    phase: "idle",
    draft: "",
    refreshing: false,
    recognition: null,
    isRecording: false,
};

const STATUS_TEXT = {
    idle: "未唤醒",
    connecting: "连接中...",
    connected: "已连接",
    selecting: "选择终端",
    typing: "输入指令",
    confirming: "确认发送",
    sending: "发送中",
    sent: "已发送",
    error: "错误",
};

function setStatus(status) {
    state.phase = status;
    elements.status.textContent = STATUS_TEXT[status] || status;
    elements.status.className = `status ${status}`;
}

function setFeedback(message, type) {
    elements.feedback.textContent = message;
    elements.feedback.className = "feedback " + (type || "info");
}

function showSection(...sections) {
    const all = ["ccList", "textSection", "resultSection"];
    all.forEach((name) => {
        if (sections.includes(name)) {
            elements[name].classList.remove("hidden");
        } else {
            elements[name].classList.add("hidden");
        }
    });
}

function generateDeviceId() {
    const stored = localStorage.getItem("cc-terminal-device-id");
    if (stored) return stored;
    const id = "web-" + crypto.randomUUID().slice(0, 12);
    localStorage.setItem("cc-terminal-device-id", id);
    return id;
}

function getStoredToken() {
    return localStorage.getItem("cc-terminal-token");
}

function storeToken(token) {
    localStorage.setItem("cc-terminal-token", token);
    state.token = token;
}

function connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${protocol}//${window.location.host}/ws`;
    state.ws = new WebSocket(url);
    state.deviceId = generateDeviceId();

    state.ws.onopen = () => {
        setFeedback("已连接网关...", "info");
        sendHello(getStoredToken() || "");
    };

    state.ws.onclose = () => {
        setStatus("idle");
        state.authenticated = false;
        if (state.phase === "sent") {
            // keep success state
        } else {
            setFeedback("连接已断开，点击唤醒重新连接", "error");
        }
        elements.wakeBtn.disabled = false;
        elements.wakeBtn.textContent = "唤醒";
    };

    state.ws.onerror = () => {
        setStatus("error");
        setFeedback("连接网关失败，请确认网关已启动", "error");
    };

    state.ws.onmessage = (event) => {
        try {
            const message = JSON.parse(event.data);
            handleMessage(message);
        } catch (error) {
            console.error("Failed to parse message:", error);
        }
    };
}

function sendHello(token) {
    sendMessage({
        version: PROTOCOL_VERSION,
        type: "device.hello",
        device_id: state.deviceId,
        token: token,
        capabilities: ["input", "display"],
    });
}

function sendMessage(message) {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) {
        state.ws.send(JSON.stringify(message));
    }
}

function handleMessage(message) {
    switch (message.type) {
        case "device.ready":
            state.authenticated = true;
            if (message.token) {
                storeToken(message.token);
            }
            elements.refreshBtn.classList.remove("hidden");
            if (!state.refreshing) {
                setStatus("selecting");
                setFeedback("认证成功，已接入网关", "success");
            showSection("ccList");
                renderCcRows();
            }
            break;
        case "cc.snapshot":
            state.sessions = message.sessions || [];
            renderCcRows();
            if (state.refreshing) {
                state.refreshing = false;
                elements.refreshBtn.disabled = false;
                setFeedback("终端列表已刷新", "success");
            }
            break;
        case "cc.state":
            handleStateDelta(message);
            break;
        case "message.ack":
            handleAck(message);
            break;
        case "device.error":
            showError(message.error);
            break;
    }
}

function handleStateDelta(message) {
    const index = state.sessions.findIndex((s) => s.cc_code === message.cc_code);
    if (index >= 0) {
        state.sessions[index] = {
            cc_code: message.cc_code,
            state: message.state,
            summary: message.summary,
            priority: message.priority,
            ts: message.ts,
        };
    } else {
        state.sessions.push({
            cc_code: message.cc_code,
            state: message.state,
            summary: message.summary,
            priority: message.priority,
            ts: message.ts,
        });
    }
    renderCcRows();
}

function renderCcRows() {
    if (state.sessions.length === 0) {
        elements.ccEmpty.classList.remove("hidden");
        elements.ccRows.innerHTML = "";
    } else {
        elements.ccEmpty.classList.add("hidden");
    }
    elements.ccRows.innerHTML = "";
    state.sessions
        .sort((a, b) => a.cc_code - b.cc_code)
        .forEach((session) => {
            const row = document.createElement("div");
            row.className = `cc-row${session.cc_code === state.selectedCcCode ? " selected" : ""}`;
            row.innerHTML = `
                <span class="cc-code">#${session.cc_code}</span>
                <span class="cc-state ${session.state}">${session.state}</span>
                <span class="cc-summary">${escapeHtml(session.summary)}</span>
            `;
            row.addEventListener("click", () => selectCc(session.cc_code));
            elements.ccRows.appendChild(row);
        });
}

function selectCc(ccCode) {
    if (state.phase !== "selecting") return;
    state.selectedCcCode = ccCode;

    sendMessage({
        version: PROTOCOL_VERSION,
        type: "cc.select",
        cc_code: ccCode,
    });

    elements.selectedTarget.textContent = `目标: #${ccCode}`;
    showSection("textSection");
    setStatus("confirming");
    elements.commandInput.focus();
    updateConfirmButton();
}

function updateConfirmButton() {
    const btn = elements.confirmBtn;
    btn.disabled = false;
    btn.className = "confirm-btn";

    if (elements.commandInput.value.trim()) {
        btn.textContent = "发送";
        btn.classList.add("sending");
    } else {
        btn.textContent = "输入内容后发送";
        btn.disabled = true;
    }
}

// -- Browser Speech Recognition (HTML terminal only) --

function toggleSpeechRecognition() {
    if (state.isRecording) {
        stopSpeechRecognition();
    } else {
        startSpeechRecognition();
    }
}

function startSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        setFeedback("当前浏览器不支持语音识别，请使用 Chrome", "error");
        return;
    }

    state.recognition = new SpeechRecognition();
    state.recognition.lang = "zh-CN";
    state.recognition.continuous = true;
    state.recognition.interimResults = true;

    state.recognition.onresult = (event) => {
        let transcript = "";
        for (let i = 0; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
        }
        elements.commandInput.value = transcript;
        updateConfirmButton();
    };

    state.recognition.onerror = (event) => {
        if (event.error !== "aborted" && event.error !== "no-speech") {
            setFeedback(`语音识别错误: ${event.error}`, "error");
        }
    };

    state.recognition.onend = () => {
        if (state.isRecording) {
            state.recognition.start();
        }
    };

    state.isRecording = true;
    elements.micBtn.classList.add("recording");
    elements.speechStatus.classList.remove("hidden");
    elements.commandInput.placeholder = "正在聆听，请说话...";
    state.recognition.start();
    setFeedback("语音识别中，点击麦克风停止", "info");
}

function stopSpeechRecognition() {
    if (!state.isRecording) return;
    state.isRecording = false;

    if (state.recognition) {
        state.recognition.stop();
    }
    elements.micBtn.classList.remove("recording");
    elements.speechStatus.classList.add("hidden");
    elements.commandInput.placeholder = "输入要发送到 Claude Code 的指令";
    setFeedback("语音识别已停止，可编辑文本后发送", "info");
    elements.commandInput.focus();
}

function sendMessageToCc() {
    const text = elements.commandInput.value.trim();
    if (!state.selectedCcCode || !text) return;

    if (state.isRecording) {
        stopSpeechRecognition();
    }

    setStatus("sending");
    elements.confirmBtn.disabled = true;

    sendMessage({
        version: PROTOCOL_VERSION,
        type: "message.send",
        cc_code: state.selectedCcCode,
        text: text,
    });
    updateCcCount();
}

function updateCcCount() {
    const count = state.sessions.length;
    if (count > 0) {
        elements.ccCount.classList.remove("hidden");
        elements.ccCount.textContent = count + " 个终端";
    } else {
        elements.ccCount.classList.add("hidden");
    }
}

function requestSnapshot() {
    if (!state.authenticated || !state.token) return;
    state.refreshing = true;
    setFeedback("正在刷新终端列表...", "info");
    elements.refreshBtn.disabled = true;
    sendHello(state.token);
    setTimeout(() => {
        if (state.refreshing) {
            state.refreshing = false;
            elements.refreshBtn.disabled = false;
            setFeedback("刷新超时，请重试", "error");
        }
    }, 5000);
}

function handleAck(message) {
    if (message.ok) {
        setFeedback(`已发送到 #${message.cc_code}`, "success");
    } else {
        setFeedback(`发送失败: ${message.error || "未知错误"}`, "error");
    }
    setStatus(message.ok ? "sent" : "error");
    setTimeout(() => {
        startNewRound();
    }, message.ok ? 1200 : 2500);
}

function showError(message) {
    elements.resultMessage.textContent = message;
    elements.resultMessage.className = "error";
    setStatus("error");
    showSection("resultSection");
}

function startNewRound() {
    if (state.isRecording) {
        stopSpeechRecognition();
    }
    state.selectedCcCode = null;
    elements.commandInput.value = "";
    elements.selectedTarget.textContent = "";
    setStatus("selecting");
    showSection("ccList");
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
}

elements.wakeBtn.addEventListener("click", () => {
    if (state.phase === "idle" || state.phase === "error") {
        elements.wakeBtn.disabled = true;
        elements.wakeBtn.textContent = "已唤醒";
        setStatus("connecting");
        setFeedback("正在连接网关...", "info");
        connectWebSocket();
    }
});

elements.wakeBtn.addEventListener("dblclick", () => {
    elements.wakeBtn.click();
});

document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.ws && state.ws.readyState === WebSocket.OPEN) {
        if (!state.authenticated) {
            const token = getStoredToken();
            if (token) {
                sendHello(token);
            }
        }
    }
});

elements.commandInput.addEventListener("input", updateConfirmButton);

elements.commandInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        if (elements.commandInput.value.trim()) {
            sendMessageToCc();
        }
    }
});

elements.confirmBtn.addEventListener("click", sendMessageToCc);

elements.backBtn.addEventListener("click", startNewRound);

elements.newRoundBtn.addEventListener("click", startNewRound);

elements.micBtn.addEventListener("click", toggleSpeechRecognition);

elements.refreshBtn.addEventListener("click", requestSnapshot);
