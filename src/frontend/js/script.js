const API_BASE_URL = 'https://api.deenlink.org/api/v2';
const TOKEN_ENDPOINT = 'https://deenlink.org/api/auth/ai_token.php';

const State = {
    activeConversationId: null,
    jwtToken: null,
    jwtExpiry: null,
    streamingActive: false,
    autoScroll: true,
    isUserScrolling: false,
    scrollTimeout: null,
    tokenQueue: [],
    rendering: false,
    streamController: null,
    lastUserPrompt: null,
    tokenFetchPromise: null,
    isLoadingConversation: false,
    sourcesShown: false,
    currentStreamingElement: null,
    editingMessageId: null,
    pendingFeedback: null,
    responseMode: 'auto',
};

const Elements = {
    chatMessages: document.getElementById("chatMessages"),
    messageInput: document.getElementById("messageInput"),
    sendButton: document.getElementById("sendButton"),
    conversationList: document.getElementById("conversationList"),
    newChatBtn: document.getElementById("newChatBtn"),
    themeToggle: document.getElementById("themeToggle"),
    sidebar: document.getElementById("sidebar"),
    overlay: document.getElementById("sidebarOverlay"),
    menuToggle: document.getElementById("menuToggle"),
    errorToast: document.getElementById("error-toast"),
    quickPromptBtns: document.querySelectorAll(".quick-prompt-btn"),
    inputArea: document.querySelector(".input-area"),
    feedbackModal: document.getElementById("feedbackModal"),
    closeFeedbackModal: document.getElementById("closeFeedbackModal"),
    cancelFeedbackBtn: document.getElementById("cancelFeedbackBtn"),
    submitFeedbackBtn: document.getElementById("submitFeedbackBtn"),
    feedbackReasonInput: document.getElementById("feedbackReasonInput"),
    settingsBtn: document.getElementById("settingsBtn"),
    settingsModal: document.getElementById("settingsModal"),
    closeSettingsModal: document.getElementById("closeSettingsModal"),
    saveSettingsBtn: document.getElementById("saveSettingsBtn"),
    modeRadios: document.querySelectorAll("input[name='responseMode']"),
    scrollToBottomBtn: document.getElementById("scrollToBottomBtn"),
};

const PurifyConfig = {
    ALLOWED_TAGS: [
        'p', 'br', 'strong', 'em', 'b', 'i', 'u',
        'div', 'span', 'blockquote',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'ul', 'ol', 'li', 'a', 'code', 'pre'
    ],
    ALLOWED_ATTR: ['class', 'href', 'title', 'dir', 'target', 'rel'],
    FORBID_ATTR: ['onclick', 'onload', 'onerror'],
};

marked.setOptions({
    breaks: true,
    gfm: true,
    headerIds: false,
    mangle: false,
    sanitize: false,
    smartLists: true,
    smartypants: true,
    xhtml: false
});

async function getValidToken() {
    const now = Date.now();
    if (State.jwtToken && State.jwtExpiry && now < State.jwtExpiry - 60000) {
        return State.jwtToken;
    }
    if (State.tokenFetchPromise) return State.tokenFetchPromise;
    State.tokenFetchPromise = fetchToken();
    try {
        const token = await State.tokenFetchPromise;
        return token;
    } finally {
        State.tokenFetchPromise = null;
    }
}

async function fetchToken() {
    const now = Date.now();
    const csrfMeta = document.querySelector('meta[name="csrf-token"]') || document.querySelector('meta[name="csrf"]');
    let csrfToken = csrfMeta ? csrfMeta.getAttribute('content') : (window.csrfToken || window.csrf_token || '');
    if (!csrfToken) {
        csrfToken = 'deenlink_ai_auto_csrf';
    }

    const formData = new FormData();
    formData.append('csrf_token', csrfToken);

    const res = await fetch(TOKEN_ENDPOINT, {
        method: "POST",
        credentials: "include",
        headers: {
            'X-CSRF-Token': csrfToken,
            'X-CSRF-TOKEN': csrfToken
        },
        body: formData
    });

    if (!res.ok) {
        console.error("Token server error", await res.text());
        throw new Error("Token fetch failed");
    }

    const contentType = res.headers.get("content-type");
    if (!contentType || !contentType.includes("application/json")) {
        console.error("Expected JSON but got:", await res.text());
        throw new Error("Invalid token response format");
    }

    const data = await res.json();
    State.jwtToken = data.ai_jwt || data.token;
    State.jwtExpiry = now + (5 * 60 * 1000);

    return State.jwtToken;
}

function showError(message, duration = 4000) {
    const toast = Elements.errorToast;
    toast.textContent = message;
    toast.classList.remove("hidden");
    setTimeout(() => {
        toast.classList.add("hidden");
    }, duration);
}

function showSuccessToast(message) {
    const toast = document.createElement('div');
    toast.className = 'success-toast';
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 70px;
        left: 50%;
        transform: translateX(-50%);
        background: var(--primary-green);
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
        font-size: 14px;
        z-index: 10000;
        animation: slideDown 0.3s ease;
    `;
    document.body.appendChild(toast);
    setTimeout(() => {
        toast.remove();
    }, 2000);
}

function getUserFriendlyError(rawMessage) {
    if (!rawMessage || typeof rawMessage !== 'string') {
        return "Something went wrong. Please try again.";
    }

    const msg = rawMessage.toLowerCase();

    if (msg.includes("collection") && (msg.includes("doesn't exist") || msg.includes("does not exist") || msg.includes("not found"))) {
        return "The knowledge base is temporarily unavailable. Please try again in a moment.";
    }

    if (/b'[\s\S]*'/.test(rawMessage) || /b"[\s\S]*"/.test(rawMessage)) {
        return "The server returned an unexpected response. Please try again.";
    }

    // FIX #1b: "message not found" errors from edit on old messages - treat gracefully
    if (msg.includes("message not found") || msg.includes("message_not_found")) {
        return null; // Return null to signal we should silently retry as new message
    }

    if (msg.includes("404") || msg.includes("not found")) {
        return "The requested resource was not found. Please try a different question.";
    }
    if (msg.includes("401") || msg.includes("403") || msg.includes("unauthorized") || msg.includes("forbidden")) {
        return "Session expired. Please refresh the page and try again.";
    }
    if (msg.includes("500") || msg.includes("internal server")) {
        return "The server encountered an error. Please try again shortly.";
    }
    if (msg.includes("503") || msg.includes("unavailable")) {
        return "The service is temporarily unavailable. Please try again later.";
    }

    if (msg.includes("timeout") || msg.includes("timed out") || msg.includes("network") || msg.includes("failed to fetch")) {
        return "A network error occurred. Please check your connection and try again.";
    }

    if (msg.includes("abort") || msg.includes("aborted") || msg.includes("cancelled")) {
        return "Request was cancelled.";
    }

    const firstLine = rawMessage.split(/\n|Raw response/i)[0].trim();
    if (firstLine.length > 0 && firstLine.length <= 120) {
        return firstLine;
    }

    return "Something went wrong. Please try again.";
}

function updateSendButtonIcon(type = 'send') {
    const icon = type === 'stop' ? 'fa-stop' : 'fa-paper-plane';
    Elements.sendButton.innerHTML = `<i class="fas ${icon}"></i>`;
}

function createMessageActionButton(iconClass, label, action, extraClass = '') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = `message-action-btn ${extraClass}`.trim();
    btn.setAttribute('aria-label', label);
    btn.title = label;
    btn.dataset.action = action;
    btn.innerHTML = `<i class="fas ${iconClass}"></i>`;
    return btn;
}

function createUserMessageActions(messageEl, promptText, messageId = '') {
    const actions = document.createElement('div');
    actions.className = 'message-actions user-actions';

    const copyBtn = createMessageActionButton('fa-copy', 'Copy prompt', 'copy-prompt');
    const editBtn = createMessageActionButton('fa-pen', 'Edit prompt', 'edit-prompt');

    editBtn.dataset.prompt = promptText;
    copyBtn.dataset.prompt = promptText;

    if (messageId) {
        editBtn.dataset.messageId = messageId;
    }

    copyBtn.addEventListener('click', async () => {
        try {
            await navigator.clipboard.writeText(promptText);
            copyBtn.innerHTML = '<i class="fas fa-check"></i>';
            setTimeout(() => {
                copyBtn.innerHTML = '<i class="far fa-copy"></i>';
            }, 2000);
        } catch (err) {
            console.error('Failed to copy', err);
        }
    });

    actions.appendChild(copyBtn);
    actions.appendChild(editBtn);

    const contentDiv = messageEl.querySelector('.message-content');
    if (contentDiv) {
        contentDiv.appendChild(actions);
    } else {
        messageEl.appendChild(actions);
    }

    return actions;
}

function createErrorRetryAction(messageEl, promptText) {
    const actions = document.createElement('div');
    actions.className = 'message-actions ai-actions';
    const retryBtn = createMessageActionButton('fa-rotate-right', 'Retry response', 'retry-prompt', 'retry-error-btn');
    retryBtn.dataset.prompt = promptText;
    actions.appendChild(retryBtn);
    messageEl.appendChild(actions);
    return actions;
}

function isNearBottom(el, threshold = 200) {
    return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function isHTMLContent(str) {
    if (!str || typeof str !== 'string') return false;
    const trimmed = str.trim();
    return trimmed.startsWith('<') && trimmed.includes('</');
}

// FIX #2: Remove leading whitespace/indent from last paragraphs in markdown output
function cleanMarkdownOutput(rawContent) {
    // Remove leading spaces/tabs from lines that would cause indent on last paragraphs
    return rawContent
        .replace(/^[ \t]+(?=[^\s])/gm, '') // Remove leading whitespace on each line
        .replace(/\n{3,}/g, '\n\n')          // Collapse multiple blank lines
        .trim();
}

function renderContent(element, rawContent) {
    const cleaned = rawContent
        .replace(/>\s+</g, '><')
        .replace(/\n\s*\n/g, '\n')
        .trim();

    let html;
    if (isHTMLContent(cleaned)) {
        html = cleaned;
    } else {
        try {
            // FIX #2: Clean content before parsing to prevent indent on last paragraph
            const cleanedForMd = cleanMarkdownOutput(rawContent);
            html = DOMPurify.sanitize(marked.parse(cleanedForMd, { async: false }), PurifyConfig);
        } catch (e) {
            html = DOMPurify.sanitize(rawContent.replace(/\n/g, '<br>'), PurifyConfig);
        }
    }

    element.innerHTML = html;

    // FIX #2: Remove any text-indent or padding-left that may have been applied to last <p>
    const paragraphs = element.querySelectorAll('p');
    paragraphs.forEach(p => {
        p.style.textIndent = '0';
        p.style.paddingLeft = '0';
        p.style.marginLeft = '0';
    });

    element.querySelectorAll('a').forEach(link => {
        if (link.hostname !== window.location.hostname) {
            link.setAttribute('target', '_blank');
            link.setAttribute('rel', 'noopener noreferrer');
        }
    });
}

async function streamTokenToElement(element, token) {
    if (!element) return;
    const chars = token.split('');
    for (let i = 0; i < chars.length; i++) {
        if (!State.streamingActive) break;
        element.textContent += chars[i];
        let delay = 8;
        if (chars[i] === '.' || chars[i] === '!' || chars[i] === '?') delay = 60;
        else if (chars[i] === ',' || chars[i] === ';') delay = 25;
        else if (chars[i] === ' ') delay = 4;
        await new Promise(resolve => setTimeout(resolve, delay));
        if (State.autoScroll && !State.isUserScrolling) {
            Elements.chatMessages.scrollTo({
                top: Elements.chatMessages.scrollHeight,
                behavior: 'auto'
            });
        }
    }
}

function showSearchIndicator() {
    removeSearchIndicator();
    removeTypingIndicator();
    const indicator = document.createElement('div');
    indicator.className = 'search-indicator';
    indicator.id = 'searchIndicator';
    indicator.innerHTML = `
        <div class="search-indicator-content">
            <div class="search-spinner"></div>
            <span class="search-text">Searching knowledge base...</span>
        </div>
    `;
    Elements.chatMessages.appendChild(indicator);
    if (State.autoScroll) {
        Elements.chatMessages.scrollTo({
            top: Elements.chatMessages.scrollHeight,
            behavior: 'smooth'
        });
    }
    return indicator;
}

function showTypingIndicator() {
    removeSearchIndicator();
    removeTypingIndicator();
    const indicator = document.createElement('div');
    indicator.className = 'message ai typing-indicator-message';
    indicator.id = 'typingIndicator';
    indicator.innerHTML = `
        <div class="typing-dots">
            <div class="typing-dot-small"></div>
            <div class="typing-dot-small"></div>
            <div class="typing-dot-small"></div>
        </div>
    `;
    Elements.chatMessages.appendChild(indicator);
    if (State.autoScroll) {
        Elements.chatMessages.scrollTo({
            top: Elements.chatMessages.scrollHeight,
            behavior: 'smooth'
        });
    }
    return indicator;
}

function removeSearchIndicator() {
    const indicator = document.getElementById('searchIndicator');
    if (indicator) {
        if (indicator.dataset.intervalId) {
            clearInterval(parseInt(indicator.dataset.intervalId));
        }
        indicator.remove();
    }
}

function removeTypingIndicator() {
    const indicator = document.getElementById('typingIndicator');
    if (indicator) indicator.remove();
}

function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function filterBestSources(sources) {
    if (!sources || sources.length === 0) return sources;
    return [sources[0]];
}

function createSourcesPanel(sources) {
    const panel = document.createElement('div');
    panel.className = 'sources-panel';
    const validSources = sources.filter(s => s && s.payload);
    panel.innerHTML = `
        <div class="sources-header" onclick="this.parentElement.classList.toggle('expanded')">
            <span>${validSources.length} source${validSources.length !== 1 ? 's' : ''} used</span>
            <i class="fas fa-chevron-down sources-chevron"></i>
        </div>
        <div class="sources-content">
            ${validSources.map((src, idx) => {
        const isHadith = src.source_type === 'hadith';
        const payload = src.payload || {};
        let displayTitle = isHadith ? 'Hadith' : 'Qur\'an';
        if (src.display_reference) {
            displayTitle = src.display_reference;
        } else if (isHadith && payload.hadith_number_display) {
            displayTitle = `${payload.collection || 'Hadith'} ${payload.hadith_number_display}`;
        } else if (!isHadith && payload.surah_name && payload.ayah) {
            displayTitle = `${payload.surah_name}:${payload.ayah}`;
        }
        return `
                    <div class="source-item">
                        <div class="source-badge">${idx + 1}</div>
                        <div class="source-details">
                            <div class="source-title">${escapeHtml(displayTitle)}</div>
                            <div class="source-meta">
                                ${isHadith ?
                `<span>${escapeHtml(payload.collection || 'Unknown')}</span>
                                     ${payload.hadith_number_display ? `<span>${escapeHtml(payload.hadith_number_display)}</span>` : ''}`
                :
                `<span>Surah ${escapeHtml(payload.surah_name || 'Unknown')}</span>
                                     <span>Ayah ${payload.ayah || 'Unknown'}</span>`
            }
                            </div>
                            ${payload.arabic ? `
                            <details class="source-expandable">
                                <summary>View Arabic Text</summary>
                                <div class="rag-arabic" dir="rtl">${escapeHtml(payload.arabic)}</div>
                            </details>` : ''}
                            ${payload.english ? `
                            <details class="source-expandable">
                                <summary>View English Translation</summary>
                                <div class="rag-english">${escapeHtml(payload.english)}</div>
                            </details>` : ''}
                        </div>
                    </div>
                `;
    }).join('')}
        </div>
    `;
    return panel;
}

function createStreamingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ai streaming';
    messageDiv.innerHTML = `
        <div class="message-content">
            <div class="message-text"></div>
            <div class="message-feedback" style="display: none;">
                <button class="feedback-btn like-btn" title="Helpful response">
                    <i class="far fa-thumbs-up"></i>
                    <span>Helpful</span>
                </button>
                <button class="feedback-btn dislike-btn" title="Not helpful">
                    <i class="far fa-thumbs-down"></i>
                    <span>Not helpful</span>
                </button>
                <button class="feedback-btn copy-btn" title="Copy response">
                    <i class="far fa-copy"></i>
                    <span>Copy</span>
                </button>
            </div>
        </div>
    `;
    Elements.chatMessages.appendChild(messageDiv);
    if (State.autoScroll) {
        Elements.chatMessages.scrollTo({
            top: Elements.chatMessages.scrollHeight,
            behavior: 'smooth'
        });
    }
    return {
        container: messageDiv,
        textEl: messageDiv.querySelector('.message-text'),
        feedbackDiv: messageDiv.querySelector('.message-feedback')
    };
}

function finalizeStreamingMessage(messageObj, rawContent, sources = null) {
    const { container, textEl } = messageObj;
    let feedbackDiv = messageObj.feedbackDiv || container.querySelector('.message-feedback');

    container.classList.remove('streaming', 'loading');
    const streamingText = textEl.querySelector('.streaming-text');
    if (streamingText) {
        streamingText.remove();
    }

    const indicator = container.querySelector('.typing-indicator');
    if (indicator) indicator.remove();

    renderContent(textEl, rawContent);
    textEl.classList.add('message-text');
    void textEl.offsetHeight;

    if (textEl.querySelector('.rag-source')) {
        styleRAGSources(textEl);
    }

    const contentDiv = container.querySelector('.message-content');

    // FIX #4: Filter to best source only before rendering panel
    if (sources && sources.length > 0) {
        const bestSources = filterBestSources(sources);
        const existingPanel = container.querySelector('.sources-panel');
        if (existingPanel) existingPanel.remove();
        const sourcesPanel = createSourcesPanel(bestSources);
        contentDiv.appendChild(sourcesPanel);
    }

    if (feedbackDiv) {
        feedbackDiv.style.display = 'flex';
        setupFeedbackButtons(feedbackDiv, textEl, container.dataset.prompt);
    } else {
        feedbackDiv = createFeedbackButtons(contentDiv);
        feedbackDiv.style.display = 'flex';
        contentDiv.appendChild(feedbackDiv);
    }

    setTimeout(() => {
        const scrollable = Elements.chatMessages.closest('.messages-area') || Elements.chatMessages.parentElement;
        const target = scrollable || Elements.chatMessages;
        const distFromBottom = target.scrollHeight - target.scrollTop - target.clientHeight;

        if (distFromBottom <= 80) {
            target.scrollTo({ top: target.scrollHeight, behavior: 'smooth' });
        } else {
            container.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    }, 80);
}

function setupFeedbackButtons(feedbackDiv, textEl, prompt) {
    const likeBtn = feedbackDiv.querySelector('.like-btn');
    const dislikeBtn = feedbackDiv.querySelector('.dislike-btn');
    const copyBtn = feedbackDiv.querySelector('.copy-btn');

    likeBtn.addEventListener('click', async () => {
        const response = textEl?.innerText || '';
        likeBtn.classList.add('active');
        likeBtn.innerHTML = '<i class="fas fa-thumbs-up"></i><span>Helpful</span>';
        dislikeBtn.disabled = true;
        await sendFeedback('like', prompt, response);
        showSuccessToast('Thanks for your feedback!');
    });

    dislikeBtn.addEventListener('click', async () => {
        const response = textEl?.innerText || '';
        dislikeBtn.classList.add('active');
        dislikeBtn.innerHTML = '<i class="fas fa-thumbs-down"></i><span>Not helpful</span>';
        likeBtn.disabled = true;
        await sendFeedback('dislike', prompt, response);
        showSuccessToast('Thanks for your feedback!');
    });

    copyBtn.addEventListener('click', async () => {
        const text = textEl?.innerText || '';
        try {
            await navigator.clipboard.writeText(text);
            copyBtn.innerHTML = '<i class="fas fa-check"></i><span>Copied!</span>';
            setTimeout(() => {
                copyBtn.innerHTML = '<i class="far fa-copy"></i><span>Copy</span>';
            }, 2000);
        } catch (err) {
            showError('Failed to copy');
        }
    });
}

function createMessageElement(sender, text = "", incomplete = false, prompt = null, messageId = null) {
    const el = document.createElement("div");
    el.className = `message ${sender}`;
    if (incomplete) el.classList.add('error');
    if (prompt) el.dataset.prompt = prompt;
    el.dataset.incomplete = incomplete ? "true" : "false";
    el.dataset.raw = text || "";
    el.dataset.messageId = messageId || Date.now().toString(36) + Math.random().toString(36).substr(2);

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";

    const textDiv = document.createElement("div");
    textDiv.className = "message-text";

    if (sender === "user") {
        textDiv.textContent = text;
    } else {
        if (isHTMLContent(text)) {
            textDiv.innerHTML = DOMPurify.sanitize(text, PurifyConfig);
            setTimeout(() => styleRAGSources(textDiv), 10);
        } else {
            const cleanedText = cleanMarkdownOutput(text);
            textDiv.innerHTML = DOMPurify.sanitize(marked.parse(cleanedText, { async: false }), PurifyConfig);
        }
    }

    contentDiv.appendChild(textDiv);
    if (sender === "ai" && !incomplete) {
        const feedbackButtons = createFeedbackButtons(contentDiv);
        contentDiv.appendChild(feedbackButtons);
    }

    el.appendChild(contentDiv);
    if (sender === "user") {
        createUserMessageActions(el, text || prompt || "", el.dataset.messageId);
    } else if (sender === "ai" && incomplete) {
        createErrorRetryAction(el, prompt || "");
    }
    Elements.chatMessages.appendChild(el);

    if (State.autoScroll) {
        requestAnimationFrame(() => {
            Elements.chatMessages.scrollTop = Elements.chatMessages.scrollHeight;
        });
    }
    return textDiv;
}

function appendLoadingMessage() {
    const el = document.createElement("div");
    el.className = "message ai loading";
    el.innerHTML = `
        <div class="message-content">
           <div class="message-text"></div>
           <div class="typing-indicator">
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
           </div>
        </div>
    `;
    Elements.chatMessages.appendChild(el);
    requestAnimationFrame(() => {
        Elements.chatMessages.scrollTop = Elements.chatMessages.scrollHeight;
    });
    return {
        container: el,
        textEl: el.querySelector(".message-text"),
        remove: () => el.remove()
    };
}

function replaceLoadingWithAIMessage(loadingObj, incomplete = false) {
    const { container } = loadingObj;
    container.classList.remove("loading");
    const indicator = container.querySelector(".typing-indicator");
    if (indicator) indicator.remove();
    if (incomplete) {
        container.dataset.incomplete = "true";
        const retry = document.createElement("span");
        retry.className = "retry-icon";
        retry.title = "Retry";
        retry.innerHTML = "&#x21bb;";
        retry.onclick = () => retryMessage(container.dataset.prompt);
        container.querySelector(".message-content").appendChild(retry);
    }
    const contentDiv = container.querySelector(".message-content");
    const textEl = container.querySelector(".message-text");
    if (contentDiv && !contentDiv.querySelector('.message-feedback')) {
        const feedbackButtons = createFeedbackButtons(contentDiv);
        contentDiv.appendChild(feedbackButtons);
    }
    return textEl;
}

function appendMessage(sender, text, options = {}) {
    const { messageId = null } = options;
    const shouldScroll = isNearBottom(Elements.chatMessages);
    const el = document.createElement("div");
    el.className = `message ${sender}`;
    el.dataset.messageId = messageId || Date.now().toString(36) + Math.random().toString(36).substr(2);
    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    const textDiv = document.createElement("div");
    textDiv.className = "message-text";
    textDiv.dataset.raw = text;

    renderContent(textDiv, text);
    textDiv.classList.add('message-text');
    void textDiv.offsetHeight;
    setTimeout(() => {
        styleRAGSources(textDiv);
    }, 10);

    contentDiv.appendChild(textDiv);
    if (sender === "ai") {
        const feedbackButtons = createFeedbackButtons(contentDiv);
        contentDiv.appendChild(feedbackButtons);
    }
    el.appendChild(contentDiv);
    if (sender === "user") {
        createUserMessageActions(el, text, el.dataset.messageId);
    }
    Elements.chatMessages.appendChild(el);
    if (shouldScroll) {
        Elements.chatMessages.scrollTop = Elements.chatMessages.scrollHeight;
    }
}

function createFeedbackButtons(messageContent) {
    const feedbackDiv = document.createElement('div');
    feedbackDiv.className = 'message-feedback';
    feedbackDiv.innerHTML = `
        <button class="feedback-btn like-btn" title="Helpful response">
            <i class="far fa-thumbs-up"></i>
            <span>Helpful</span>
        </button>
        <button class="feedback-btn dislike-btn" title="Not helpful">
            <i class="far fa-thumbs-down"></i>
            <span>Not helpful</span>
        </button>
        <button class="feedback-btn copy-btn" title="Copy response">
            <i class="far fa-copy"></i>
            <span>Copy</span>
        </button>
    `;
    const likeBtn = feedbackDiv.querySelector('.like-btn');
    const dislikeBtn = feedbackDiv.querySelector('.dislike-btn');
    const copyBtn = feedbackDiv.querySelector('.copy-btn');
    const textEl = messageContent.querySelector('.message-text');

    likeBtn.addEventListener('click', async () => {
        const msgContainer = messageContent.closest('.message');
        const prompt = msgContainer?.dataset.prompt || msgContainer?.previousElementSibling?.querySelector('.message-text')?.innerText || '';
        const response = textEl?.innerText || '';
        likeBtn.classList.add('active');
        likeBtn.innerHTML = '<i class="fas fa-thumbs-up"></i><span>Helpful</span>';
        dislikeBtn.disabled = true;
        await sendFeedback('like', prompt, response);
        showSuccessToast('Thanks for your feedback!');
    });

    dislikeBtn.addEventListener('click', async () => {
        const msgContainer = messageContent.closest('.message');
        const promptStr = msgContainer?.dataset.prompt || msgContainer?.previousElementSibling?.querySelector('.message-text')?.innerText || '';
        const response = textEl?.innerText || '';

        State.pendingFeedback = { prompt: promptStr, response: response, dislikeBtn: dislikeBtn, likeBtn: likeBtn };

        if (Elements.feedbackReasonInput) Elements.feedbackReasonInput.value = '';
        if (Elements.feedbackModal) Elements.feedbackModal.classList.remove('hidden');
    });

    copyBtn.addEventListener('click', async () => {
        const text = textEl?.innerText || '';
        try {
            await navigator.clipboard.writeText(text);
            copyBtn.innerHTML = '<i class="fas fa-check"></i><span>Copied!</span>';
            setTimeout(() => {
                copyBtn.innerHTML = '<i class="far fa-copy"></i><span>Copy</span>';
            }, 2000);
        } catch (err) {
            showError('Failed to copy');
        }
    });
    return feedbackDiv;
}

async function sendFeedback(type, prompt, response, reason = null) {
    try {
        const token = await getValidToken();
        const feedbackData = {
            type,
            prompt,
            response,
            reason,
            conversationId: State.activeConversationId,
            timestamp: new Date().toISOString(),
            url: window.location.href
        };
        const res = await fetch(`${API_BASE_URL}/feedback`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`
            },
            body: JSON.stringify(feedbackData)
        });
        if (!res.ok) throw new Error('Failed to submit feedback');
        console.log('Feedback sent successfully');
    } catch (err) {
        console.error('Failed to send feedback:', err);
    }
}

function stopGeneration() {
    if (State.streamController) {
        State.streamController.abort();
    }
    State.streamingActive = false;
    State.streamController = null;
    State.rendering = false;
    State.tokenQueue = [];
    const loadingEl = document.querySelector('.message.ai.loading');
    if (loadingEl) loadingEl.remove();
    const searchIndicator = document.getElementById('searchIndicator');
    if (searchIndicator) searchIndicator.remove();
    updateSendButtonIcon('send');
    Elements.messageInput.disabled = false;
    Elements.sendButton.disabled = false;
    Elements.messageInput.focus();
    showError("Generation stopped");
}

async function fetchWithRetry(url, options, maxRetries = 3) {
    let lastError;
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 30000);
            const res = await fetch(url, {
                ...options,
                signal: controller.signal,
            });
            clearTimeout(timeoutId);
            return res;
        } catch (error) {
            lastError = error;
            if (attempt === maxRetries) break;
            await new Promise(r => setTimeout(r, 1000 * attempt));
        }
    }
    throw lastError;
}

async function loadConversations() {
    try {
        const token = await getValidToken();
        const res = await fetchWithRetry(`${API_BASE_URL}/conversations`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!res.ok) {
            if (res.status === 401 || res.status === 403) {
                State.jwtToken = null;
                State.jwtExpiry = null;
                throw new Error("Session expired");
            }
            throw new Error("Failed to load conversations");
        }
        const data = await res.json();
        if (!Array.isArray(data)) throw new Error("Invalid data format");
        renderConversationTabs(data);
        if (!State.activeConversationId && data.length > 0) {
            await switchToConversation(data[0].id);
        }
    } catch (err) {
        showError(err.message || "Failed to load conversations");
    }
}

function renderConversationTabs(conversations) {
    if (!Array.isArray(conversations)) {
        showError("Invalid conversations data");
        return;
    }
    Elements.conversationList.innerHTML = "";
    conversations.forEach(conv => {
        const card = document.createElement("div");
        card.className = "conversation-card";
        if (conv.id === State.activeConversationId) card.classList.add("active");
        card.dataset.id = conv.id;
        const titleSpan = document.createElement("span");
        titleSpan.className = "conversation-title";
        titleSpan.textContent = conv.title || "New Chat";
        card.appendChild(titleSpan);
        card.onclick = async () => {
            if (State.isLoadingConversation) return;
            await switchToConversation(conv.id);
        };
        const deleteBtn = document.createElement("button");
        deleteBtn.className = "delete-btn";
        deleteBtn.setAttribute("aria-label", "Delete conversation");
        deleteBtn.innerHTML = '<i class="fas fa-trash-alt"></i>';
        deleteBtn.onclick = async (e) => {
            e.stopPropagation();
            if (!confirm("Delete this conversation?")) return;
            try {
                await deleteConversation(conv.id);
            } catch (err) {
                showError("Failed to delete conversation");
            }
        };
        card.appendChild(deleteBtn);
        Elements.conversationList.appendChild(card);
    });
}

async function switchToConversation(id) {
    if (State.isLoadingConversation || id === State.activeConversationId) return;
    State.isLoadingConversation = true;
    closeSidebar();
    Elements.chatMessages.innerHTML = '<div class="loading-state">Loading...</div>';
    try {
        await loadConversation(id);
        State.activeConversationId = id;
        document.querySelectorAll('.conversation-card').forEach(card => {
            card.classList.toggle('active', card.dataset.id === id);
        });
    } catch (err) {
        showError("Failed to load conversation");
        Elements.chatMessages.innerHTML = '';
    } finally {
        State.isLoadingConversation = false;
    }
}

async function loadConversation(id) {
    const token = await getValidToken();
    const res = await fetchWithRetry(`${API_BASE_URL}/conversations/${id}`, {
        headers: { "Authorization": `Bearer ${token}` }
    });
    if (!res.ok) throw new Error("Conversation not found");
    const data = await res.json();
    Elements.chatMessages.innerHTML = "";
    if (!data.messages || !Array.isArray(data.messages)) {
        throw new Error("Invalid conversation data");
    }
    data.messages.forEach(msg => {
        appendMessage(
            msg.role === "user" ? "user" : "ai",
            msg.content,
            { messageId: msg.id || null }
        );
    });

    // FIX #3: Scroll to BOTTOM (most recent message) after loading conversation
    // Use multiple frames to ensure all content (including images) is rendered
    const scrollToBottom = () => {
        const messagesArea = Elements.chatMessages.closest('.messages-area') || Elements.chatMessages.parentElement;
        const target = messagesArea || Elements.chatMessages;
        target.scrollTop = target.scrollHeight;
        Elements.chatMessages.scrollTop = Elements.chatMessages.scrollHeight;
    };

    scrollToBottom();
    requestAnimationFrame(() => {
        scrollToBottom();
        setTimeout(scrollToBottom, 100);
        setTimeout(scrollToBottom, 300);
    });
}

async function editConversationFromMessage(conversationId, messageId, editedText) {
    const token = await getValidToken();
    const res = await fetchWithRetry(`${API_BASE_URL}/conversations/${conversationId}/edit`, {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            message_id: messageId,
            message: editedText
        })
    });
    if (!res.ok) {
        let detail = "Failed to edit conversation";
        try {
            const errorData = await res.json();
            detail = errorData?.detail || detail;
        } catch (_) {
            // no-op
        }
        throw new Error(detail);
    }
    return res.json();
}

async function deleteConversation(conversationId) {
    const token = await getValidToken();
    const res = await fetchWithRetry(
        `${API_BASE_URL}/conversations/${conversationId}`,
        {
            method: "DELETE",
            headers: { "Authorization": `Bearer ${token}` },
        }
    );
    if (!res.ok) throw new Error("Delete failed");
    if (conversationId === State.activeConversationId) {
        State.activeConversationId = null;
        Elements.chatMessages.innerHTML = '';
    }
    await loadConversations();
}

async function createNewConversation() {
    const token = await getValidToken();
    const res = await fetchWithRetry(`${API_BASE_URL}/conversations/new`, {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json"
        }
    });
    if (!res.ok) throw new Error("Failed to create conversation");
    return await res.json();
}

function styleRAGSources(el) {
    if (!el) return;
    const sources = el.querySelectorAll('.rag-source');
    const totalSources = sources.length;

    sources.forEach((source, index) => {
        if (totalSources > 1) {
            let badge = source.querySelector('.source-badge');
            if (!badge) {
                badge = document.createElement('div');
                badge.className = 'source-badge';
                source.insertBefore(badge, source.firstChild);
            }
            badge.textContent = `${index + 1}/${totalSources}`;
        }

        source.style.cssText = '';
    });
}

function showRAGLoadingIndicator(el) {
    const existing = el.querySelector('.rag-loading-indicator');
    if (existing) return;
    const indicator = document.createElement('div');
    indicator.className = 'rag-loading-indicator';
    indicator.innerHTML = `
        <div class="spinner"></div>
        <span>Retrieving Islamic sources...</span>
    `;
    el.innerHTML = '';
    el.appendChild(indicator);
    if (!document.getElementById('rag-animations')) {
        const style = document.createElement('style');
        style.id = 'rag-animations';
        style.textContent = `
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.6; }
            }
        `;
        document.head.appendChild(style);
    }
}

async function sendMessage(retryData = null) {
    if (State.streamingActive) {
        showError("Already processing a message");
        return;
    }

    State.streamingActive = true;
    updateSendButtonIcon('stop');
    Elements.messageInput.disabled = true;

    const text = retryData?.message ?? Elements.messageInput.value.trim();
    if (!text) {
        resetInputState();
        return;
    }
    const editingMessageId = retryData?.editMessageId || State.editingMessageId;

    if (!retryData) State.lastUserPrompt = text;

    if (!State.activeConversationId) {
        try {
            const newConv = await createNewConversation();
            State.activeConversationId = newConv.id;
        } catch (err) {
            resetInputState();
            showError("Failed to create conversation");
            return;
        }
    }

    if (!retryData) {
        Elements.messageInput.value = "";
        Elements.messageInput.style.height = "auto";
    }

    // FIX #1b: Handle edit with "message not found" gracefully - fall back to new message
    if (editingMessageId && State.activeConversationId) {
        try {
            await editConversationFromMessage(State.activeConversationId, editingMessageId, text);
            await loadConversation(State.activeConversationId);
            showSuccessToast('Message updated and regenerated');
            State.editingMessageId = null;
            resetInputState();
            return;
        } catch (err) {
            State.editingMessageId = null;
            const friendlyErr = getUserFriendlyError(err?.message);
            // If it's a "message not found" error, silently send as new message instead
            if (friendlyErr === null) {
                console.warn('Message not found for edit, sending as new message');
                // Continue below to send as normal new message
            } else {
                resetInputState();
                showError(friendlyErr || "Failed to edit message");
                return;
            }
        }
    }

    appendMessage("user", text);
    const streamingMsg = appendLoadingMessage();
    streamingMsg.container.dataset.prompt = text;
    streamingMsg.container.style.display = 'none';

    let collectedSources = null;
    let fullContent = '';
    let aiMessageEl = streamingMsg.textEl;
    let isHTML = false;
    let hasDetectedType = false;
    let hasReceivedContent = false;

    try {
        const token = await getValidToken();
        State.streamController = new AbortController();

        const res = await fetch(`${API_BASE_URL}/ask/stream`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({
                message: text,
                conversation_id: State.activeConversationId,
                mode: State.responseMode
            }),
            signal: State.streamController.signal
        });

        if (!res.ok || !res.body) {
            throw new Error(`Request failed: ${res.status}`);
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const parts = buffer.split("\n\n");
            buffer = parts.pop();

            for (const part of parts) {
                const trimmed = part.trim();
                if (!trimmed.startsWith("data:")) continue;

                const dataStr = trimmed.replace(/^data:\s*/, "");
                let data;
                try {
                    data = JSON.parse(dataStr);
                } catch {
                    continue;
                }

                switch (data.type) {
                    case 'search_start':
                        showSearchIndicator();
                        break;

                    case 'chat_start':
                        showTypingIndicator();
                        break;

                    case 'sources':
                        collectedSources = data.sources;
                        break;

                    case 'token':
                        if (!hasDetectedType) {
                            hasDetectedType = true;
                            removeSearchIndicator();
                            removeTypingIndicator();
                            streamingMsg.container.style.display = 'flex';

                            if (data.content.trim().startsWith('<')) {
                                isHTML = true;
                            }
                        }

                        const content = data.content;
                        hasReceivedContent = true;

                        if (isHTML) {
                            fullContent += content;
                            aiMessageEl.innerHTML = DOMPurify.sanitize(fullContent, PurifyConfig);
                            styleRAGSources(aiMessageEl);
                        } else {
                            fullContent += content;
                            await streamTokenWithTypingEffect(aiMessageEl, content);
                        }
                        break;

                    case 'error':
                        throw new Error(getUserFriendlyError(data.message || "Stream error"));

                    case 'done':
                        break;
                }
            }
        }

        let rawFinalContent = fullContent;
        if (!rawFinalContent || !hasReceivedContent) {
            rawFinalContent = "I'm sorry, I couldn't generate a response. Please try again.";
        }

        finalizeStreamingMessage(streamingMsg, rawFinalContent, collectedSources);
        await loadConversations();

    } catch (err) {
        removeSearchIndicator();
        removeTypingIndicator();

        if (err.name === 'AbortError') {
            streamingMsg.container.remove();
        } else {
            streamingMsg.container.remove();
            const safeError = getUserFriendlyError(err?.message);
            if (safeError) {
                createMessageElement("ai", safeError, true, text);
            }
        }
    } finally {
        resetInputState();
    }
}

async function streamTokenWithTypingEffect(element, token) {
    if (!element) return;

    const chars = token.split('');

    for (let i = 0; i < chars.length; i++) {
        if (!State.streamingActive) break;

        element.textContent += chars[i];

        let delay = 5;
        if (chars[i] === '.' || chars[i] === '!' || chars[i] === '?') delay = 40;
        else if (chars[i] === ',' || chars[i] === ';') delay = 15;
        else if (chars[i] === ' ') delay = 2;

        await new Promise(resolve => setTimeout(resolve, delay));

        if (State.autoScroll && !State.isUserScrolling) {
            Elements.chatMessages.scrollTo({
                top: Elements.chatMessages.scrollHeight,
                behavior: 'auto'
            });
        }
    }
}

function resetInputState() {
    State.streamingActive = false;
    State.streamController = null;
    State.tokenQueue = [];
    State.rendering = false;
    State.currentStreamingElement = null;

    updateSendButtonIcon('send');
    Elements.messageInput.disabled = false;
    Elements.sendButton.disabled = false;
    Elements.messageInput.focus();
}

function retryMessage(prompt) {
    if (!prompt) return;
    sendMessage({ message: prompt });
}

function initSidebar() {
    Elements.menuToggle.addEventListener("click", toggleSidebar);
    Elements.overlay.addEventListener("click", closeSidebar);

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && Elements.sidebar.classList.contains('open')) {
            closeSidebar();
        }
    });

    let startX = 0;
    let startY = 0;

    document.addEventListener("touchstart", e => {
        startX = e.changedTouches[0].screenX;
        startY = e.changedTouches[0].screenY;
    }, { passive: true });

    document.addEventListener("touchend", e => {
        const endX = e.changedTouches[0].screenX;
        const endY = e.changedTouches[0].screenY;
        const diffX = endX - startX;
        const diffY = endY - startY;

        if (Math.abs(diffX) > Math.abs(diffY)) {
            if (diffX > 80) openSidebar();
            if (diffX < -80) closeSidebar();
        }
    }, { passive: true });
}

function openSidebar() {
    Elements.sidebar.classList.add("open");
    Elements.overlay.classList.add("show");
}

function closeSidebar() {
    Elements.sidebar.classList.remove("open");
    Elements.overlay.classList.remove("show");
}

function toggleSidebar() {
    Elements.sidebar.classList.contains("open") ? closeSidebar() : openSidebar();
}

const PWA = {
    init: async () => {
        const isCapacitor = window.Capacitor !== undefined;
        if (isCapacitor) {
            return;
        }
        if (!('serviceWorker' in navigator)) return;
        try {
            await navigator.serviceWorker.register('sw.js', { scope: './' });
        } catch (error) {
            // Silent fail
        }
    }
};

// FIX #1: Edit message - scroll edit area into view when keyboard opens
function scrollEditIntoView(editContainer) {
    // Small delay to let keyboard open
    setTimeout(() => {
        // Scroll the edit container into view within the messages area
        editContainer.scrollIntoView({ behavior: 'smooth', block: 'center' });

        // Also ensure the messages area scrolls to show the edit field above keyboard
        const messagesArea = Elements.chatMessages.closest('.messages-area') || Elements.chatMessages.parentElement;
        if (messagesArea) {
            const containerRect = editContainer.getBoundingClientRect();
            const areaRect = messagesArea.getBoundingClientRect();
            
            if (containerRect.bottom > areaRect.bottom - 50) {
                messagesArea.scrollTop += (containerRect.bottom - areaRect.bottom + 80);
            }
        }
    }, 350); // Wait for keyboard animation
}

function initEventListeners() {
    Elements.sendButton.addEventListener("click", () => {
        if (State.streamingActive && State.streamController) {
            stopGeneration();
        } else {
            sendMessage();
        }
    });

    const inputContainer = document.querySelector('.input-container');
    if (inputContainer) {
        inputContainer.addEventListener('touchmove', (e) => {
            const onTextarea = e.target === Elements.messageInput;
            const textareaScrollable = onTextarea &&
                Elements.messageInput.scrollHeight > Elements.messageInput.clientHeight;
            if (!textareaScrollable) {
                e.preventDefault();
            }
        }, { passive: false });
    }

    Elements.messageInput.addEventListener("input", () => {
        Elements.messageInput.style.height = "auto";
        const newHeight = Math.min(Elements.messageInput.scrollHeight, 200);
        Elements.messageInput.style.height = newHeight + "px";
        Elements.messageInput.style.overflowY = Elements.messageInput.scrollHeight > 200 ? "auto" : "hidden";
    });

    Elements.messageInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (!State.streamingActive) sendMessage();
        }
    });

    // FIX #3: scroll-to-bottom button visibility - use correct scrollable container
    const messagesArea = Elements.chatMessages.closest('.messages-area') || Elements.chatMessages.parentElement;
    const scrollContainer = messagesArea || Elements.chatMessages;

    const updateScrollButton = () => {
        if (!Elements.scrollToBottomBtn) return;
        const distanceFromBottom = scrollContainer.scrollHeight -
            scrollContainer.scrollTop -
            scrollContainer.clientHeight;

        if (distanceFromBottom > 250) {
            Elements.scrollToBottomBtn.classList.remove('hidden');
        } else {
            Elements.scrollToBottomBtn.classList.add('hidden');
        }
    };

    // Listen on BOTH the messages area AND chatMessages for scroll events
    scrollContainer.addEventListener("scroll", () => {
        if (State.scrollTimeout) clearTimeout(State.scrollTimeout);

        updateScrollButton();

        const distanceFromBottom = scrollContainer.scrollHeight -
            scrollContainer.scrollTop -
            scrollContainer.clientHeight;

        if (State.streamingActive) {
            if (distanceFromBottom > 300) {
                State.isUserScrolling = true;
                State.autoScroll = false;
            } else {
                State.autoScroll = true;
                State.isUserScrolling = false;
            }
        } else {
            State.autoScroll = distanceFromBottom < 100;
        }

        State.scrollTimeout = setTimeout(() => {
            State.isUserScrolling = false;
        }, 150);
    });

    // Also listen on chatMessages directly in case it's the scroll target
    if (scrollContainer !== Elements.chatMessages) {
        Elements.chatMessages.addEventListener("scroll", () => {
            updateScrollButton();
        });
    }

    if (Elements.scrollToBottomBtn) {
        Elements.scrollToBottomBtn.addEventListener('click', () => {
            scrollContainer.scrollTo({
                top: scrollContainer.scrollHeight,
                behavior: 'smooth'
            });
            Elements.chatMessages.scrollTo({
                top: Elements.chatMessages.scrollHeight,
                behavior: 'smooth'
            });
        });
    }

    Elements.themeToggle?.addEventListener("click", () => {
        document.body.classList.toggle("dark-theme");
        const isDark = document.body.classList.contains("dark-theme");
        localStorage.setItem("theme", isDark ? "dark" : "light");
    });

    Elements.quickPromptBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            Elements.messageInput.value = btn.dataset.prompt;
            Elements.messageInput.focus();
            Elements.messageInput.dispatchEvent(new Event('input'));
        });
    });

    Elements.newChatBtn.addEventListener("click", async () => {
        if (State.streamingActive) return;
        try {
            const newConv = await createNewConversation();
            State.activeConversationId = newConv.id;
            Elements.chatMessages.innerHTML = "";
            closeSidebar();
            await loadConversations();
        } catch (err) {
            showError("Failed to create new chat");
        }
    });

    if (window.visualViewport) {
        let _vpRafId = null;

        const updateInputPosition = () => {
            if (!Elements.inputArea) return;
            const keyboardHeight = window.innerHeight - window.visualViewport.height;

            if (keyboardHeight > 50) {
                Elements.inputArea.style.bottom = keyboardHeight + 'px';
            } else {
                Elements.inputArea.style.bottom = 'calc(4px + env(safe-area-inset-bottom))';
            }
        };

        const scheduleVpUpdate = () => {
            if (_vpRafId) cancelAnimationFrame(_vpRafId);
            _vpRafId = requestAnimationFrame(updateInputPosition);
        };

        window.visualViewport.addEventListener('resize', scheduleVpUpdate);
    }

    Elements.chatMessages.addEventListener('click', async (e) => {
        const actionBtn = e.target.closest('.message-action-btn');
        if (!actionBtn) return;

        const prompt = actionBtn.dataset.prompt || '';
        const action = actionBtn.dataset.action;
        if (!prompt) return;

        if (action === 'edit-prompt') {
            const messageId = actionBtn.dataset.messageId || '';
            if (!messageId || !State.activeConversationId) {
                showError("Cannot edit this message");
                return;
            }

            const messageEl = actionBtn.closest('.message');
            const messageTextEl = messageEl.querySelector('.message-text');
            const actionsEl = messageEl.querySelector('.message-actions');

            const originalHTML = messageTextEl.innerHTML;

            actionsEl.style.display = 'none';

            const editContainer = document.createElement('div');
            editContainer.className = 'edit-container';

            const textarea = document.createElement('textarea');
            textarea.className = 'edit-textarea';
            textarea.value = prompt;

            textarea.addEventListener("input", () => {
                textarea.style.height = "auto";
                textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
            });

            const btnContainer = document.createElement('div');
            btnContainer.className = 'edit-btn-container';

            const cancelBtn = document.createElement('button');
            cancelBtn.className = 'cancel-edit-btn';
            cancelBtn.textContent = 'Cancel';

            const sendBtn = document.createElement('button');
            sendBtn.className = 'send-edit-btn';
            sendBtn.textContent = 'Send';

            btnContainer.appendChild(cancelBtn);
            btnContainer.appendChild(sendBtn);

            editContainer.appendChild(textarea);
            editContainer.appendChild(btnContainer);

            messageTextEl.innerHTML = '';
            messageTextEl.appendChild(editContainer);
            messageTextEl.classList.add('editing');

            textarea.style.height = "auto";
            textarea.style.height = Math.min(textarea.scrollHeight, 200) + "px";
            textarea.focus();

            // FIX #1: Scroll edit container into view when keyboard opens
            scrollEditIntoView(editContainer);

            cancelBtn.addEventListener('click', () => {
                messageTextEl.innerHTML = originalHTML;
                messageTextEl.classList.remove('editing');
                actionsEl.style.display = 'flex';
            });

            sendBtn.addEventListener('click', () => {
                const newText = textarea.value.trim();
                if (!newText) return;

                messageTextEl.innerHTML = originalHTML;
                messageTextEl.classList.remove('editing');
                actionsEl.style.display = 'flex';

                State.editingMessageId = messageId;
                sendMessage({ message: newText, editMessageId: messageId });
            });

            return;
        }

        if (action === 'retry-prompt') {
            if (State.streamingActive) return;

            const messageEl = actionBtn.closest('.message');
            if (messageEl && messageEl.classList.contains('error')) {
                messageEl.remove();
            }

            sendMessage({ message: prompt });
            return;
        }
    });

    // Feedback Modal Event Listeners
    const closeFeedback = () => {
        if (Elements.feedbackModal) Elements.feedbackModal.classList.add('hidden');
        State.pendingFeedback = null;
    };

    Elements.closeFeedbackModal?.addEventListener('click', closeFeedback);
    Elements.cancelFeedbackBtn?.addEventListener('click', closeFeedback);

    Elements.submitFeedbackBtn?.addEventListener('click', async () => {
        if (!State.pendingFeedback) return;
        const { prompt, response, dislikeBtn, likeBtn } = State.pendingFeedback;
        const reason = Elements.feedbackReasonInput?.value.trim() || null;

        closeFeedback();

        dislikeBtn.classList.add('active');
        dislikeBtn.innerHTML = '<i class="fas fa-thumbs-down"></i><span>Not helpful</span>';
        likeBtn.disabled = true;

        await sendFeedback('dislike', prompt, response, reason);
        showSuccessToast('Thanks for your feedback!');
    });

    // Settings Modal Logic
    const openSettings = () => {
        Elements.modeRadios?.forEach(radio => {
            radio.checked = (radio.value === State.responseMode);
        });
        if (Elements.settingsModal) Elements.settingsModal.classList.remove('hidden');
        closeSidebar();
    };

    const closeSettings = () => {
        if (Elements.settingsModal) Elements.settingsModal.classList.add('hidden');
    };

    Elements.settingsBtn?.addEventListener('click', openSettings);
    Elements.closeSettingsModal?.addEventListener('click', closeSettings);

    Elements.saveSettingsBtn?.addEventListener('click', () => {
        let selectedMode = 'auto';
        Elements.modeRadios?.forEach(radio => {
            if (radio.checked) selectedMode = radio.value;
        });
        State.responseMode = selectedMode;
        localStorage.setItem('responseMode', selectedMode);
        closeSettings();
        showSuccessToast('Settings saved!');
    });
}

window.addEventListener("load", async () => {
    await PWA.init();
    initSidebar();
    initEventListeners();

    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") {
        document.body.classList.add("dark-theme");
    }

    const savedMode = localStorage.getItem("responseMode");
    if (savedMode) {
        State.responseMode = savedMode;
    }

    await loadConversations();
    Elements.messageInput?.focus();
});

const backBtn = document.getElementById('backBtn');

if (backBtn) {
    backBtn.addEventListener('click', function() {
        if (document.referrer && document.referrer.includes('deenlink.org')) {
            window.history.back();
        } else {
            window.location.href = 'https://deenlink.org/index.html';
        }
    });
}
