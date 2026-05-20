const API_BASE_URL = 'https://api.deenlink.org/api/v2';
const TOKEN_ENDPOINT = 'https://deenlink.org/api/auth/ai_token.php';
const AI_AVATAR_SRC = '../img/deenlink-ai.jpg';

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
    responseLang: 'en',
    userProfile: null,
    queryModule: null,
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
    modeRadios: document.querySelectorAll("input[name='responseMode']"),
    scrollToBottomBtn: document.getElementById("scrollToBottomBtn"),
    micBtn: document.getElementById("micBtn"),
    modulesBtn: document.getElementById("modulesBtn"),
    modulesPopup: document.getElementById("modulesPopup")
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

/* ─── helpers ─────────────────────────────────────────────── */

/**
 * Build the small logo <img> that sits to the left of every AI bubble.
 */
function createAiAvatarEl() {
    const img = document.createElement('img');
    img.src = AI_AVATAR_SRC;
    img.alt = 'DeenLink AI';
    img.className = 'ai-avatar';
    img.onerror = function () { this.style.display = 'none'; };
    return img;
}

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

async function fetchUserProfile() {
    try {
        const token = await getValidToken();
        const res = await fetchWithRetry(`${API_BASE_URL}/user/me`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        if (!res.ok) return;

        const data = await res.json();
        //console.log('[Profile]', data);

        const displayName = data.full_name || data.name || data.username || 'Guest';

        const userNameDisplay = document.getElementById("userNameDisplay");
        if (userNameDisplay) userNameDisplay.textContent = displayName;

        const settingsName = document.getElementById('settingsProfileName');
        if (settingsName) settingsName.textContent = displayName;

        const settingsSub = document.getElementById('settingsProfileSub');
        if (settingsSub) settingsSub.textContent = data.email || 'DeenLink Member';

        const rawAvatar = data.profile_image
            || data.avatar_url
            || data.profile_picture
            || data.photo
            || null;

        const avatarEl = document.getElementById('settingsProfileAvatar');
        if (avatarEl && rawAvatar) {
            let fullAvatarUrl;
            if (rawAvatar.startsWith('http://') || rawAvatar.startsWith('https://')) {
                fullAvatarUrl = rawAvatar;
            } else {
                const filename = rawAvatar.split('/').pop();
                fullAvatarUrl = `https://deenlink.org/uploads/profile/${filename}`;
            }

            console.log('[Profile] avatar URL:', fullAvatarUrl);

            const img = document.createElement('img');
            img.src = fullAvatarUrl;
            img.alt = displayName;
            img.style.cssText = 'width:100%;height:100%;border-radius:50%;object-fit:cover;';
            img.onerror = function () {
                avatarEl.innerHTML = '';
                const icon = document.createElement('i');
                icon.className = 'fas fa-user-circle';
                avatarEl.appendChild(icon);
            };
            avatarEl.innerHTML = '';
            avatarEl.appendChild(img);
        }

        State.userProfile = data;

    } catch (e) {
        console.warn("Could not fetch user profile", e);
    }
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

    if (msg.includes("message not found") || msg.includes("message_not_found")) {
        return null;
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

function cleanMarkdownOutput(rawContent) {
    return rawContent
        .replace(/^[ \t]+(?=[^\s])/gm, '')
        .replace(/\n{3,}/g, '\n\n')
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
            const cleanedForMd = cleanMarkdownOutput(rawContent);
            html = DOMPurify.sanitize(marked.parse(cleanedForMd, { async: false }), PurifyConfig);
        } catch (e) {
            html = DOMPurify.sanitize(rawContent.replace(/\n/g, '<br>'), PurifyConfig);
        }
    }

    element.innerHTML = html;

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

function showSearchIndicator(text = "Searching knowledge base...", iconType = "database") {
    removeSearchIndicator();
    removeTypingIndicator();
    const indicator = document.createElement('div');
    indicator.className = 'search-indicator';
    indicator.id = 'searchIndicator';

    let iconHtml = '<div class="search-spinner"></div>';
    if (iconType === "web") {
        iconHtml = '<i class="fas fa-globe search-spinner-icon" style="animation: spin 2s linear infinite; margin-right: 8px;"></i>';
    }

    indicator.innerHTML = `
        <div class="search-indicator-content">
            ${iconHtml}
            <span class="search-text">${text}</span>
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
    // Keep ALL valid sources — never discard any
    if (!sources || sources.length === 0) return sources;
    return sources.filter(s => s && s.payload);
}

/* ── Source persistence helpers ──────────────────────────────
   Sources are saved to localStorage keyed by messageId so they
   survive page refresh (issue #8).
   ────────────────────────────────────────────────────────── */
function _sourcesKey(messageId) { return `deen_sources_${messageId}`; }

function persistSources(messageId, sources) {
    if (!messageId || !sources || !sources.length) return;
    try {
        localStorage.setItem(_sourcesKey(messageId), JSON.stringify(sources));
    } catch {}
}

function restoreSources(messageId) {
    try {
        const raw = localStorage.getItem(_sourcesKey(messageId));
        return raw ? JSON.parse(raw) : null;
    } catch { return null; }
}

function createSourcesPanel(sources) {
    const panel = document.createElement('div');
    panel.className = 'sources-panel';
    const validSources = sources.filter(s => s && s.payload);
    if (!validSources.length) return panel;

    // ─── Pill button ──────────────────────────────────────────────────
    const pillBtn = document.createElement('button');
    pillBtn.className = 'sources-pill-btn';

    const pillIcons = document.createElement('span');
    pillIcons.className = 'sources-pill-icons';
    validSources.slice(0, 3).forEach(src => {
        const wrap = document.createElement('span');
        wrap.className = 'sources-pill-icon';
        if (src.source_type === 'web' && src.payload?.url) {
            let h = '';
            try { h = new URL(src.payload.url).hostname; } catch {}
            const img = document.createElement('img');
            img.src = `https://www.google.com/s2/favicons?domain=${h}&sz=32`;
            img.alt = '';
            img.onerror = function () {
                const i = document.createElement('i');
                i.className = 'fas fa-globe';
                this.parentElement.replaceChildren(i);
            };
            wrap.appendChild(img);
        } else {
            const i = document.createElement('i');
            i.className = src.source_type === 'hadith' ? 'fas fa-book' : 'fas fa-quran';
            wrap.appendChild(i);
        }
        pillIcons.appendChild(wrap);
    });

    const pillLabel = document.createElement('span');
    pillLabel.textContent = `${validSources.length} source${validSources.length > 1 ? 's' : ''}`;

    const chevron = document.createElement('i');
    chevron.className = 'fas fa-chevron-down';
    chevron.style.cssText = 'font-size:10px;margin-left:4px;opacity:0.6;';

    pillBtn.appendChild(pillIcons);
    pillBtn.appendChild(pillLabel);
    pillBtn.appendChild(chevron);

    // ─── Expanded list ────────────────────────────────────────────────
    const expandedList = document.createElement('div');
    expandedList.className = 'sources-expanded-list';

    validSources.forEach(src => {
        const payload = src.payload || {};
        const isHadith = src.source_type === 'hadith';
        const isWeb = src.source_type === 'web';

        let title = '', meta = '', preview = '', hostname = '';

        if (isWeb) {
            try { hostname = new URL(payload.url || '').hostname.replace('www.', ''); } catch {}
            title   = payload.title || hostname || 'Web Source';
            meta    = hostname;
            preview = payload.snippet || '';
        } else if (src.display_reference) {
            title   = src.display_reference;
            preview = payload.english || '';
        } else if (isHadith) {
            title   = `${payload.collection || 'Hadith'} ${payload.hadith_number_display || ''}`.trim();
            meta    = payload.collection || '';
            preview = payload.english || '';
        } else {
            title   = (payload.surah_name && payload.ayah) ? `${payload.surah_name} — Ayah ${payload.ayah}` : "Qur'an";
            meta    = payload.surah_name || '';
            preview = payload.english || '';
        }

        const item = (isWeb && payload.url) ? document.createElement('a') : document.createElement('div');
        item.className = 'source-list-item';
        if (isWeb && payload.url) { item.href = payload.url; item.target = '_blank'; item.rel = 'noopener noreferrer'; }

        // icon box
        const iconBox = document.createElement('div');
        iconBox.className = 'source-list-icon';
        if (isWeb) {
            const img = document.createElement('img');
            img.src = `https://www.google.com/s2/favicons?domain=${hostname}&sz=32`;
            img.alt = '';
            img.onerror = function () {
                const i = document.createElement('i'); i.className = 'fas fa-globe';
                this.parentElement.replaceChildren(i);
            };
            iconBox.appendChild(img);
        } else {
            const i = document.createElement('i');
            i.className = isHadith ? 'fas fa-book' : 'fas fa-quran';
            iconBox.appendChild(i);
        }

        // body text
        const body = document.createElement('div');
        body.className = 'source-list-body';

        const titleEl = document.createElement('div');
        titleEl.className = 'source-list-title';
        titleEl.textContent = title;
        body.appendChild(titleEl);

        if (meta) {
            const metaEl = document.createElement('div');
            metaEl.className = 'source-list-meta';
            metaEl.textContent = meta;
            body.appendChild(metaEl);
        }

        // Arabic — full, no truncation
        if (payload.arabic && !isWeb) {
            const ar = document.createElement('div');
            ar.className = 'rag-arabic';
            ar.dir = 'rtl';
            ar.style.cssText = 'font-size:13px;margin-top:6px;white-space:normal;word-break:break-word;line-height:1.9;';
            ar.textContent = payload.arabic;   // textContent = no escaping issues
            body.appendChild(ar);
        }

        if (preview) {
            const prev = document.createElement('div');
            prev.className = 'source-list-preview';
            prev.textContent = preview;        // textContent = no escaping issues
            body.appendChild(prev);
        }

        item.appendChild(iconBox);
        item.appendChild(body);
        expandedList.appendChild(item);
    });

    pillBtn.addEventListener('click', () => {
        const open = expandedList.classList.toggle('visible');
        chevron.className = open ? 'fas fa-chevron-up' : 'fas fa-chevron-down';
        chevron.style.cssText = 'font-size:10px;margin-left:4px;opacity:0.6;';
    });

    panel.appendChild(pillBtn);
    panel.appendChild(expandedList);
    return panel;
}

/* ─── MESSAGE CREATION — all AI messages now include the logo avatar ─── */

function createStreamingMessage() {
    const messageDiv = document.createElement('div');
    messageDiv.className = 'message ai streaming';
    // Pre-assign an id so sources can be keyed to this message immediately
    messageDiv.dataset.messageId = Date.now().toString(36) + Math.random().toString(36).substr(2);

    // ── DeenLink logo avatar ──
    messageDiv.appendChild(createAiAvatarEl());

    messageDiv.innerHTML += `
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

    if (sources && sources.length > 0) {
        const validSources = filterBestSources(sources);
        const existingPanel = container.querySelector('.sources-panel');
        if (existingPanel) existingPanel.remove();
        const sourcesPanel = createSourcesPanel(validSources);
        contentDiv.appendChild(sourcesPanel);
        // Persist so they survive a page refresh (issue #8)
        const msgId = container.dataset.messageId || container.dataset.aiMessageId;
        if (msgId) persistSources(msgId, validSources);
    }

    if (feedbackDiv) {
        feedbackDiv.style.display = 'flex';
        setupFeedbackButtons(feedbackDiv, textEl, container.dataset.prompt);
    } else {
        feedbackDiv = createFeedbackButtons(contentDiv);
        feedbackDiv.style.display = 'flex';
        contentDiv.appendChild(feedbackDiv);
    }

    // Notify user if page is in background (issue #5)
    _notifyAIDone(textEl?.innerText || '');

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

    // ── DeenLink logo avatar (AI only) ──
    if (sender === 'ai') {
        el.appendChild(createAiAvatarEl());
    }

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

    // ── DeenLink logo avatar ──
    el.appendChild(createAiAvatarEl());

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    contentDiv.innerHTML = `
        <div class="message-text"></div>
        <div class="typing-indicator">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
        </div>
    `;
    el.appendChild(contentDiv);

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

function updateEmptyStateVisibility() {
    const emptyGreeting = document.getElementById("emptyChatGreeting");
    const quickPrompts = document.getElementById("quickPrompts");

    const hasMessages = Array.from(Elements.chatMessages.children).some(
        child => !child.classList.contains("loading-state") && !child.id.includes("Indicator")
    );

    if (hasMessages) {
        if (emptyGreeting) emptyGreeting.style.display = 'none';
        if (quickPrompts) quickPrompts.style.display = 'none';
    } else {
        if (emptyGreeting) emptyGreeting.style.display = 'flex';
        if (quickPrompts) quickPrompts.style.display = 'flex';
    }
}

function appendMessage(sender, text, options = {}) {
    const { messageId = null, sources = null } = options;
    const shouldScroll = isNearBottom(Elements.chatMessages);
    const el = document.createElement("div");
    el.className = `message ${sender}`;
    const mid = messageId || Date.now().toString(36) + Math.random().toString(36).substr(2);
    el.dataset.messageId = mid;

    if (sender === 'ai') el.appendChild(createAiAvatarEl());

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";
    const textDiv = document.createElement("div");
    textDiv.className = "message-text";
    textDiv.dataset.raw = text;

    if (sender === 'user') {
        textDiv.textContent = text;
    } else {
        renderContent(textDiv, text);
        void textDiv.offsetHeight;
        setTimeout(() => { styleRAGSources(textDiv); }, 10);
    }

    contentDiv.appendChild(textDiv);

    if (sender === 'ai') {
        const savedSources = sources || restoreSources(mid);
        if (savedSources && savedSources.length > 0) {
            contentDiv.appendChild(createSourcesPanel(savedSources));
        }
        contentDiv.appendChild(createFeedbackButtons(contentDiv));
    }
    el.appendChild(contentDiv);
    if (sender === 'user') createUserMessageActions(el, text, mid);

    Elements.chatMessages.appendChild(el);
    if (shouldScroll) Elements.chatMessages.scrollTop = Elements.chatMessages.scrollHeight;
    updateEmptyStateVisibility();
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
            { messageId: msg.id || null, sources: msg.sources || null }
        );
    });

    updateEmptyStateVisibility();

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
        } catch (_) {}
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
    const jsonRes = await res.json();
    updateEmptyStateVisibility();
    return jsonRes;
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
}

async function sendMessage(retryData = null) {
    if (State.streamingActive) {
        showError("Already processing a message");
        return;
    }

    State.streamingActive = true;
    updateSendButtonIcon('stop');
    Elements.messageInput.disabled = true;

    let text = "";
    if (typeof retryData === 'string') {
        text = retryData;
    } else {
        text = retryData?.message ?? Elements.messageInput.value.trim();
    }
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

    if (editingMessageId && State.activeConversationId) {
        try {
            await editConversationFromMessage(State.activeConversationId, editingMessageId, text);
        } catch (err) {
            const friendlyErr = getUserFriendlyError(err?.message);
            if (friendlyErr !== null) {
                State.editingMessageId = null;
                resetInputState();
                showError(friendlyErr || "Failed to edit message");
                return;
            }
            console.warn('Edit: message not found, sending as new message');
        }
        State.editingMessageId = null;
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
                message: State.queryModule && MODULE_CONFIG[State.queryModule]?.prefix
                    ? MODULE_CONFIG[State.queryModule].prefix + text
                    : text,
                conversation_id: State.activeConversationId,
                mode: State.queryModule === 'chat' ? 'chat'
                    : State.queryModule === 'books' ? 'rag'
                    : State.responseMode,
                response_language: State.responseLang || localStorage.getItem('deenLang') || 'en',
                client_datetime: new Date().toLocaleString('en-GB', {
                    weekday:'long', year:'numeric', month:'long',
                    day:'numeric', hour:'2-digit', minute:'2-digit', second:'2-digit', hour12: true
                }),
                client_timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || ""
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
                    case 'intent_selection':
                        removeSearchIndicator();
                        removeTypingIndicator();
                        
                        const selectionContainer = document.createElement('div');
                        selectionContainer.className = 'intent-selection-container';
                        selectionContainer.style.cssText = 'display:flex;flex-direction:column;gap:12px;margin:12px 0;width:100%;';

                        const promptText = document.createElement('p');
                        promptText.textContent = 'Please choose a category to receive the response from:';
                        promptText.style.cssText = 'margin:0;font-weight:600;font-size:14px;color:var(--text-dark);';
                        selectionContainer.appendChild(promptText);

                        const cardsGrid = document.createElement('div');
                        cardsGrid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit, minmax(130px, 1fr));gap:10px;width:100%;';

                        data.options.forEach(opt => {
                            const card = document.createElement('button');
                            card.type = 'button';
                            card.style.cssText = `
                                display:flex;
                                flex-direction:column;
                                align-items:center;
                                justify-content:center;
                                gap:8px;
                                padding:16px;
                                background:var(--ai-bg);
                                border:1px solid rgba(29,111,66,0.15);
                                border-radius:12px;
                                cursor:pointer;
                                transition:all 0.2s ease;
                                text-align:center;
                            `;
                            card.innerHTML = `
                                <span style="font-size:24px;">${opt.icon}</span>
                                <span style="font-size:13px;font-weight:600;color:var(--text-dark);">${opt.label}</span>
                            `;
                            
                            card.addEventListener('mouseenter', () => {
                                card.style.transform = 'translateY(-2px)';
                                card.style.boxShadow = '0 4px 12px rgba(29, 111, 66, 0.1)';
                                card.style.borderColor = 'rgba(29,111,66,0.4)';
                            });
                            card.addEventListener('mouseleave', () => {
                                card.style.transform = 'none';
                                card.style.boxShadow = 'none';
                                card.style.borderColor = 'rgba(29,111,66,0.15)';
                            });

                            card.addEventListener('click', () => {
                                _applyModule(opt.id);
                                streamingMsg.container.remove();
                                sendMessage(streamingMsg.container.dataset.prompt);
                            });

                            cardsGrid.appendChild(card);
                        });

                        selectionContainer.appendChild(cardsGrid);
                        
                        streamingMsg.container.style.display = 'flex';
                        aiMessageEl.innerHTML = '';
                        aiMessageEl.appendChild(selectionContainer);
                        
                        completed = true;
                        return;

                    case 'search_start':
                        showSearchIndicator();
                        break;

                    case 'web_search_start':
                        showSearchIndicator("Getting info from the internet...", "web");
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

                    case 'memory_updated':
                        if (data.action === "add" || data.action === "update") {
                            showMemoryUpdatedInline(data.fact);
                        }
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
        if (isCapacitor) return;
        if (!('serviceWorker' in navigator)) return;
        try {
            await navigator.serviceWorker.register('sw.js', { scope: './' });
        } catch (error) {}
    }
};

function scrollEditIntoView(editContainer) {
    // Use a short delay so the keyboard finishes animating first.
    // We scroll the *messages area* div — NOT document.scrollIntoView —
    // because scrollIntoView triggers a page-level scroll that confuses the
    // visualViewport handler and is the root cause of the "bar jumps to
    // middle of screen" bug.
    setTimeout(() => {
        const messagesArea = Elements.chatMessages.closest('.messages-area')
            || Elements.chatMessages.parentElement;
        if (!messagesArea) return;

        const containerRect = editContainer.getBoundingClientRect();
        const areaRect = messagesArea.getBoundingClientRect();

        if (containerRect.bottom > areaRect.bottom - 60) {
            messagesArea.scrollTop += (containerRect.bottom - areaRect.bottom + 80);
        }
    }, 400);
}

function initEventListeners() {
    Elements.sendButton.addEventListener("click", () => {
        if (State.streamingActive && State.streamController) {
            stopGeneration();
        } else {
            sendMessage();
        }
    });

    Elements.modulesBtn?.addEventListener('click', (e) => {
        if (e.target.closest('.module-pill-close')) return;
        e.stopPropagation();
        Elements.modulesPopup?.classList.toggle('hidden');
    });

    document.querySelectorAll('.module-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            _applyModule(btn.dataset.module);
        });
    });

    document.addEventListener('click', (e) => {
        if (!Elements.modulesPopup || Elements.modulesPopup.classList.contains('hidden')) return;
        if (!Elements.modulesPopup.contains(e.target) && e.target !== Elements.modulesBtn && !Elements.modulesBtn?.contains(e.target)) {
            Elements.modulesPopup.classList.add('hidden');
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

    const messagesArea = Elements.chatMessages.closest('.messages-area') || Elements.chatMessages.parentElement;
    const scrollContainer = messagesArea || Elements.chatMessages;

    const updateScrollButton = () => {
        if (!Elements.scrollToBottomBtn) return;
        const distanceFromBottom = scrollContainer.scrollHeight -
            scrollContainer.scrollTop -
            scrollContainer.clientHeight;

        if (distanceFromBottom > 250) {
            Elements.scrollToBottomBtn.classList.remove('hidden');
            Elements.scrollToBottomBtn.classList.add('visible');
        } else {
            Elements.scrollToBottomBtn.classList.add('hidden');
            Elements.scrollToBottomBtn.classList.remove('visible');
        }
    };

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

    if (scrollContainer !== Elements.chatMessages) {
        Elements.chatMessages.addEventListener("scroll", () => {
            updateScrollButton();
        });
    }

    if (Elements.scrollToBottomBtn) {
        Elements.scrollToBottomBtn.addEventListener('click', () => {
            scrollContainer.scrollTo({ top: scrollContainer.scrollHeight, behavior: 'smooth' });
            Elements.chatMessages.scrollTo({ top: Elements.chatMessages.scrollHeight, behavior: 'smooth' });
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
            _clearModule(); // reset module on new chat
            updateEmptyStateVisibility();
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
            const vv = window.visualViewport;
            // offsetTop accounts for any visual-viewport scroll (e.g. browser chrome shrink)
            const keyboardHeight = window.innerHeight - vv.height - (vv.offsetTop || 0);

            if (keyboardHeight > 50) {
                // Pin input bar just above the keyboard.
                // Clamp to 45% of the visible viewport so it NEVER drifts to the
                // centre of the screen (the old bug was bare keyboardHeight which
                // can exceed half the screen on small devices).
                const maxBottom = Math.floor(vv.height * 0.45);
                const targetBottom = Math.min(keyboardHeight + 4, maxBottom);
                Elements.inputArea.style.bottom = targetBottom + 'px';
            } else {
                Elements.inputArea.style.bottom = 'calc(16px + env(safe-area-inset-bottom))';
            }
        };

        const scheduleVpUpdate = () => {
            if (_vpRafId) cancelAnimationFrame(_vpRafId);
            _vpRafId = requestAnimationFrame(updateInputPosition);
        };

        window.visualViewport.addEventListener('resize', scheduleVpUpdate);
        window.visualViewport.addEventListener('scroll', scheduleVpUpdate);
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

    const settingsModal = Elements.settingsModal;

    function showSettingsPage(pageId) {
        settingsModal?.querySelectorAll('.settings-page').forEach(p => p.classList.add('hidden'));
        document.getElementById(pageId)?.classList.remove('hidden');
    }

    function closeSettings() {
        settingsModal?.classList.add('hidden');
        showSettingsPage('settingsPageMain');
    }

    Elements.settingsBtn?.addEventListener('click', () => {
        Elements.modeRadios?.forEach(r => { r.checked = (r.value === State.responseMode); });

        // Populate profile card from cache
        const profile = State.userProfile || {};
        const displayName = profile.full_name || profile.name || profile.username
            || document.getElementById('userNameDisplay')?.textContent || 'Guest';

        const nameEl = document.getElementById('settingsProfileName');
        if (nameEl) nameEl.textContent = displayName;

        const subEl = document.getElementById('settingsProfileSub');
        if (subEl) subEl.textContent = profile.email || 'DeenLink Member';

        // Re-render avatar using DOM (not innerHTML) to avoid escaping bugs
        const avatarEl = document.getElementById('settingsProfileAvatar');
        const rawAvatar = profile.profile_image || profile.avatar_url
            || profile.profile_picture || profile.photo || null;

        if (avatarEl && rawAvatar) {
            let fullAvatarUrl;
            if (rawAvatar.startsWith('http://') || rawAvatar.startsWith('https://')) {
                fullAvatarUrl = rawAvatar;
            } else {
                const filename = rawAvatar.split('/').pop();
                fullAvatarUrl = `https://deenlink.org/uploads/profile/${filename}`;
            }
            const img = document.createElement('img');
            img.src = fullAvatarUrl;
            img.alt = displayName;
            img.style.cssText = 'width:100%;height:100%;border-radius:50%;object-fit:cover;';
            img.onerror = function () {
                avatarEl.innerHTML = '';
                const icon = document.createElement('i');
                icon.className = 'fas fa-user-circle';
                avatarEl.appendChild(icon);
            };
            avatarEl.innerHTML = '';
            avatarEl.appendChild(img);
        }

        // Notification toggle state
        const toggle = document.getElementById('toggleAINotif');
        if (toggle) toggle.checked = (localStorage.getItem('deen_notif_ai_done') === 'true');

        settingsModal?.classList.remove('hidden');
        showSettingsPage('settingsPageMain');
        closeSidebar();
    });
    ['closeSettingsModal','closeSettingsFromPersonalization','closeSettingsFromMemory','closeSettingsFromManageMemory','closeSettingsFromMode'].forEach(id => {
        document.getElementById(id)?.addEventListener('click', closeSettings);
    });

    document.getElementById('saveSettingsBtn')?.addEventListener('click', () => {
        let selectedMode = 'auto';
        Elements.modeRadios?.forEach(r => { if (r.checked) selectedMode = r.value; });
        State.responseMode = selectedMode;
        localStorage.setItem('responseMode', selectedMode);
        closeSettings();
        showSuccessToast('Settings saved!');
    });

    document.getElementById('saveSettingsModeBtn')?.addEventListener('click', () => {
        let selectedMode = 'auto';
        Elements.modeRadios?.forEach(r => { if (r.checked) selectedMode = r.value; });
        State.responseMode = selectedMode;
        localStorage.setItem('responseMode', selectedMode);
        showSuccessToast('Response mode saved!');
        showSettingsPage('settingsPageMain');
    });

    document.getElementById('navToPersonalization')?.addEventListener('click', () => showSettingsPage('settingsPagePersonalization'));
    document.getElementById('navToMode')?.addEventListener('click', () => showSettingsPage('settingsPageMode'));
    document.getElementById('navToMemory')?.addEventListener('click', () => showSettingsPage('settingsPageMemory'));
    document.getElementById('navToManageMemory')?.addEventListener('click', () => {
        showSettingsPage('settingsPageManageMemory');
        loadMemoriesIntoPage();
    });
    document.getElementById('navToAppearance')?.addEventListener('click', () => {
        // Sync slider to current font size
        const sz = parseInt(localStorage.getItem('deenFontSize') || '15');
        const slider = document.getElementById('fontSizeSlider');
        const preview = document.getElementById('fontSizePreview');
        if (slider) { slider.value = sz; }
        if (preview) preview.textContent = sz + 'px';
        showSettingsPage('settingsPageAppearance');
    });
    document.getElementById('navToLanguage')?.addEventListener('click', () => {
        const lang = localStorage.getItem('deenLang') || 'en';
        const tr = localStorage.getItem('deenQuranTr') || 'sahih';
        const langSel = document.getElementById('responseLangSelect');
        const trSel = document.getElementById('quranTranslationSelect');
        if (langSel) langSel.value = lang;
        if (trSel) trSel.value = tr;
        showSettingsPage('settingsPageLanguage');
    });
    document.getElementById('navToNotifications')?.addEventListener('click', () => showSettingsPage('settingsPageNotifications'));

    // Font size live preview
    document.getElementById('fontSizeSlider')?.addEventListener('input', (e) => {
        const sz = e.target.value;
        const preview = document.getElementById('fontSizePreview');
        if (preview) preview.textContent = sz + 'px';
    });

    // Save appearance
    document.getElementById('saveAppearanceBtn')?.addEventListener('click', () => {
        const sz = document.getElementById('fontSizeSlider')?.value || '15';
        document.documentElement.style.setProperty('--chat-font-size', sz + 'px');
        localStorage.setItem('deenFontSize', sz);
        showSuccessToast('Appearance saved!');
        closeSettings();
    });

    // Theme buttons inside appearance page
    document.getElementById('themeLight')?.addEventListener('click', () => {
        document.body.classList.remove('dark-theme');
        localStorage.setItem('theme', 'light');
    });
    document.getElementById('themeDark')?.addEventListener('click', () => {
        document.body.classList.add('dark-theme');
        localStorage.setItem('theme', 'dark');
    });
    document.getElementById('themeSystem')?.addEventListener('click', () => {
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        document.body.classList.toggle('dark-theme', prefersDark);
        localStorage.setItem('theme', 'system');
    });

    // Save language
    document.getElementById('saveLanguageBtn')?.addEventListener('click', () => {
        const lang = document.getElementById('responseLangSelect')?.value || 'en';
        const tr = document.getElementById('quranTranslationSelect')?.value || 'sahih';
        localStorage.setItem('deenLang', lang);
        localStorage.setItem('deenQuranTr', tr);
        State.responseLang = lang;
        showSuccessToast('Language preferences saved!');
        closeSettings();
    });

    // Save notifications
    document.getElementById('saveNotificationsBtn')?.addEventListener('click', () => {
        const aiNotif = document.getElementById('toggleAINotif')?.checked || false;
        localStorage.setItem('deen_notif_ai_done', aiNotif);

        if (aiNotif && Notification.permission !== 'granted') {
            Notification.requestPermission().then(permission => {
                if (permission !== 'granted') {
                    const note = document.getElementById('notifPermissionNote');
                    if (note) note.style.display = 'block';
                }
            });
        }
        showSuccessToast('Notification preferences saved!');
        closeSettings();
    });

    document.getElementById('backFromPersonalization')?.addEventListener('click', () => showSettingsPage('settingsPageMain'));
    document.getElementById('backFromMemory')?.addEventListener('click', () => showSettingsPage('settingsPagePersonalization'));
    document.getElementById('backFromManageMemory')?.addEventListener('click', () => showSettingsPage('settingsPageMemory'));
    document.getElementById('backFromMode')?.addEventListener('click', () => showSettingsPage('settingsPageMain'));
    document.getElementById('backFromAppearance')?.addEventListener('click', () => showSettingsPage('settingsPagePersonalization'));
    document.getElementById('backFromLanguage')?.addEventListener('click', () => showSettingsPage('settingsPagePersonalization'));
    document.getElementById('backFromNotifications')?.addEventListener('click', () => showSettingsPage('settingsPagePersonalization'));

    // Close buttons on all pages (add new ones)
    ['closeSettingsModal','closeSettingsFromPersonalization','closeSettingsFromMemory',
     'closeSettingsFromManageMemory','closeSettingsFromMode','closeSettingsFromAppearance',
     'closeSettingsFromLanguage','closeSettingsFromNotifications'].forEach(id => {
        document.getElementById(id)?.addEventListener('click', closeSettings);
    });

    document.getElementById('settingsOverlay')?.addEventListener('click', closeSettings);

    document.getElementById('clearMemoriesBtn')?.addEventListener('click', async () => {
        if (!confirm("Clear all your memories? This cannot be undone.")) return;
        try {
            const token = await getValidToken();
            const res = await fetch(`${API_BASE_URL}/user/memories`, { method: 'DELETE', headers: { "Authorization": `Bearer ${token}` } });
            if (res.ok) {
                Object.keys(localStorage).filter(k => k.startsWith('deen_memory_notices_')).forEach(k => localStorage.removeItem(k));
                showSuccessToast("All memories cleared.");
                showSettingsPage('settingsPageMemory');
            }
        } catch { showError("Failed to clear memories"); }
    });
}

async function loadMemoriesIntoPage() {
    const loading = document.getElementById('memoriesListLoading');
    const ul = document.getElementById('memoriesList');
    const empty = document.getElementById('memoriesEmpty');
    if (!ul) return;

    ul.innerHTML = '';
    if (empty) empty.classList.add('hidden');
    if (loading) { loading.style.display = 'block'; }

    try {
        const token = await getValidToken();
        const res = await fetch(`${API_BASE_URL}/user/memories`, { headers: { "Authorization": `Bearer ${token}` } });
        if (!res.ok) throw new Error("Failed to fetch memories");
        const memories = await res.json();

        if (loading) loading.style.display = 'none';

        if (!memories.length) {
            if (empty) empty.classList.remove('hidden');
            return;
        }

        memories.forEach(m => {
            const li = document.createElement('li');
            li.className = 'memory-item-gpt';
            li.dataset.memoryId = m.id;

            const convId = m.conversation_id || m.conv_id || null;
            const chatLinkHtml = convId
                ? `Saved from a <a class="memory-chat-link" data-conv-id="${convId}" href="#">chat</a>`
                : `Saved by DeenLink AI`;

            li.innerHTML = `
                <div class="memory-item-gpt-body">
                    <div class="memory-item-gpt-fact">${escapeHtml(m.fact)}</div>
                    <div class="memory-item-gpt-meta">${chatLinkHtml}</div>
                </div>
                <button class="memory-item-menu-btn" title="Options">⋯</button>
            `;

            li.querySelector('.memory-chat-link')?.addEventListener('click', async (e) => {
                e.preventDefault();
                const cid = e.currentTarget.dataset.convId;
                if (!cid) return;
                document.getElementById('settingsModal')?.classList.add('hidden');
                await switchToConversation(cid);
            });

            const menuBtn = li.querySelector('.memory-item-menu-btn');
            menuBtn?.addEventListener('click', (e) => {
                e.stopPropagation();
                document.querySelectorAll('.memory-item-popover').forEach(p => p.remove());

                const popover = document.createElement('div');
                popover.className = 'memory-item-popover';
                popover.innerHTML = `
                    <button class="memory-popover-item danger"><i class="fas fa-trash"></i> Delete</button>
                `;
                popover.querySelector('.memory-popover-item')?.addEventListener('click', async () => {
                    popover.remove();
                    try {
                        const token = await getValidToken();
                        const del = await fetch(`${API_BASE_URL}/user/memories/${m.id}`, { method: 'DELETE', headers: { "Authorization": `Bearer ${token}` } });
                        if (del.ok) {
                            li.remove();
                            if (!document.querySelectorAll('.memory-item-gpt').length) {
                                if (empty) empty.classList.remove('hidden');
                            }
                        }
                    } catch { showError("Failed to delete memory"); }
                });
                li.style.position = 'relative';
                li.appendChild(popover);

                const outsideClick = (ev) => {
                    if (!popover.contains(ev.target)) { popover.remove(); document.removeEventListener('click', outsideClick); }
                };
                setTimeout(() => document.addEventListener('click', outsideClick), 0);
            });

            ul.appendChild(li);
        });
    } catch {
        if (loading) loading.style.display = 'none';
        if (empty) { empty.classList.remove('hidden'); empty.textContent = "Failed to load memories."; }
    }
}

/* --- Modules & Speech (issue #4) --------------------------- */

const MODULE_CONFIG = {
    books:      { label: 'Books',      icon: '📚', placeholder: 'Search Hadith, Surah or Ayah...', prefix: 'search_sources: ' },
    motivation: { label: 'Motivation', icon: '💡', placeholder: 'Need some Islamic encouragement?', prefix: 'topic_motivation: ' },
    fatwa:      { label: 'Fatwa',      icon: '⚖️', placeholder: 'Ask an Islamic jurisprudence question...', prefix: 'topic_fatwa: ' },
    general:    { label: 'General',    icon: '💬', placeholder: 'Ask anything Islamic...', prefix: '' },
    chat:       { label: 'Chat',       icon: '🗨️', placeholder: 'Casual conversation...', prefix: '' }
};

function _applyModule(moduleId) {
    const config = MODULE_CONFIG[moduleId];
    if (!config) return;
    State.queryModule = moduleId;
    if (Elements.messageInput) Elements.messageInput.placeholder = config.placeholder;

    // Remove any existing chip
    _clearModuleChip();

    // Insert chip INSIDE the input-container, before the textarea
    const inputContainer = document.querySelector('.input-container');
    if (!inputContainer) return;

    const chip = document.createElement('div');
    chip.id = 'activeModuleChip';
    chip.className = 'active-module-chip';
    chip.innerHTML = `<span>${config.icon} ${config.label}</span>`;

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Clear mode');
    closeBtn.innerHTML = '<i class="fas fa-times"></i>';
    closeBtn.style.cssText = 'background:none;border:none;color:inherit;cursor:pointer;padding:0;display:flex;align-items:center;opacity:0.8;';
    closeBtn.addEventListener('click', (e) => { e.stopPropagation(); _clearModule(); });
    chip.appendChild(closeBtn);

    // Put chip as first child of input-container (left side, before plus btn)
    inputContainer.insertBefore(chip, inputContainer.firstChild);
    Elements.messageInput?.focus();
}

function _clearModule() {
    State.queryModule = null;
    if (Elements.messageInput) {
        Elements.messageInput.placeholder = 'Ask your Islamic question...';
    }

    // Restore + button
    if (Elements.modulesBtn) {
        Elements.modulesBtn.innerHTML = '<i class="fas fa-plus"></i>';
        Elements.modulesBtn.className = 'input-action-btn';
    }
    _clearModuleChip();
}

function _clearModuleChip() {
    document.getElementById('activeModuleChip')?.remove();
}

function initSpeechToText() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition || !Elements.micBtn) {
        if (Elements.micBtn) {
            Elements.micBtn.style.opacity = '0.35';
            Elements.micBtn.title = 'Voice input not supported in this browser';
            Elements.micBtn.disabled = true;
        }
        return;
    }

    const recognition = new SpeechRecognition();
    recognition.interimResults = false;
    recognition.continuous = false;
    let isListening = false;

    Elements.micBtn.addEventListener('click', () => {
        if (isListening) {
            recognition.stop();
            return;
        }
        recognition.lang = localStorage.getItem('deenLang') === 'ar' ? 'ar-SA' : 'en-US';
        try { recognition.start(); } catch (e) { console.warn('Speech start error:', e); }
    });

    recognition.onstart = () => {
        isListening = true;
        Elements.micBtn.classList.add('listening');
        Elements.micBtn.innerHTML = '<i class="fas fa-microphone-slash"></i>';
    };

    recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
            .map(r => r[0].transcript)
            .join('');
        if (Elements.messageInput) {
            Elements.messageInput.value = transcript;
            Elements.messageInput.dispatchEvent(new Event('input'));
        }
    };

    recognition.onend = () => {
        isListening = false;
        Elements.micBtn.classList.remove('listening');
        Elements.micBtn.innerHTML = '<i class="fas fa-microphone"></i>';
    };

    recognition.onerror = (event) => {
        isListening = false;
        Elements.micBtn.classList.remove('listening');
        Elements.micBtn.innerHTML = '<i class="fas fa-microphone"></i>';
        if (event.error === 'not-allowed') {
            showError('Microphone access denied. Please allow it in browser settings.');
        }
    };
}

function _notifyAIDone(bodyText) {
    if (document.visibilityState === 'visible') return;
    if (localStorage.getItem('deen_notif_ai_done') !== 'true') return;
    if (Notification.permission !== 'granted') return;

    try {
        const clean = bodyText.replace(/[#*`]/g, '').substring(0, 120) + '...';
        if (navigator.serviceWorker && navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({
                type: 'SHOW_NOTIFICATION',
                title: 'DeenLink AI',
                body: clean,
                icon: './icons/icon-192.png',
                badge: './icons/icon-72.png'
            });
        } else {
            new Notification("DeenLink AI", {
                body: clean,
                icon: './icons/icon-192.png'
            });
        }
    } catch (e) { console.warn("Notif failed", e); }
}

window.addEventListener("load", async () => {
    await PWA.init();
    initSidebar();
    initEventListeners();

    const savedTheme = localStorage.getItem("theme");
    if (savedTheme === "dark") {
        document.body.classList.add("dark-theme");
    } else if (savedTheme === "system") {
        if (window.matchMedia('(prefers-color-scheme: dark)').matches) {
            document.body.classList.add("dark-theme");
        }
    }

    const savedMode = localStorage.getItem("responseMode");
    if (savedMode) State.responseMode = savedMode;

    // Apply saved font size
    const savedFontSize = localStorage.getItem('deenFontSize');
    if (savedFontSize) document.documentElement.style.setProperty('--chat-font-size', savedFontSize + 'px');

    // Apply saved language pref to State
    const savedLang = localStorage.getItem('deenLang');
    if (savedLang) State.responseLang = savedLang;

    fetchUserProfile();
    await loadConversations();
    updateEmptyStateVisibility();
    
    initSpeechToText();

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

function _memoryStorageKey(convId) { return `deen_memory_notices_${convId}`; }

function persistMemoryNotice(fact) {
    const convId = State.activeConversationId;
    if (!convId) return;
    try {
        const key = _memoryStorageKey(convId);
        const existing = JSON.parse(localStorage.getItem(key) || '[]');
        if (!existing.includes(fact)) { existing.push(fact); localStorage.setItem(key, JSON.stringify(existing)); }
    } catch {}
}

function restoreMemoryNotices(convId) {
    try {
        const key = _memoryStorageKey(convId);
        const facts = JSON.parse(localStorage.getItem(key) || '[]');
        facts.forEach(fact => _renderMemoryNotice(fact, false));
    } catch {}
}

function _renderMemoryNotice(fact, persist = true) {
    if (persist) persistMemoryNotice(fact);
    const notice = document.createElement('div');
    notice.className = 'memory-inline-notice';
    notice.dataset.fact = fact;
    notice.innerHTML = `
        <i class="fas fa-brain"></i>
        <span><strong>Memory updated:</strong> ${escapeHtml(fact)}</span>
        <button class="memory-inline-manage"><i class="fas fa-cog"></i> Manage</button>
    `;
    notice.querySelector('.memory-inline-manage')?.addEventListener('click', () => {
        Elements.settingsModal?.classList.remove('hidden');
        document.querySelectorAll('.settings-page').forEach(p => p.classList.add('hidden'));
        document.getElementById('settingsPageManageMemory')?.classList.remove('hidden');
        loadMemoriesIntoPage();
    });
    Elements.chatMessages.appendChild(notice);
    if (State.autoScroll) Elements.chatMessages.scrollTo({ top: Elements.chatMessages.scrollHeight, behavior: 'smooth' });
}

function showMemoryUpdatedInline(fact) { _renderMemoryNotice(fact, true); }
function showMemoryUpdatedToast(fact) { showMemoryUpdatedInline(fact); }
