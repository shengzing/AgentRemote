"use strict";

const PROTOCOL_VERSION = 1;
const LONG_PRESS_DELAY = 600;

const elements = {
    screenTitle: document.getElementById("screen-title"),
    screenBody: document.getElementById("screen-body"),
    screenFooter: document.getElementById("screen-footer"),
    btnA: document.getElementById("m5-btn-a"),
    btnB: document.getElementById("m5-btn-b"),
    stateLabel: document.getElementById("state-label"),
    feedback: document.getElementById("feedback"),
};

const state = {
    phase: "IDLE",
    ws: null,
    deviceId: null,
    token: null,
    authenticated: false,
    sessions: [],
    selectedIndex: 0,
    recognition: null,
    isRecording: false,
    transcript: "",
    recordingSeconds: 0,
    recordingTimer: null,
    pressTimerA: null,
    refreshTimer: null,
};

function setPhase(phase) {
    state.phase = phase;
    elements.stateLabel.textContent = phase;
    if (phase === "LIST") {
        startAutoRefresh();
    } else {
        stopAutoRefresh();
    }
    renderScreen();
}

function setFeedback(message) {
    elements.feedback.textContent = message;
}

// -- Screen rendering --

function renderScreen() {
    switch (state.phase) {
        case "IDLE": renderIdle(); break;
        case "LIST": renderList(); break;
        case "IN_TERMINAL": renderTerminal(); break;
        case "RECORDING": renderRecording(); break;
        case "SENT": renderSent(); break;
    }
}

function renderIdle() {
    elements.screenTitle.textContent = "CC Companion";
    elements.screenBody.innerHTML = '<div class="screen-empty">按 A 键唤醒</div>';
    elements.screenFooter.textContent = "";
}

function renderList() {
    elements.screenTitle.textContent = "终端";
    if (state.sessions.length === 0) {
        elements.screenBody.innerHTML = '<div class="screen-empty">暂无终端</div>';
        elements.screenFooter.textContent = "A:切换 B:进入";
        return;
    }
    let html = "";
    state.sessions.forEach((session, index) => {
        const selected = index === state.selectedIndex ? " selected" : "";
        html += `<div class="screen-list-item${selected}">
            <span class="screen-list-code">#${session.cc_code}</span>
            <span class="screen-list-state ${session.state}">${session.state}</span>
            <span class="screen-list-summary">${escapeHtml(session.summary)}</span>
        </div>`;
    });
    elements.screenBody.innerHTML = html;
    elements.screenFooter.textContent = `A:切换 B:进入 (${state.selectedIndex + 1}/${state.sessions.length})`;
}

function renderTerminal() {
    const session = state.sessions[state.selectedIndex];
    if (!session) { setPhase("LIST"); return; }
    elements.screenTitle.textContent = `#${session.cc_code}`;
    elements.screenBody.innerHTML = `
        <div style="padding:12px 0;text-align:center;">
            <div style="font-size:10px;color:#0f0;margin-bottom:6px;">${session.state}</div>
            <div style="font-size:8px;color:#080;margin-bottom:16px;">${escapeHtml(session.summary)}</div>
            <div style="font-size:8px;color:#0a0;">A长按:录音</div>
            <div style="font-size:8px;color:#0a0;">B:返回列表</div>
        </div>
    `;
    elements.screenFooter.textContent = "";
}

function renderRecording() {
    const session = state.sessions[state.selectedIndex];
    elements.screenTitle.textContent = `REC → #${session ? session.cc_code : "?"}`;
    elements.screenBody.innerHTML = `
        <div class="screen-recording">
            <div class="recording-dot"></div>
            <div class="recording-timer">${state.recordingSeconds}s</div>
            ${state.transcript ? `<div style="font-size:8px;color:#fa4;padding:0 6px;text-align:center;max-height:40px;overflow:hidden;">${escapeHtml(state.transcript)}</div>` : ""}
            <div class="recording-text">A:发送 B:取消</div>
        </div>
    `;
    elements.screenFooter.textContent = "语音识别中...";
}

function renderSent() {
    const session = state.sessions[state.selectedIndex];
    elements.screenTitle.textContent = "已发送";
    elements.screenBody.innerHTML = `
        <div style="padding:16px 0;text-align:center;">
            <div style="font-size:10px;color:#0f0;">OK → #${session ? session.cc_code : "?"}</div>
            <div style="font-size:7px;color:#080;margin-top:4px;padding:0 4px;">${escapeHtml(state.transcript.slice(0, 60))}</div>
        </div>
    `;
    elements.screenFooter.textContent = "返回列表...";
}

// -- Button A: single = navigate/send, long press = record --

elements.btnA.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    elements.btnA.classList.add("pressed");
    state.pressTimerA = setTimeout(() => {
        state.pressTimerA = null;
        handleALongPress();
    }, LONG_PRESS_DELAY);
});

elements.btnA.addEventListener("pointerup", (event) => {
    event.preventDefault();
    elements.btnA.classList.remove("pressed");
    if (state.pressTimerA !== null) {
        clearTimeout(state.pressTimerA);
        state.pressTimerA = null;
        handleASingleClick();
    }
});

elements.btnA.addEventListener("pointerleave", () => {
    elements.btnA.classList.remove("pressed");
    if (state.pressTimerA !== null) {
        clearTimeout(state.pressTimerA);
        state.pressTimerA = null;
    }
});

function handleASingleClick() {
    switch (state.phase) {
        case "IDLE":
            setPhase("LIST");
            connectWebSocket();
            setFeedback("已唤醒，连接网关...");
            break;
        case "LIST":
            if (state.sessions.length > 0) {
                state.selectedIndex = (state.selectedIndex + 1) % state.sessions.length;
                renderList();
            }
            break;
        case "RECORDING":
            stopRecordingAndSend();
            break;
    }
}

function handleALongPress() {
    if (state.phase === "IN_TERMINAL") {
        startRecording();
    }
}

// -- Button B: enter/back/cancel --

elements.btnB.addEventListener("click", () => {
    switch (state.phase) {
        case "LIST":
            if (state.sessions.length > 0) {
                setPhase("IN_TERMINAL");
                setFeedback(`进入 #${state.sessions[state.selectedIndex].cc_code}`);
            }
            break;
        case "IN_TERMINAL":
            setPhase("LIST");
            setFeedback("返回列表");
            break;
        case "RECORDING":
            cancelRecording();
            break;
    }
});

// -- Recording with browser Speech Recognition --

function startRecording() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
        setFeedback("浏览器不支持语音识别，使用 Chrome");
        return;
    }

    state.isRecording = true;
    state.transcript = "";
    state.recordingSeconds = 0;
    setPhase("RECORDING");
    setFeedback("录音中...");

    state.recognition = new SpeechRecognition();
    state.recognition.lang = "zh-CN";
    state.recognition.continuous = true;
    state.recognition.interimResults = true;

    state.recognition.onresult = (event) => {
        let transcript = "";
        for (let i = 0; i < event.results.length; i++) {
            transcript += event.results[i][0].transcript;
        }
        state.transcript = transcript;
        renderRecording();
    };

    state.recognition.onerror = (event) => {
        if (event.error !== "aborted" && event.error !== "no-speech") {
            setFeedback(`语音错误: ${event.error}`);
        }
    };

    state.recognition.onend = () => {
        if (state.isRecording) {
            state.recognition.start();
        }
    };

    state.recognition.start();

    state.recordingTimer = setInterval(() => {
        state.recordingSeconds++;
        if (state.recordingSeconds >= 15) {
            stopRecordingAndSend();
        } else {
            renderRecording();
        }
    }, 1000);
}

function stopRecordingAndSend() {
    if (!state.isRecording) return;
    state.isRecording = false;

    if (state.recognition) {
        state.recognition.stop();
    }
    clearInterval(state.recordingTimer);
    state.recordingTimer = null;

    if (!state.transcript.trim()) {
        setFeedback("没有识别到语音");
        setPhase("IN_TERMINAL");
        return;
    }

    sendMessage();
}

function cancelRecording() {
    if (!state.isRecording) return;
    state.isRecording = false;

    if (state.recognition) {
        state.recognition.stop();
    }
    clearInterval(state.recordingTimer);
    state.recordingTimer = null;
    state.transcript = "";
    setPhase("IN_TERMINAL");
    setFeedback("已取消");
}

function sendMessage() {
    const session = state.sessions[state.selectedIndex];
    if (!session) { setPhase("LIST"); return; }

    if (state.ws && state.ws.readyState === WebSocket.OPEN && state.authenticated) {
        state.ws.send(JSON.stringify({
            version: PROTOCOL_VERSION,
            type: "message.send",
            cc_code: session.cc_code,
            text: state.transcript,
        }));
        setPhase("SENT");
        setFeedback(`发送到 #${session.cc_code}`);
        setTimeout(() => setPhase("LIST"), 2000);
    } else {
        setFeedback("未连接网关");
        setPhase("IN_TERMINAL");
    }
}

// -- WebSocket --

function generateDeviceId() {
    const stored = localStorage.getItem("m5-sim-device-id");
    if (stored) return stored;
    const id = "m5-sim-" + crypto.randomUUID().slice(0, 8);
    localStorage.setItem("m5-sim-device-id", id);
    return id;
}

function connectWebSocket() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN) return;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    state.ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
    state.deviceId = generateDeviceId();

    state.ws.onopen = () => {
        sendHello(localStorage.getItem("m5-sim-token") || "");
    };

    state.ws.onmessage = (event) => {
        const message = JSON.parse(event.data);
        handleMessage(message);
    };

    state.ws.onclose = () => {
        state.authenticated = false;
        if (state.phase !== "IDLE") {
            setFeedback("连接断开");
        }
    };
}

function sendHello(token) {
    state.ws.send(JSON.stringify({
        version: PROTOCOL_VERSION,
        type: "device.hello",
        device_id: state.deviceId,
        token: token,
        capabilities: ["input", "display", "audio", "select"],
    }));
}

function handleMessage(message) {
    switch (message.type) {
        case "device.ready":
            state.authenticated = true;
            if (message.token) {
                localStorage.setItem("m5-sim-token", message.token);
            }
            setFeedback("已连接网关");
            break;
        case "cc.snapshot":
            state.sessions = message.sessions || [];
            if (state.selectedIndex >= state.sessions.length) {
                state.selectedIndex = Math.max(0, state.sessions.length - 1);
            }
            renderScreen();
            break;
        case "cc.state":
            handleStateDelta(message);
            break;
        case "message.ack":
            if (message.ok) {
                setFeedback(`发送成功: ${message.text}`);
            } else {
                setFeedback(`发送失败: ${message.error}`);
                setPhase("IN_TERMINAL");
            }
            break;
        case "device.error":
            setFeedback(`错误: ${message.error}`);
            break;
    }
}

function handleStateDelta(message) {
    const index = state.sessions.findIndex((s) => s.cc_code === message.cc_code);
    if (index >= 0) {
        state.sessions[index] = message;
    } else {
        state.sessions.push(message);
    }
    if (state.phase === "LIST") {
        renderList();
    }
}

function startAutoRefresh() {
    if (state.refreshTimer) return;
    requestSnapshot();
    state.refreshTimer = setInterval(requestSnapshot, 5000);
}

function stopAutoRefresh() {
    if (state.refreshTimer) {
        clearInterval(state.refreshTimer);
        state.refreshTimer = null;
    }
}

function requestSnapshot() {
    if (state.ws && state.ws.readyState === WebSocket.OPEN && state.authenticated && state.token) {
        sendHello(state.token);
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
}
