const API_BASE_URL = 'https://api.deenlink.org/api/v2';
const TOKEN_ENDPOINT = 'https://deenlink.org/api/auth/token_server.php';

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

async function getValidToken() {
    const now = Date.now();

    if (jwtToken && jwtExpiry && now < jwtExpiry) {
        return jwtToken;
    }

    const res = await fetch("https://deenlink.org/api/auth/token_server.php", {
        method: "POST",
        credentials: "include"
    });

    if (!res.ok) {
        const text = await res.text();
        console.error("Token server error", text);
        throw new Error("Token fetch failed");
    }

    const contentType = res.headers.get("content-type");

    if (!contentType || !contentType.includes("application/json")) {
        const text = await res.text();
        console.error("Expected JSON but got:", text);
        throw new Error("Invalid token response format");
    }

    const data = await res.json();
    jwtToken = data.token;
    jwtExpiry = now + (5 * 60 * 1000);

    return jwtToken;
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

function updateSendButtonIcon(type = 'send') {
    const icon = type === 'stop' ? 'fa-stop' : 'fa-paper-plane';
    Elements.sendButton.innerHTML = `<i class="fas ${icon}"></i>`;
}

function isNearBottom(el, threshold = 200) {
    return el.scrollHeight - el.scrollTop - el.clientHeight < threshold;
}

function isHTMLContent(str) {
    if (!str || typeof str !== 'string') return false;
    const trimmed = str.trim();
    return trimmed.startsWith('<') && trimmed.includes('</');
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
            html = DOMPurify.sanitize(marked.parse(cleaned, { async: false }), PurifyConfig);
        } catch (e) {
            html = DOMPurify.sanitize(cleaned.replace(/\n/g, '<br>'), PurifyConfig);
        }
    }

    element.innerHTML = html;
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

function createSourcesPanel(sources) {
    const panel = document.createElement('div');
    panel.className = 'sources-panel';
    const validSources = sources.filter(s => s && s.payload);
    panel.innerHTML = `
        <div class="sources-header" onclick="this.parentElement.classList.toggle('expanded')">
            <i class="fas fa-book-open"></i>
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
                                    `<span><i class="fas fa-scroll"></i> ${escapeHtml(payload.collection || 'Unknown')}</span>
                                     ${payload.hadith_number_display ? `<span><i class="fas fa-hashtag"></i> ${escapeHtml(payload.hadith_number_display)}</span>` : ''}
                                     ${payload.grade && payload.grade !== 'Unknown' ? `<span><i class="fas fa-star"></i> ${escapeHtml(payload.grade)}</span>` : ''}`
                                    :
                                    `<span><i class="fas fa-quran"></i> Surah ${escapeHtml(payload.surah_name || 'Unknown')}</span>
                                     <span><i class="fas fa-hashtag"></i> Ayah ${payload.ayah || 'Unknown'}</span>`
                                }
                            </div>
                            ${payload.english ? `<div class="source-preview">${escapeHtml(payload.english.substring(0, 100))}...</div>` : ''}
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
    const { container, textEl, feedbackDiv } = messageObj;
    container.classList.remove('streaming');
    const streamingText = textEl.querySelector('.streaming-text');
    if (streamingText) {
        streamingText.remove();
    }
    renderContent(textEl, rawContent);
    textEl.classList.add('message-text');
    void textEl.offsetHeight;
    if (textEl.querySelector('.rag-source')) {
        styleRAGSources(textEl);
    }
    if (sources && sources.length > 0) {
        const existingPanel = container.querySelector('.sources-panel');
        if (existingPanel) existingPanel.remove();
        const sourcesPanel = createSourcesPanel(sources);
        const contentDiv = container.querySelector('.message-content');
        contentDiv.appendChild(sourcesPanel);
    }
    feedbackDiv.style.display = 'flex';
    setupFeedbackButtons(feedbackDiv, textEl, container.dataset.prompt);
    if (State.autoScroll) {
        setTimeout(() => {
            Elements.chatMessages.scrollTo({
                top: Elements.chatMessages.scrollHeight,
                behavior: 'smooth'
            });
        }, 100);
    }
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

function createMessageElement(sender, text = "", incomplete = false, prompt = null) {
    const el = document.createElement("div");
    el.className = `message ${sender}`;
    if (prompt) el.dataset.prompt = prompt;
    el.dataset.incomplete = incomplete ? "true" : "false";
    el.dataset.raw = text || "";
    el.dataset.messageId = Date.now().toString(36) + Math.random().toString(36).substr(2);

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";

    const textDiv = document.createElement("div");
    textDiv.className = "message-text";

    if (sender === "user") {
        textDiv.textContent = text;
        textDiv.style.cssText = `
            background: var(--user-bg);
            color: var(--user-text);
            padding: 10px 14px;
            font-size: 14px;
            line-height: 1.5;
            word-break: break-word;
            overflow-wrap: break-word;
            white-space: pre-wrap;
            border-radius: 18px;
            border-bottom-right-radius: 6px;
            width: fit-content;
            max-width: 100%;
            display: inline-block;
        `;
    } else {
        if (isHTMLContent(text)) {
            textDiv.innerHTML = DOMPurify.sanitize(text, PurifyConfig);
            setTimeout(() => styleRAGSources(textDiv), 10);
        } else {
            textDiv.innerHTML = DOMPurify.sanitize(marked.parse(text, { async: false }), PurifyConfig);
        }
    }

    contentDiv.appendChild(textDiv);
    if (sender === "ai" && !incomplete) {
        const feedbackButtons = createFeedbackButtons(contentDiv);
        contentDiv.appendChild(feedbackButtons);
    }

    el.appendChild(contentDiv);
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

function appendMessage(sender, text) {
    const shouldScroll = isNearBottom(Elements.chatMessages);
    const el = document.createElement("div");
    el.className = `message ${sender}`;
    el.dataset.messageId = Date.now().toString(36) + Math.random().toString(36).substr(2);
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
        const prompt = msgContainer?.dataset.prompt || msgContainer?.previousElementSibling?.querySelector('.message-text')?.innerText || '';
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
    return feedbackDiv;
}

async function sendFeedback(type, prompt, response) {
    try {
        const token = await getValidToken();
        const feedbackData = {
            type,
            prompt,
            response,
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
        appendMessage(msg.role === "user" ? "user" : "ai", msg.content);
    });
    Elements.chatMessages.scrollTop = Elements.chatMessages.scrollHeight;
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

// FIXED: Removed ALL inline styles - let CSS handle everything
function styleRAGSources(el) {
    if (!el) return;
    const sources = el.querySelectorAll('.rag-source');
    const totalSources = sources.length;
    
    sources.forEach((source, index) => {
        // Only add badge for multiple sources
        if (totalSources > 1) {
            let badge = source.querySelector('.source-badge');
            if (!badge) {
                badge = document.createElement('div');
                badge.className = 'source-badge';
                source.insertBefore(badge, source.firstChild);
            }
            badge.textContent = `${index + 1}/${totalSources}`;
        }
        
        // Remove any existing inline styles that might conflict
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
                conversation_id: State.activeConversationId
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
                            // FIXED: Use faster typing effect - no delay between tokens
                            await streamTokenWithTypingEffect(aiMessageEl, content);
                        }
                        break;

                    case 'error':
                        throw new Error(data.message || "Stream error");

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
            const errorMsg = `**Error:** ${err.message}. [Click to retry]`;
            const errorDiv = createMessageElement("ai", errorMsg, true, text);
            errorDiv.dataset.prompt = text;
        }
    } finally {
        resetInputState();
    }
}

// FIXED: Removed duplicate definition, faster typing to prevent cursor blink delay
async function streamTokenWithTypingEffect(element, token) {
    if (!element) return;
    
    const chars = token.split('');
    
    for (let i = 0; i < chars.length; i++) {
        if (!State.streamingActive) break;
        
        element.textContent += chars[i];
        
        // FASTER typing - reduced delays to prevent visible pauses
        let delay = 5; // Reduced from 15
        if (chars[i] === '.' || chars[i] === '!' || chars[i] === '?') delay = 40; // Reduced from 120
        else if (chars[i] === ',' || chars[i] === ';') delay = 15; // Reduced from 50
        else if (chars[i] === ' ') delay = 2; // Reduced from 8
        
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

function initEventListeners() {
    Elements.sendButton.addEventListener("click", () => {
        if (State.streamingActive && State.streamController) {
            stopGeneration();
        } else {
            sendMessage();
        }
    });

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

    Elements.chatMessages.addEventListener("scroll", () => {
        if (State.scrollTimeout) clearTimeout(State.scrollTimeout);

        const distanceFromBottom = Elements.chatMessages.scrollHeight -
            Elements.chatMessages.scrollTop -
            Elements.chatMessages.clientHeight;

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
        window.visualViewport.addEventListener("resize", () => {
            const keyboardHeight = window.innerHeight - window.visualViewport.height;
            if (keyboardHeight > 150) {
                Elements.inputArea.style.bottom = keyboardHeight + 16 + "px";
                setTimeout(() => {
                    Elements.chatMessages.scrollTop = Elements.chatMessages.scrollHeight;
                }, 100);
            } else {
                Elements.inputArea.style.bottom = "calc(18px + env(safe-area-inset-bottom))";
            }
        });
    }
}

window.addEventListener("load", async () => {
    await PWA.init();
    initSidebar();
    initEventListeners();

    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") {
        document.body.classList.add("dark-theme");
    }

    await loadConversations();
    Elements.messageInput?.focus();
});