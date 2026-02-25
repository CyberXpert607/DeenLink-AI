
let activeConversationId = null;
let jwtToken = null;
let jwtExpiry = null;

const chatMessages = document.getElementById("chatMessages");
const messageInput = document.getElementById("messageInput");
const sendButton = document.getElementById("sendButton");
const conversationList = document.getElementById("conversationList");
const newChatBtn = document.getElementById("newChatBtn");
const themeToggle = document.getElementById("themeToggle")
const quickPromptBtns = document.querySelectorAll(".quick-prompt-btn")

const sidebar = document.getElementById("sidebar");
const overlay = document.getElementById("sidebarOverlay");
const menuToggle = document.getElementById("menuToggle");

window.addEventListener("load", async () => {
    initSidebar();
    await loadConversations();
});

window.addEventListener("unhandledrejection", event => {
    console.error("Unhandled promise rejection:", event.reason);
    showError("An unexpected error occurred. Please try again.");
});

//AUTH TOKEN MANAGEMENT
async function getValidToken() {
    /*const now = Date.now();

    if (jwtToken && jwtExpiry && now < jwtExpiry) {
        return jwtToken;
    }

    const res = await fetch("https://deenlink.infinityfreeapp.com/api/auth/token_server.php", {
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

    return jwtToken;*/
    return "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwidXNlcm5hbWUiOiJ0ZXN0X3VzZXIiLCJ1c2VyX3R5cGUiOiJhZG1pbiIsImlzcyI6ImRlZW5saW5rIiwiYXVkIjoiZGVlbmxpbmstYWkiLCJleHAiOjE3NzIwMzE1NDV9.HiLs_ztMsQzBaJDZ8jKOj_Zjw19Arb_73aj92bVwFEpWOi7B9F2vYV6dP_lOuCBUg2ZyS5S6wQqh3LeJP18g9foTbEUfR0pJKLj745G-4VVN2_A_mr6_PRONKebJsDPNnOKpaN4cI-ffPsoH6j-gbYcEY4jCFX8jvVJ3sUI3GUEVqtE52ZzALaAiWagU3OCr94uM4QX8szIjt1GS4oI13vRc6eh3evKoLMmVC-8EtfXy1Hter8PiC8wqL5B9ml06BUyqCJIhq6J3NByM_KKuCLhWfA5f32B_l8-ZNIDP-D1-o-nZ1eg-6kXPPgjqw27Uyal9sL4hR_yYykuF7ZnaGA"
}

//sidebar behaviour.

function initSidebar() {
    menuToggle.addEventListener("click", () => {
        toggleSidebar();
    });

    overlay.addEventListener("click", () => {
        closeSidebar();
    });

    // Swipe support
    let startX = 0;

    document.addEventListener("touchstart", e => {
        startX = e.changedTouches[0].screenX;
    });

    document.addEventListener("touchend", e => {
        const endX = e.changedTouches[0].screenX;
        const diff = endX - startX;

        if (diff > 80) openSidebar();
        if (diff < -80) closeSidebar();
    });
}

function openSidebar() {
    sidebar.classList.add("open");
    overlay.classList.add("show");
}

function closeSidebar() {
    sidebar.classList.remove("open");
    overlay.classList.remove("show");
}

function toggleSidebar() {
    sidebar.classList.contains("open") ? closeSidebar() : openSidebar();
}

function showError(message) {
    const toast = document.getElementById("error-toast");
    toast.textContent = message;
    toast.classList.remove("hidden");

    setTimeout(() => {
        toast.classList.add("hidden");
    }, 4000);
}

//load multiple conversations.

async function loadConversations() {
    try {
        const token = await getValidToken();

        const res = await fetch("http://localhost:8000/api/v2/conversations", {
            headers: {
                "Authorization": `Bearer ${token}`
            }
        });

        if (!res.ok) {
            if (res.status === 401) {
                showError("Session expired. Please log in again.");
        }   else {
                showError("Failed to load conversations");
            }
            return;
        }
        const data = await res.json();
        
        if (!Array.isArray(data)) {
            showError("Invalid response format from server");
            return;
        }

        renderConversationTabs(data);

        if (data.length > 0) {
            activeConversationId = data[0].conversation_id;
            await loadConversation(activeConversationId);
        }
    }   catch (err) {
        console.error("Error loading conversations", err);
        showError("An error occurred while loading conversations");
    }

}

function renderConversationTabs(conversations) {
    if (!Array.isArray(conversations)) {
        showError("Invalid conversations data");
        return;
    }

    conversationList.innerHTML = "";

    conversations.forEach(conv => {
        const card = document.createElement("div");
        card.className = "conversation-card";
        card.textContent = conv.title || "New Chat";
        card.dataset.id = conv.id;

        card.onclick = async () => {
            try {
            activeConversationId = conv.id;
            await loadConversation(activeConversationId);
            closeSidebar();
        } catch (err) {
            showError("Failed to load conversation.");
            }
        
        };

        const deleteBtn = document.createElement("button");
        deleteBtn.textContent = "Delete";
        deleteBtn.classList.add("delete-btn");

        deleteBtn.onclick = async (e) => {
            e.stopPropagation();
            try {
                await deleteConversation(conv.id);
            } catch (err) {
                showError("Failed to delete conversation.");
            }
        };

        card.appendChild(deleteBtn);
        conversationList.appendChild(card);
    });
}

async function deleteConversation(conversationId) {
    const token = await getValidToken();
    const res = await fetch(`http://localhost:8000/api/v2/conversations/${conversationId}`,
    {
        method: "DELETE",
        headers: {"Authorization": `Bearer ${token}`},
    });
    if (!res.ok) {
        console.error("Failed to delete conversation"); //or alert("failed to delete conversation")
        return;
    }
    await loadConversations(); // refresh conversation list.
}

//load single conversation.

async function loadConversation(id) {
    const token = await getValidToken();

    const res = await fetch(`http://localhost:8000/api/v2/conversations/${id}`, {
        headers: {
            "Authorization": `Bearer ${token}`
        }
    });

    const data = await res.json();

    chatMessages.innerHTML = "";

    data.messages.forEach(msg => {
        appendMessage(msg.role === "user" ? "user" : "ai", msg.content);
    });
}

//stream message.

async function sendMessage() {
    const text = messageInput.value.trim();
    if (!text) return;
    
    if (!activeConversationId) {
        const token = await getValidToken();
        const res = await fetch("http://localhost:8000/api/v2/conversations/new", {
            method: "POST",
            headers: {
                "Authorization": `Bearer ${token}`,
                "Content-Type": "application/json"
            }
        });
        const data = await res.json();
        activeConversationId = data.conversation_id;
        
        renderConversationTabs([
            {
                conversation_id: activeConversationId,
                title: data.title || "New Chat"
            },
            ...Array.from(document.document.querySelectorAll(".conversation-card")).map(c => ({
                conversation_id: c.dataset.id,
                title: c.textContent
            }))
        ]);
    }

    appendMessage("user", text);
    messageInput.value = "";
    messageInput.style.height = "auto";
    messageInput.style.overflowY = "hidden";

    //show loading animation immediately
    const loadingObj = appendLoadingMessage();
    try {
        const token = await getValidToken();

        const res = await fetch("http://localhost:8000/api/v2/ask/stream", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": `Bearer ${token}`
            },
            body: JSON.stringify({
                message: text,
                conversation_id: activeConversationId
            })
        });
        if (!res.ok || !res.body) {
            loadingEl.remove();
            throw new Error("Streaming failed");
        }

    const reader = res.body.getReader();
    const decoder = new TextDecoder("utf-8");

    let aiMessageEl = replaceLoadingWithAIMessage(loadingObj);
    let buffer = "";

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, {stream: true});
        buffer += chunk;

        const events = buffer.split("\n\n");
        for (let i = 0; i < events.length - 1; i++) {
            const line = events[i].trim();
            if (!line.startsWith("data:")) continue;

            const dataStr = line.replace(/^data:\s*/, "");
            const data = JSON.parse(dataStr);

            if (data.type === "token") {
                aiMessageEl.innerHTML += data.content;
                chatMessages.scrollTop = chatMessages.scrollHeight;
            } else if (data.done) {
                chatMessages.scrollTop = chatMessages.scrollHeight;
            }
        }
        buffer = events[events.length -1];
    }

    await loadConversations(); // refresh titles if new chat

} catch (err) {
    loadingEl.remove();
    console.error(err);
    showError("Failed to send message. Please try again.");
    }
}


sendButton.addEventListener("click", sendMessage);

messageInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

messageInput.addEventListener("input", () => {
    messageInput.style.height = "auto";
    messageInput.style.height = messageInput.scrollHeight + "px";

    if (messageInput.scrollHeight > 120) {
        messageInput.style.overflowY = "auto";
    } else {
        messageInput.style.overflowY = "hidden";
    }
});

themeToggle.addEventListener("click", () => {
    document.body.classList.toggle("dark-theme");
});

quickPromptBtns.forEach(btn => {
    btn.addEventListener('click', ()=> {
        messageInput.value = btn.dataset.prompt;
        messageInput.focus();
        sendButton.disabled = false;
    });
});

//ui helpers.
function appendLoadingMessage() {
    const el = document.createElement("div");
    el.className = "message ai loading";
    el.innerHTML = `
        <div class="message-content">
           <div class="typing-indicator">
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
              <div class="typing-dot"></div>
           </div>
        </div>
`;
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
    return {
        container: el,
        textEl: el.querySelector(".message-text")
    };
}

function replaceLoadingWithAIMessage(loadingObj){
    const {container, textEl} = loadingObj;
    textEl.innerHTML = ""; //clear dots.
    container.classList.remove("loading");
    return textEl;
}

function appendMessage(sender, text) {
    const el = document.createElement("div");
    el.className = `message ${sender}`;
    el.innerHTML = `
        <div class="message-content">
            <div class="message-text">${text}</div>
        </div>
    `;
    el.querySelector(".message-text").textContent = text;
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function createEmptyAIMessage() {
    const el = document.createElement("div");
    el.className = "message ai";
    el.innerHTML = `
        <div class="message-avatar">
            <i class="fas fa-robot"></i>
        </div>
        <div class="message-content">
            <div class="message-text"></div>
        </div>
    `;
    chatMessages.appendChild(el);
    chatMessages.scrollTop = chatMessages.scrollHeight;

    return el.querySelector(".message-text");
}

//start a new conversation.
newChatBtn.addEventListener("click", async () => {
    const token = await getValidToken();

    const res = await fetch("http://localhost:8000/api/v2/conversations/new",
    {
        method: "POST",
        headers: {
            "Authorization": `Bearer ${token}`,
            "Content-Type": "application/json"
        }
    });
    const data = await res.json();

    activeConversationId = data.conversation_id;
    //reset chat window from here...
    chatMessages.innerHTML = "";
    closeSidebar();

    const existingCards = Array.from(
        document.querySelectorAll(".conversation-card")
        ).map(c => ({
            conversation_id: c.dataset.id,
            title: c.textContent
        }));

    renderConversationTabs([
        {
            conversation_id: activeConversationId,
            title: data.title || "New Chat"
        },
        ...existingCards
    ]);
});
