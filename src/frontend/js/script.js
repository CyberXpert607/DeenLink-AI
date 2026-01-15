        const pageLoader = document.getElementById('pageLoader');
        const pageContent = document.querySelector('.container');

        function showPageLoader() {
            pageLoader.classList.add('active');
            document.body.style.overflow = 'hidden';
        }

        function hidePageLoader() {
            pageLoader.classList.remove('active');
            document.body.style.overflow = 'auto';
        }

        document.getElementById('backButton').addEventListener('click', function() {
            showPageLoader();
            setTimeout(() => {
                window.location.href = 'index.html';
            }, 300);
        });

        window.addEventListener('load', function() {
            setTimeout(hidePageLoader, 300);
            
            
            if (pageContent) {
                pageContent.style.opacity = '1';
            }
        });


        setTimeout(() => {
            if (document.readyState === 'complete') {
                hidePageLoader();
            }
        }, 100);

    /*Updated this calls the backend for the response not dummy data, Ussy :) */

        const state = {
            isDarkMode: false,
            messages: [
                {
                    id: 1,
                    sender: 'ai',
                    text: 'Assalamu Alaikum! I am DeenLink AI. Ask me about Qur’an, Hadith, Fiqh, or Aqeedah.',
                    time: 'Just now'
                }
            ],
            isTyping: false
        };

        const body = document.body;
        const chatMessages = document.getElementById('chatMessages');
        const messageInput = document.getElementById('messageInput');
        const sendButton = document.getElementById('sendButton');
        const themeToggle = document.getElementById('themeToggle');
        const clearChatBtn = document.getElementById('clearChatBtn');
        const quickPromptBtns = document.querySelectorAll('.quick-prompt-btn');

        themeToggle.addEventListener('click', () => {
            state.isDarkMode = !state.isDarkMode;
            body.classList.toggle('dark-theme', state.isDarkMode);
            body.classList.toggle('light-theme', !state.isDarkMode);
        });

        function renderMessages() {
            chatMessages.innerHTML = '';

            state.messages.forEach(msg => {
                const el = document.createElement('div');
                el.className = `message ${msg.sender}`;
                el.innerHTML = `
                    <div class="message-avatar">
                        <i class="fas ${msg.sender === 'user' ? 'fa-user' : 'fa-robot'}"></i>
                    </div>
                    <div class="message-content">
                        <div class="message-text">${msg.text}</div>
                        <div class="message-time">${msg.time}</div>
                    </div>
                `;
                chatMessages.appendChild(el);
            });

            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function showTypingIndicator() {
            if (state.isTyping) return;
            state.isTyping = true;

            const el = document.createElement('div');
            el.id = 'typing-indicator';
            el.className = 'message ai';
            el.innerHTML = `
                <div class="message-avatar"><i class="fas fa-robot"></i></div>
                <div class="typing-indicator">
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                    <div class="typing-dot"></div>
                </div>
            `;
            chatMessages.appendChild(el);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function removeTypingIndicator() {
            state.isTyping = false;
            const el = document.getElementById('typing-indicator');
            if (el) el.remove();
        }

        async function sendMessage() {
            const text = messageInput.value.trim();
            if (!text) return;

            state.messages.push({
                id: state.messages.length + 1,
                sender: 'user',
                text,
                time: getCurrentTime()
            });

            renderMessages();
            messageInput.value = '';
            sendButton.disabled = true;
            showTypingIndicator();

            try {
                const res = await fetch('http://localhost:8080/api/v2/ask', { //now the Agent calls my backend so... no harcoded responses
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: text })
                });

                const data = await res.json();
                removeTypingIndicator();

                state.messages.push({
                    id: state.messages.length + 1,
                    sender: 'ai',
                    text: data.answer_html,
                    time: getCurrentTime()
                });

                renderMessages();

            } catch (err) {
                removeTypingIndicator();
                state.messages.push({
                    id: state.messages.length + 1,
                    sender: 'ai',
                    text: 'Something went wrong. Please try again.',
                    time: getCurrentTime()
                });
            renderMessages();
        }
    }

    sendButton.addEventListener('click', sendMessage);

    messageInput.addEventListener('keydown', e => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    quickPromptBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            messageInput.value = btn.dataset.prompt;
            messageInput.focus();
            sendButton.disabled = false;
        });
    });

    clearChatBtn.addEventListener('click', () => {
        state.messages = [state.messages[0]];
        renderMessages();
    });

    function getCurrentTime() {
        const d = new Date();
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    renderMessages();