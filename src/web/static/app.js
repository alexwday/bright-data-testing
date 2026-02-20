/* ══════════════════════════════════════════════════════════════════════════
   BD Research Agent — Chat Client
   ══════════════════════════════════════════════════════════════════════════ */

const state = {
    chatId: null,
    pollTimer: null,
    pollInFlight: false,
    messageOffset: 0,
    prompts: [],
    isProcessing: false,
    // Progress card tracking
    progressCard: null,   // current progress card DOM element
    progressSteps: [],    // steps collected for current task
    progressFiles: [],    // files collected for current task
    progressFileKeys: new Set(), // dedupe files by filename
    processingStartTime: null,  // timestamp when processing began
    elapsedTimer: null,         // interval for updating elapsed time
};

/* ── Init ───────────────────────────────────────────────────────────────── */

async function init() {
    const prompts = await fetch("/api/config/prompts").then(r => r.json());
    state.prompts = prompts;
    renderPromptButtons();
    renderWelcomeChips();
    document.getElementById("chat-input").focus();
}

/* ── Prompt Buttons ─────────────────────────────────────────────────────── */

function renderPromptButtons() {
    const container = document.getElementById("prompt-buttons");
    container.innerHTML = "";
    state.prompts.forEach((p, i) => {
        const btn = document.createElement("button");
        btn.className = "prompt-btn";
        btn.textContent = p.label;
        btn.style.animationDelay = `${i * 0.05}s`;
        btn.onclick = () => handlePromptClick(p);
        container.appendChild(btn);
    });
}

function renderWelcomeChips() {
    const container = document.getElementById("welcome-chips");
    if (!container) return;
    container.innerHTML = "";
    state.prompts.forEach(p => {
        const chip = document.createElement("button");
        chip.className = "welcome-chip";
        chip.textContent = p.label;
        chip.onclick = () => handlePromptClick(p);
        container.appendChild(chip);
    });
}

function handlePromptClick(prompt) {
    const input = document.getElementById("chat-input");
    if (prompt.prefill) {
        input.value = prompt.message;
        input.focus();
        autoResize(input);
    } else {
        input.value = prompt.message;
        sendMessage();
    }
}

/* ── Chat ───────────────────────────────────────────────────────────────── */

async function sendMessage() {
    const input = document.getElementById("chat-input");
    const message = input.value.trim();
    if (!message || state.isProcessing) return;

    // Remove welcome screen
    const welcome = document.getElementById("welcome");
    if (welcome) welcome.remove();

    // Show user message
    appendUserMessage(message);

    input.value = "";
    autoResize(input);
    setProcessing(true);

    // Create progress card for this task
    createProgressCard();

    // Send to backend
    const body = { message };
    if (state.chatId) body.chat_id = state.chatId;

    try {
        const resp = await fetch("/api/chat", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(body),
        });
        if (!resp.ok) {
            const err = await resp.json();
            removeProgressCard();
            appendSystemMessage(`Error: ${err.detail || "Request failed"}`);
            setProcessing(false);
            return;
        }
        const data = await resp.json();
        state.chatId = data.chat_id;
        state.messageOffset += 1; // Skip the user message we already rendered

        // Show status section
        document.getElementById("status-section").style.display = "";

        startPolling();
    } catch (err) {
        console.error("[send error]", err);
        removeProgressCard();
        appendSystemMessage(`Network error: ${err.message}`);
        setProcessing(false);
    }
}

function startPolling() {
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollInFlight = false;
    pollChat();
    state.pollTimer = setInterval(pollChat, 800);
}

async function pollChat() {
    if (!state.chatId) return;
    if (state.pollInFlight) return;
    state.pollInFlight = true;

    try {
        const resp = await fetch(`/api/chat/${state.chatId}?since=${state.messageOffset}`);
        if (!resp.ok) return;
        const data = await resp.json();

        const messages = data.messages;
        const isDone = !data.is_processing;

        if (isDone && messages.length > 0) {
            // When done, the last assistant message is the final response.
            // Route everything before it through the progress card, then
            // render final response and then finalize the card.
            const lastMsg = messages[messages.length - 1];
            const isLastAssistant = lastMsg.role === "assistant";

            const progressMsgs = isLastAssistant ? messages.slice(0, -1) : messages;
            progressMsgs.forEach(msg => handleIncomingMessage(msg));

            if (isLastAssistant) {
                appendAssistantMessage(lastMsg.content);
            }

            // Finalize progress card and append file summary after assistant response
            finalizeProgressCard();
            setProcessing(false);

            clearInterval(state.pollTimer);
            state.pollTimer = null;
        } else if (isDone && messages.length === 0) {
            // Processing finished with no new messages
            finalizeProgressCard();
            setProcessing(false);
            clearInterval(state.pollTimer);
            state.pollTimer = null;
        } else {
            // Still processing — update status if no steps yet
            if (messages.length === 0 && state.progressCard && state.progressSteps.length === 0) {
                const statusText = state.progressCard.querySelector(".progress-status-text");
                if (statusText) statusText.textContent = "Thinking...";
            }
            messages.forEach(msg => handleIncomingMessage(msg));
        }

        state.messageOffset = data.total_messages;
    } catch (err) {
        console.error("[poll error]", err);
    } finally {
        state.pollInFlight = false;
    }
}

function handleIncomingMessage(msg) {
    console.log("[msg]", msg.role, msg.tool_name || msg.filename || (msg.content || "").substring(0, 40));
    switch (msg.role) {
        case "user":
            // Already rendered locally, skip
            break;
        case "tool_activity":
            addProgressStep(msg);
            break;
        case "file":
            addProgressFile(msg);
            break;
        case "system":
            addProgressWarning(msg);
            break;
        case "assistant":
            if (state.isProcessing && state.progressCard) {
                // Intermediate assistant message during processing — add as a thinking step
                addProgressThinking(msg.content);
            } else {
                // Final response — render below progress card
                appendAssistantMessage(msg.content);
            }
            break;
    }
}

function newChat() {
    state.chatId = null;
    state.messageOffset = 0;
    state.isProcessing = false;
    state.progressCard = null;
    state.progressSteps = [];
    state.progressFiles = [];
    state.progressFileKeys = new Set();
    state.processingStartTime = null;
    state.pollInFlight = false;
    stopElapsedTimer();
    if (state.pollTimer) {
        clearInterval(state.pollTimer);
        state.pollTimer = null;
    }

    const messages = document.getElementById("chat-messages");
    messages.innerHTML = `
        <div class="welcome-message" id="welcome">
            <div class="welcome-icon">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                    <circle cx="11" cy="11" r="8"></circle>
                    <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
                </svg>
            </div>
            <h2>What would you like to research?</h2>
            <p>Search the web, scrape pages, and download documents.<br>Choose a quick action or describe what you need.</p>
            <div class="welcome-chips" id="welcome-chips"></div>
        </div>
    `;
    renderWelcomeChips();

    document.getElementById("status-section").style.display = "none";
    setProcessing(false);
    document.getElementById("chat-input").focus();
}

/* ── Message Rendering ──────────────────────────────────────────────────── */

function appendUserMessage(content) {
    const container = document.getElementById("chat-messages");
    const el = document.createElement("div");
    el.className = "message message-user";
    el.innerHTML = `
        <div class="msg-bubble msg-user">
            <div class="msg-user-content is-collapsed">${renderMarkdown(content)}</div>
            <button class="msg-expand-btn" type="button" hidden>Show more</button>
        </div>
    `;
    container.appendChild(el);

    initUserMessageExpansion(el);
    scrollToBottom();
}

function appendAssistantMessage(content) {
    const container = document.getElementById("chat-messages");
    const el = document.createElement("div");
    el.className = "message message-assistant";
    el.innerHTML = `<div class="msg-bubble msg-assistant">${renderMarkdown(content)}</div>`;
    container.appendChild(el);
    scrollToBottom();
}

function initUserMessageExpansion(messageEl) {
    const contentEl = messageEl.querySelector(".msg-user-content");
    const btnEl = messageEl.querySelector(".msg-expand-btn");
    if (!contentEl || !btnEl) return;

    // Wait for layout so we can determine if content exceeds collapsed max height.
    requestAnimationFrame(() => {
        const overflows = contentEl.scrollHeight > contentEl.clientHeight + 1;
        if (!overflows) {
            contentEl.classList.remove("is-collapsed");
            btnEl.hidden = true;
            return;
        }

        btnEl.hidden = false;
        btnEl.textContent = "Show more";
        btnEl.onclick = (e) => {
            e.preventDefault();
            const expanded = contentEl.classList.toggle("is-expanded");
            if (expanded) {
                contentEl.classList.remove("is-collapsed");
                btnEl.textContent = "Show less";
            } else {
                contentEl.classList.add("is-collapsed");
                btnEl.textContent = "Show more";
                scrollToBottom();
            }
        };
    });
}

function appendSystemMessage(content) {
    const container = document.getElementById("chat-messages");
    const el = document.createElement("div");
    el.className = "message message-system";
    el.innerHTML = `<div class="msg-system">${escapeHtml(content)}</div>`;
    container.appendChild(el);
    scrollToBottom();
}

/* ── Progress Card ──────────────────────────────────────────────────────── */

function createProgressCard() {
    state.progressSteps = [];
    state.progressFiles = [];
    state.progressFileKeys = new Set();
    state.processingStartTime = Date.now();

    const container = document.getElementById("chat-messages");
    const card = document.createElement("div");
    card.className = "message progress-card";
    card.innerHTML = `
        <div class="progress-header" onclick="toggleProgressExpand(this)">
            <div class="progress-status">
                <div class="progress-spinner"></div>
                <span class="progress-status-text">Thinking...</span>
            </div>
            <div class="progress-meta">
                <span class="progress-elapsed"></span>
                <span class="progress-step-count">0 steps</span>
                <svg class="progress-expand-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>
            </div>
        </div>
        <div class="progress-steps-container" hidden>
            <div class="progress-steps-list">
                <div class="progress-empty">Waiting for first tool call…</div>
            </div>
        </div>
        <div class="progress-files-container" hidden></div>
    `;
    container.appendChild(card);
    state.progressCard = card;

    // Start elapsed time updates
    startElapsedTimer();

    console.log("[progress] card created");
    scrollToBottom();
}

function startElapsedTimer() {
    if (state.elapsedTimer) clearInterval(state.elapsedTimer);
    state.elapsedTimer = setInterval(updateElapsedTime, 1000);
    updateElapsedTime(); // immediate first update
}

function stopElapsedTimer() {
    if (state.elapsedTimer) {
        clearInterval(state.elapsedTimer);
        state.elapsedTimer = null;
    }
}

function updateElapsedTime() {
    if (!state.progressCard || !state.processingStartTime) return;
    const elapsed = Math.floor((Date.now() - state.processingStartTime) / 1000);
    const elapsedEl = state.progressCard.querySelector(".progress-elapsed");
    if (elapsedEl) {
        if (elapsed < 60) {
            elapsedEl.textContent = `${elapsed}s`;
        } else {
            const mins = Math.floor(elapsed / 60);
            const secs = elapsed % 60;
            elapsedEl.textContent = `${mins}m ${secs}s`;
        }
    }
}

function addProgressStep(msg) {
    if (!state.progressCard) { console.warn("[progress] no card, dropping step:", msg.tool_name); return; }

    const name = msg.tool_name || "tool";
    const duration = msg.tool_duration_ms != null ? `${(msg.tool_duration_ms / 1000).toFixed(1)}s` : "";
    const toolType = { search: "search", scrape_page: "scrape", download_file: "download" }[name] || "tool";

    let preview = "";
    if (msg.tool_args) {
        if (name === "search") preview = msg.tool_args.query || "";
        else if (name === "scrape_page") preview = msg.tool_args.url || "";
        else if (name === "download_file") preview = msg.tool_args.filename || msg.tool_args.url || "";
        else preview = JSON.stringify(msg.tool_args);
    }

    const stepData = { name, toolType, preview, duration, msg, timestamp: Date.now() };
    state.progressSteps.push(stepData);

    // Update status line
    const statusLabel = { search: "Searching", scrape_page: "Scraping page", download_file: "Downloading" }[name] || "Processing";
    const statusText = state.progressCard.querySelector(".progress-status-text");
    statusText.textContent = `${statusLabel}: ${truncate(preview, 60)}`;

    // Update step count
    const countEl = state.progressCard.querySelector(".progress-step-count");
    countEl.textContent = `${state.progressSteps.length} step${state.progressSteps.length !== 1 ? "s" : ""}`;

    // Add to expanded list
    const list = state.progressCard.querySelector(".progress-steps-list");
    const emptyState = list.querySelector(".progress-empty");
    if (emptyState) emptyState.remove();
    const stepEl = document.createElement("div");
    stepEl.className = `progress-step progress-step-${toolType}`;

    const iconSvg = getToolIconSvg(toolType);
    const chevron = '<svg class="tool-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="9 18 15 12 9 6"></polyline></svg>';

    let resultPreview = "";
    if (msg.tool_result) {
        resultPreview = JSON.stringify(msg.tool_result, null, 2);
        if (resultPreview.length > 2000) {
            resultPreview = resultPreview.substring(0, 2000) + "\n... [truncated]";
        }
    }

    stepEl.innerHTML = `
        <details class="step-details">
            <summary class="step-summary">
                ${chevron}
                <span class="tool-icon ${toolType}">${iconSvg}</span>
                <span class="step-name">${escapeHtml(name)}</span>
                <span class="step-preview">${escapeHtml(truncate(preview, 50))}</span>
                ${duration ? `<span class="step-duration">${duration}</span>` : ""}
            </summary>
            <div class="step-body">
                <div class="step-section">
                    <div class="step-section-label">Arguments</div>
                    <pre class="step-code">${escapeHtml(JSON.stringify(msg.tool_args, null, 2))}</pre>
                </div>
                <div class="step-section">
                    <div class="step-section-label">Result</div>
                    <pre class="step-code">${escapeHtml(resultPreview)}</pre>
                </div>
            </div>
        </details>
    `;
    list.appendChild(stepEl);
    scrollToBottom();
}

function addProgressFile(msg) {
    if (!state.progressCard) { console.warn("[progress] no card, dropping file:", msg.filename); return; }

    const fileKey = (msg.filename || msg.file_path || "").toLowerCase();
    if (fileKey && state.progressFileKeys.has(fileKey)) {
        console.log("[progress] skipping duplicate file:", msg.filename || msg.file_path);
        return;
    }
    if (fileKey) state.progressFileKeys.add(fileKey);

    state.progressFiles.push(msg);

    // Show files container
    const filesContainer = state.progressCard.querySelector(".progress-files-container");
    filesContainer.hidden = false;

    const fileEl = document.createElement("div");
    fileEl.className = "progress-file";
    const size = formatBytes(msg.file_size || 0);
    const ext = (msg.filename || "").split(".").pop().toUpperCase();
    const downloadUrl = `/api/files/download?path=${encodeURIComponent(msg.filename || "")}`;
    fileEl.innerHTML = `
        <div class="file-card-mini">
            <span class="file-card-mini-icon">${ext}</span>
            <a href="${downloadUrl}" class="file-card-mini-name" target="_blank">${escapeHtml(msg.filename || "file")}</a>
            <span class="file-card-mini-size">${size}</span>
        </div>
    `;
    filesContainer.appendChild(fileEl);

    // Update status
    const statusText = state.progressCard.querySelector(".progress-status-text");
    statusText.textContent = `Downloaded: ${msg.filename}`;
    scrollToBottom();
}

function addProgressThinking(content) {
    if (!state.progressCard) return;

    // Update status line with the thinking text
    const statusText = state.progressCard.querySelector(".progress-status-text");
    statusText.textContent = truncate(content, 80);

    // Add as a step in the expanded list
    const list = state.progressCard.querySelector(".progress-steps-list");
    const emptyState = list.querySelector(".progress-empty");
    if (emptyState) emptyState.remove();
    const el = document.createElement("div");
    el.className = "progress-step progress-step-thinking";
    el.innerHTML = `
        <div class="step-thinking">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><path d="M12 16v-4"></path><path d="M12 8h.01"></path></svg>
            <span>${escapeHtml(truncate(content, 200))}</span>
        </div>
    `;
    list.appendChild(el);

    state.progressSteps.push({ name: "thinking", toolType: "thinking", preview: content, duration: "", msg: { content }, timestamp: Date.now() });
}

function addProgressWarning(msg) {
    if (!state.progressCard) {
        appendSystemMessage(msg.content);
        return;
    }

    // Add as a warning step in the progress card
    const list = state.progressCard.querySelector(".progress-steps-list");
    const emptyState = list.querySelector(".progress-empty");
    if (emptyState) emptyState.remove();
    const warnEl = document.createElement("div");
    warnEl.className = "progress-step progress-step-warning";
    warnEl.innerHTML = `
        <div class="step-warning">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
            <span>${escapeHtml(truncate(msg.content, 120))}</span>
        </div>
    `;
    list.appendChild(warnEl);

    state.progressSteps.push({ name: "warning", toolType: "warning", preview: msg.content, duration: "", msg, timestamp: Date.now() });

    // Update status
    const statusText = state.progressCard.querySelector(".progress-status-text");
    statusText.textContent = "Warning: verification issue detected";
}

function finalizeProgressCard() {
    if (!state.progressCard) return;
    stopElapsedTimer();

    // Show final elapsed time
    const totalElapsed = state.processingStartTime
        ? Math.floor((Date.now() - state.processingStartTime) / 1000)
        : 0;
    const elapsedEl = state.progressCard.querySelector(".progress-elapsed");
    if (elapsedEl) {
        if (totalElapsed < 60) {
            elapsedEl.textContent = `${totalElapsed}s`;
        } else {
            const mins = Math.floor(totalElapsed / 60);
            const secs = totalElapsed % 60;
            elapsedEl.textContent = `${mins}m ${secs}s`;
        }
    }

    // Update header to show complete
    const spinner = state.progressCard.querySelector(".progress-spinner");
    if (spinner) {
        spinner.classList.remove("progress-spinner");
        spinner.classList.add("progress-done-icon");
        spinner.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"></polyline></svg>';
    }

    const statusText = state.progressCard.querySelector(".progress-status-text");
    const totalDuration = state.progressSteps.reduce((sum, s) => {
        const ms = s.msg?.tool_duration_ms || 0;
        return sum + ms;
    }, 0);
    const toolSteps = state.progressSteps.filter(s => s.name !== "warning").length;
    const durationStr = totalDuration > 0 ? ` in ${(totalDuration / 1000).toFixed(1)}s` : "";
    statusText.textContent = `Completed ${toolSteps} tool call${toolSteps !== 1 ? "s" : ""}${durationStr}`;

    state.progressCard.classList.add("progress-complete");

    // Render standalone file download cards below the progress card
    if (state.progressFiles.length > 0) {
        const container = document.getElementById("chat-messages");
        const filesEl = document.createElement("div");
        filesEl.className = "message downloads-summary";
        let cardsHtml = state.progressFiles.map(f => {
            const fsize = formatBytes(f.file_size || 0);
            const fext = (f.filename || "").split(".").pop().toUpperCase();
            const furl = `/api/files/download?path=${encodeURIComponent(f.filename || "")}`;
            return `
                <a href="${furl}" class="file-card" target="_blank">
                    <div class="file-icon">${fext}</div>
                    <div class="file-info">
                        <div class="file-name">${escapeHtml(f.filename || "file")}</div>
                        <div class="file-size">${fsize}</div>
                    </div>
                    <div class="file-open-label">Open</div>
                </a>
            `;
        }).join("");
        filesEl.innerHTML = `
            <div class="downloads-label">Downloaded Files</div>
            <div class="downloads-grid">${cardsHtml}</div>
        `;
        container.appendChild(filesEl);
    }

    // Detach from state so next task gets a new card
    state.progressCard = null;
}

function removeProgressCard() {
    stopElapsedTimer();
    if (state.progressCard) {
        state.progressCard.remove();
        state.progressCard = null;
    }
}

function toggleProgressExpand(headerEl) {
    const card = headerEl.closest(".progress-card");
    const stepsContainer = card.querySelector(".progress-steps-container");
    const icon = card.querySelector(".progress-expand-icon");

    if (stepsContainer.hidden) {
        stepsContainer.hidden = false;
        icon.style.transform = "rotate(180deg)";
        card.classList.add("is-expanded");
    } else {
        stepsContainer.hidden = true;
        icon.style.transform = "";
        card.classList.remove("is-expanded");
    }
}

/* ── Processing State ───────────────────────────────────────────────────── */

function setProcessing(processing) {
    state.isProcessing = processing;
    const input = document.getElementById("chat-input");
    const btn = document.getElementById("send-btn");
    const wrapper = document.getElementById("input-wrapper");
    const dot = document.querySelector(".status-dot");
    const statusText = document.querySelector(".status-text");

    input.disabled = processing;
    btn.disabled = processing;

    if (processing) {
        input.placeholder = "Agent is working...";
        wrapper.classList.add("processing");
        if (dot) dot.classList.add("active");
        if (statusText) statusText.textContent = "Processing";
    } else {
        input.placeholder = "Describe your research task...";
        wrapper.classList.remove("processing");
        if (dot) dot.classList.remove("active");
        if (statusText) statusText.textContent = "Idle";
        input.focus();
    }
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function scrollToBottom() {
    const container = document.getElementById("chat-messages");
    container.scrollTop = container.scrollHeight;
}

function handleInputKeydown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function autoResize(el) {
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
}

function escapeHtml(str) {
    if (!str) return "";
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
}

function escapeHtmlAttr(str) {
    return escapeHtml(str).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function sanitizeUrl(url) {
    if (!url) return null;
    const trimmed = url.trim();
    if (!trimmed) return null;

    const lowered = trimmed.toLowerCase();
    if (
        lowered.startsWith("javascript:")
        || lowered.startsWith("data:")
        || lowered.startsWith("vbscript:")
    ) {
        return null;
    }

    const hasAllowedScheme = (
        lowered.startsWith("http://")
        || lowered.startsWith("https://")
        || lowered.startsWith("mailto:")
        || lowered.startsWith("tel:")
    );
    if (hasAllowedScheme) return trimmed;

    // Allow root-relative, dot-relative, anchors, query links, and common bare relative paths.
    if (
        trimmed.startsWith("/")
        || trimmed.startsWith("./")
        || trimmed.startsWith("../")
        || trimmed.startsWith("#")
        || trimmed.startsWith("?")
        || /^[A-Za-z0-9._~!$&'()*+,;=:@%/-]+$/.test(trimmed)
    ) {
        return trimmed;
    }

    return null;
}

function truncate(str, len) {
    if (!str) return "";
    return str.length > len ? str.substring(0, len) + "..." : str;
}

function formatBytes(bytes) {
    if (bytes === 0) return "0 B";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + " " + sizes[i];
}

function renderMarkdown(text) {
    if (!text) return "";
    const codeMap = new Map();
    const withCodeTokens = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_, _lang, code) => {
        const token = `@@CODE_BLOCK_${codeMap.size}@@`;
        codeMap.set(
            token,
            `<pre class="md-code-block"><code>${escapeHtml(code)}</code></pre>`,
        );
        return token;
    });

    const lines = withCodeTokens.split(/\r?\n/);
    const blocks = [];

    function indentWidth(rawLine) {
        const leading = rawLine.match(/^\s*/)?.[0] || "";
        return leading.replace(/\t/g, "    ").length;
    }

    function parseListMarker(rawLine) {
        const m = rawLine.match(/^(\s*)([-*]|\d+[.)])\s+(.*)$/);
        if (!m) return null;
        const marker = m[2];
        const isOrdered = /^\d+[.)]$/.test(marker);
        return {
            indent: indentWidth(m[1]),
            type: isOrdered ? "ol" : "ul",
            start: isOrdered ? parseInt(marker, 10) : null,
            text: m[3] || "",
        };
    }

    function nextNonEmptyIndex(start) {
        let idx = start;
        while (idx < lines.length && !lines[idx].trim()) idx += 1;
        return idx < lines.length ? idx : -1;
    }

    function isHorizontalRule(trimmedLine) {
        return /^([-*_])(?:\s*\1){2,}$/.test(trimmedLine);
    }

    function splitTableCells(rawLine) {
        let row = rawLine.trim();
        if (row.startsWith("|")) row = row.slice(1);
        if (row.endsWith("|")) row = row.slice(0, -1);
        return row.split("|").map(c => c.trim());
    }

    function isTableDivider(rawLine) {
        const cells = splitTableCells(rawLine);
        if (cells.length < 2) return false;
        return cells.every(cell => {
            const cleaned = cell.replace(/\s+/g, "");
            return /^:?-{3,}:?$/.test(cleaned);
        });
    }

    function renderTableCell(cellText) {
        const escaped = escapeHtml(cellText.trim());
        const withBreaks = escaped.replace(/&lt;br\s*\/?&gt;/gi, "<br>");
        return renderInlineMarkdown(withBreaks);
    }

    function renderTableAt(startIndex) {
        if (startIndex + 1 >= lines.length) return null;
        const headerLine = lines[startIndex].trim();
        const dividerLine = lines[startIndex + 1].trim();
        if (!headerLine.includes("|")) return null;
        if (!dividerLine.includes("|") || !isTableDivider(dividerLine)) return null;

        const headerCells = splitTableCells(headerLine);
        if (headerCells.length < 2) return null;
        const colCount = headerCells.length;

        const rows = [];
        let i = startIndex + 2;
        while (i < lines.length) {
            const raw = lines[i];
            const trimmed = raw.trim();
            if (!trimmed) break;
            if (!trimmed.includes("|")) break;
            if (isTableDivider(trimmed)) {
                i += 1;
                continue;
            }

            const cells = splitTableCells(raw);
            if (cells.length < 2) break;

            const normalized = cells.slice(0, colCount);
            while (normalized.length < colCount) normalized.push("");
            if (cells.length > colCount) {
                normalized[colCount - 1] = `${normalized[colCount - 1]} | ${cells.slice(colCount).join(" | ")}`.trim();
            }
            rows.push(normalized);
            i += 1;
        }

        const headerHtml = headerCells
            .map(cell => `<th class="md-th">${renderTableCell(cell)}</th>`)
            .join("");
        const bodyHtml = rows
            .map(row => `<tr class="md-tr">${row.map(cell => `<td class="md-td">${renderTableCell(cell)}</td>`).join("")}</tr>`)
            .join("");

        return {
            html: `
                <div class="md-table-wrap">
                    <table class="md-table">
                        <thead><tr class="md-tr">${headerHtml}</tr></thead>
                        <tbody>${bodyHtml}</tbody>
                    </table>
                </div>
            `,
            nextIndex: i,
        };
    }

    function isLikelyListDetailLine(line) {
        if (!line) return false;
        // Common loose-list patterns emitted by LLMs: labels and filenames.
        if (/^[A-Za-z][A-Za-z0-9 /&().-]{0,50}:\s*/.test(line)) return true;
        if (/^[A-Za-z0-9._-]+\.(pdf|xlsx?|csv|docx?|pptx?)$/i.test(line)) return true;
        return false;
    }

    function renderListAt(startIndex, listIndent, listType) {
        const first = parseListMarker(lines[startIndex]);
        if (!first || first.indent !== listIndent || first.type !== listType) {
            return null;
        }

        const startAttr = listType === "ol" && first.start && first.start !== 1
            ? ` start="${first.start}"`
            : "";
        const items = [];
        let i = startIndex;

        while (i < lines.length) {
            const marker = parseListMarker(lines[i]);
            if (!marker || marker.indent !== listIndent || marker.type !== listType) break;

            const itemParts = [];
            if (marker.text.trim()) {
                itemParts.push(renderInlineMarkdown(escapeHtml(marker.text.trim())));
            }
            i += 1;

            while (i < lines.length) {
                const raw = lines[i];
                const trimmed = raw.trim();
                const childMarker = parseListMarker(raw);

                if (!trimmed) {
                    const nxt = nextNonEmptyIndex(i + 1);
                    if (nxt === -1) {
                        i = lines.length;
                        break;
                    }
                    const nxtMarker = parseListMarker(lines[nxt]);
                    if (nxtMarker && nxtMarker.indent <= listIndent) {
                        i = nxt;
                        break;
                    }
                    if (itemParts.length > 0 && itemParts[itemParts.length - 1] !== "<br><br>") {
                        itemParts.push("<br><br>");
                    }
                    i = nxt;
                    continue;
                }

                if (childMarker) {
                    if (childMarker.indent > listIndent) {
                        const nested = renderListAt(i, childMarker.indent, childMarker.type);
                        if (nested) {
                            itemParts.push(nested.html);
                            i = nested.nextIndex;
                            continue;
                        }
                    }
                    // Next sibling item or parent list.
                    break;
                }

                if (codeMap.has(trimmed)) {
                    if (indentWidth(raw) <= listIndent) break;
                    itemParts.push(codeMap.get(trimmed));
                    i += 1;
                    continue;
                }

                // Continuation line for this list item.
                const isIndented = indentWidth(raw) > listIndent;
                if (!isIndented && !isLikelyListDetailLine(trimmed)) break;
                const continuation = renderInlineMarkdown(escapeHtml(trimmed));
                itemParts.push(`<div class="md-li-cont">${continuation}</div>`);
                i += 1;
            }

            items.push(`<li class="md-li">${itemParts.join("")}</li>`);
        }

        return {
            html: `<${listType} class="md-${listType}"${startAttr}>${items.join("")}</${listType}>`,
            nextIndex: i,
        };
    }

    let i = 0;
    while (i < lines.length) {
        const rawLine = lines[i];
        const line = rawLine.trim();

        if (!line) {
            i += 1;
            continue;
        }

        if (codeMap.has(line)) {
            blocks.push(codeMap.get(line));
            i += 1;
            continue;
        }

        const heading = line.match(/^(#{1,3})\s+(.+)$/);
        if (heading) {
            const level = heading[1].length;
            const tag = level === 1 ? "h2" : level === 2 ? "h3" : "h4";
            blocks.push(`<${tag} class="md-h">${renderInlineMarkdown(escapeHtml(heading[2]))}</${tag}>`);
            i += 1;
            continue;
        }

        if (isHorizontalRule(line)) {
            blocks.push('<hr class="md-hr">');
            i += 1;
            continue;
        }

        const table = renderTableAt(i);
        if (table) {
            blocks.push(table.html);
            i = table.nextIndex;
            continue;
        }

        const listMarker = parseListMarker(rawLine);
        if (listMarker) {
            const parsed = renderListAt(i, listMarker.indent, listMarker.type);
            if (parsed) {
                blocks.push(parsed.html);
                i = parsed.nextIndex;
                continue;
            }
        }

        if (codeMap.has(line)) {
            blocks.push(codeMap.get(line));
            i += 1;
            continue;
        }

        const paragraphLines = [];
        while (
            i < lines.length
            && lines[i].trim()
            && !codeMap.has(lines[i].trim())
            && !/^(#{1,3})\s+/.test(lines[i].trim())
            && !parseListMarker(lines[i])
        ) {
            paragraphLines.push(renderInlineMarkdown(escapeHtml(lines[i].trim())));
            i += 1;
        }
        blocks.push(`<p class="md-p">${paragraphLines.join("<br>")}</p>`);
    }

    return blocks.join("");
}

function renderInlineMarkdown(text) {
    let html = text;
    html = html.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, label, rawUrl) => {
        const safeUrl = sanitizeUrl(rawUrl);
        if (!safeUrl) return `${label} (${rawUrl})`;
        const href = escapeHtmlAttr(safeUrl);
        return `<a href="${href}" target="_blank" rel="noopener">${label}</a>`;
    });
    html = html.replace(/`([^`]+)`/g, '<code class="md-code">$1</code>');
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*\n]+)\*/g, "<em>$1</em>");
    return html;
}

function getToolIconSvg(type) {
    const icons = {
        search: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>',
        scrape: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>',
        download: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>',
        tool: '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>',
    };
    return icons[type] || icons.tool;
}

/* ── System Transparency Panel ──────────────────────────────────────────── */

let systemData = null;
let currentSystemTab = "prompt";

async function toggleSystemPanel() {
    const overlay = document.getElementById("system-overlay");
    if (overlay.style.display === "none") {
        overlay.style.display = "flex";
        if (!systemData) {
            try {
                systemData = await fetch("/api/config/system").then(r => r.json());
            } catch {
                systemData = { error: "Failed to load system config" };
            }
        }
        renderSystemTab(currentSystemTab);
    } else {
        overlay.style.display = "none";
    }
}

function closeSystemPanel(e) {
    if (e.target === e.currentTarget) {
        document.getElementById("system-overlay").style.display = "none";
    }
}

function switchSystemTab(tab, btn) {
    currentSystemTab = tab;
    document.querySelectorAll(".system-tab").forEach(t => t.classList.remove("active"));
    btn.classList.add("active");
    renderSystemTab(tab);
}

function renderSystemTab(tab) {
    const container = document.getElementById("system-tab-content");
    if (!systemData) {
        container.innerHTML = '<div class="system-loading">Loading...</div>';
        return;
    }
    if (systemData.error) {
        container.innerHTML = `<div class="system-loading">${escapeHtml(systemData.error)}</div>`;
        return;
    }

    switch (tab) {
        case "prompt":
            container.innerHTML = `
                <div class="system-section">
                    <div class="system-section-label">System Prompt</div>
                    <p class="system-section-desc">This is the instruction given to the LLM at the start of every conversation. It defines the agent's behavior, reasoning approach, and general guidelines.</p>
                    <pre class="system-code">${escapeHtml(systemData.system_prompt)}</pre>
                </div>
            `;
            break;

        case "prebuilt":
            const prompts = systemData.prebuilt_prompts || [];
            let promptsHtml = prompts.map(p => `
                <div class="system-tool-card">
                    <div class="system-tool-name">${escapeHtml(p.label)}</div>
                    <div class="system-prompt-meta">
                        <span class="system-prompt-id">${escapeHtml(p.id)}</span>
                        <span class="system-prompt-type">${p.prefill ? "Prefill (user appends)" : "Sends directly"}</span>
                    </div>
                    <pre class="system-code">${escapeHtml(p.message)}</pre>
                </div>
            `).join("");
            container.innerHTML = `
                <div class="system-section">
                    <div class="system-section-label">Prebuilt Prompts</div>
                    <p class="system-section-desc">These are the sidebar quick-action messages. When clicked, the full message below is sent as a user message to the agent. "Prefill" prompts pre-fill the input so the user can append to them. This is where all domain-specific instructions live — the system prompt stays general.</p>
                    ${promptsHtml}
                </div>
            `;
            break;

        case "tools":
            let toolsHtml = systemData.tools.map(t => {
                const fn = t.function;
                const params = fn.parameters?.properties || {};
                const paramList = Object.entries(params).map(([name, p]) =>
                    `  ${name}: ${p.type} — ${p.description || ""}`
                ).join("\n");
                return `
                    <div class="system-tool-card">
                        <div class="system-tool-name">${escapeHtml(fn.name)}</div>
                        <div class="system-tool-desc">${escapeHtml(fn.description)}</div>
                        <pre class="system-code system-code-sm">${escapeHtml(paramList)}</pre>
                    </div>
                `;
            }).join("");
            container.innerHTML = `
                <div class="system-section">
                    <div class="system-section-label">Tool Definitions</div>
                    <p class="system-section-desc">These are the function-calling tools available to the agent. The LLM sees these schemas and can invoke them during a conversation.</p>
                    ${toolsHtml}
                </div>
            `;
            break;

        case "config":
            const agent = systemData.agent;
            container.innerHTML = `
                <div class="system-section">
                    <div class="system-section-label">Agent Configuration</div>
                    <p class="system-section-desc">Runtime settings for the LLM and agent loop.</p>
                    <div class="system-config-grid">
                        <div class="system-config-item">
                            <span class="system-config-key">Model</span>
                            <span class="system-config-value">${escapeHtml(agent.model)}</span>
                        </div>
                        <div class="system-config-item">
                            <span class="system-config-key">Temperature</span>
                            <span class="system-config-value">${agent.temperature}</span>
                        </div>
                        <div class="system-config-item">
                            <span class="system-config-key">Max Tool Calls</span>
                            <span class="system-config-value">${agent.max_tool_calls}</span>
                        </div>
                    </div>
                </div>
                <div class="system-section">
                    <div class="system-section-label">Full Tool Schemas (JSON)</div>
                    <p class="system-section-desc">The raw OpenAI function-calling schemas sent with every API request.</p>
                    <pre class="system-code">${escapeHtml(JSON.stringify(systemData.tools, null, 2))}</pre>
                </div>
            `;
            break;
    }
}

/* ── Boot ────────────────────────────────────────────────────────────────── */
init();
