// DOM элементы
const messagesContainer = document.getElementById('messages');
const userInput = document.getElementById('user-input');
const sendBtn = document.getElementById('send-btn');
const statusDiv = document.getElementById('status');
const clearChatBtn = document.getElementById('clear-chat-btn');
const resetSettingsBtn = document.getElementById('reset-settings-btn');
const contextCountSpan = document.getElementById('context-count');

// Vision элементы
const imageInput = document.getElementById('imageInput');
const uploadImageBtn = document.getElementById('uploadImageBtn');
const imagePreviewContainer = document.getElementById('imagePreviewContainer');
const imagePreview = document.getElementById('imagePreview');
const removeImageBtn = document.getElementById('removeImageBtn');
const imageInfo = document.getElementById('imageInfo');
const imageUploadArea = document.getElementById('imageUploadArea');

// Переменная для хранения текущего изображения (base64)
let currentImageBase64 = null;
let currentImageMimeType = null;

// Элементы меню
const drawerMenu = document.getElementById('drawerMenu');
const menuToggleBtn = document.getElementById('menuToggleBtn');
const openDrawerBtn = document.getElementById('openDrawerBtn');
const drawerClose = document.getElementById('drawerClose');
const drawerOverlay = document.getElementById('drawerOverlay');
const advancedToggle = document.getElementById('advancedToggle');
const advancedContent = document.getElementById('advancedContent');

// Элементы настроек
const modelSelect = document.getElementById('model-select');
const systemPrompt = document.getElementById('system-prompt');
const temperature = document.getElementById('temperature');
const topP = document.getElementById('top-p');
const topK = document.getElementById('top-k');
const frequencyPenalty = document.getElementById('frequency-penalty');
const presencePenalty = document.getElementById('presence-penalty');
const repeatPenalty = document.getElementById('repeat-penalty');
const maxTokens = document.getElementById('max-tokens');
const seedInput = document.getElementById('seed');

// === СОСТОЯНИЕ ===
let isWaiting = false;
let waitTimeout = null;
let conversationHistory = [];
let isAdvancedOpen = localStorage.getItem('advanced_open') === 'true';
let activeRequest = false;
let currentRequestId = null;
let currentAbortController = null;

// === НАСТРОЙКИ ТАЙМАУТА ===
let REQUEST_TIMEOUT_MS = 5 * 60 * 1000; // 5 минут по умолчанию

// === ЛОГИКА ОТМЕН И БЛОКИРОВКИ ===
let cancelAttempts = [];
let isBlocked = false;
let blockEndTime = null;
let blockTimer = null;

const CANCEL_WINDOW_MS = 30000;
const CANCEL_MAX_ATTEMPTS = 2;
const BLOCK_DURATION_MS = 60000;

// === УПРАВЛЕНИЕ КНОПКАМИ УДАЛЕНИЯ ===
function setDeleteButtonsState(disabled) {
    document.querySelectorAll('.delete-message-btn').forEach(btn => {
        btn.disabled = disabled;
    });
}

// === ДОБАВЛЕНИЕ КНОПОК КОПИРОВАНИЯ ДЛЯ КАЖДОГО БЛОКА КОДА ===
function addCopyButtonsToCodeBlocks(container) {
    if (!container) return;
    container.querySelectorAll('.code-container').forEach(containerElem => {
        if (containerElem.querySelector('.copy-code-btn')) return; // уже есть кнопка
        const codeBlock = containerElem.querySelector('pre code');
        if (!codeBlock) return;
        const btn = document.createElement('button');
        btn.className = 'copy-code-btn';
        btn.innerHTML = '<i class="fas fa-copy"></i> Копировать';
        btn.onclick = (e) => {
            e.stopPropagation();
            const code = codeBlock.innerText;
            copyToClipboard(code);
        };
        const header = containerElem.querySelector('.code-header');
        if (header) {
            header.appendChild(btn);
        }
    });
}

// === ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ ДОБАВЛЕНИЯ КНОПОК В СООБЩЕНИЕ ===
function addButtonsToMessage(messageDiv, role, content) {
    const messageContent = messageDiv.querySelector('.message-content');
    if (!messageContent) return;

    // Удаляем старые кнопки, если есть
    const oldButtons = messageContent.querySelector('.message-buttons');
    if (oldButtons) oldButtons.remove();

    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'message-buttons';

    if (role === 'assistant') {
        buttonsDiv.innerHTML = `
            <button class="delete-message-btn"><i class="fas fa-trash-alt"></i> Удалить</button>
            <button class="copy-message-btn"><i class="fas fa-copy"></i> Копировать ответ</button>
        `;
        const copyBtn = buttonsDiv.querySelector('.copy-message-btn');
        if (copyBtn) {
            copyBtn.addEventListener('click', () => copyToClipboard(content));
        }
    } else {
        buttonsDiv.innerHTML = `<button class="delete-message-btn"><i class="fas fa-trash-alt"></i> Удалить</button>`;
    }

    const deleteBtn = buttonsDiv.querySelector('.delete-message-btn');
    if (deleteBtn) {
        deleteBtn.disabled = activeRequest;
        deleteBtn.addEventListener('click', () => {
            messageDiv.remove();
            rebuildHistoryFromUI();
        });
    }

    messageContent.appendChild(buttonsDiv);
    messageDiv.setAttribute('data-raw-text', content);
}

// === ФУНКЦИЯ ПЕРЕСТРОЕНИЯ ИСТОРИИ ИЗ UI ===
function rebuildHistoryFromUI() {
    const messageElements = document.querySelectorAll('.message.user, .message.assistant');
    const newHistory = [];
    messageElements.forEach(el => {
        const role = el.classList.contains('user') ? 'user' : 'assistant';
        const rawText = el.getAttribute('data-raw-text');
        if (rawText) {
            newHistory.push({ role, content: rawText });
        }
    });
    conversationHistory = newHistory;
    saveHistory();
    updateContextCount();
}

// === ФУНКЦИИ РАБОТЫ С ИЗОБРАЖЕНИЯМИ ===
function handleImageUpload(file) {
    if (!file) return;

    const allowedTypes = ['image/jpeg', 'image/png', 'image/jpg', 'image/webp'];
    if (!allowedTypes.includes(file.type)) {
        showNotification('Поддерживаются только JPEG, PNG, JPG и WebP изображения', 'error');
        return;
    }

    const maxSize = 5 * 1024 * 1024;
    if (file.size > maxSize) {
        showNotification('Размер изображения не должен превышать 5MB', 'error');
        return;
    }

    const reader = new FileReader();
    reader.onload = function(e) {
        const base64 = e.target.result.split(',')[1];

        // Сжимаем изображение перед сохранением
        compressImage(base64, file.type, (compressedBase64, mimeType) => {
            currentImageBase64 = compressedBase64;
            currentImageMimeType = mimeType;

            imagePreview.src = `data:${mimeType};base64,${compressedBase64}`;
            imagePreviewContainer.style.display = 'block';

            const fileSizeKB = (file.size / 1024).toFixed(1);
            imageInfo.textContent = `${file.name} (${fileSizeKB} KB)`;
            showNotification(`Изображение "${file.name}" загружено`, 'success');
        });
    };
    reader.readAsDataURL(file);
}

function compressImage(base64, originalMimeType, callback) {
    const img = new Image();
    img.onload = () => {
        // Не сжимаем, просто передаём как есть
        const canvas = document.createElement('canvas');
        canvas.width = img.width;
        canvas.height = img.height;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(img, 0, 0);

        // Сохраняем оригинальный формат и качество
        const mimeType = originalMimeType;
        const quality = 1.0;  // 100% качество

        const compressed = canvas.toDataURL(mimeType, quality);
        const compressedBase64 = compressed.split(',')[1];

        callback(compressedBase64, mimeType);
    };
    img.src = `data:${originalMimeType};base64,${base64}`;
}

function removeImage() {
    currentImageBase64 = null;
    currentImageMimeType = null;
    imagePreviewContainer.style.display = 'none';
    imagePreview.src = '';
    imageInfo.textContent = '';
    if (imageInput) imageInput.value = '';
    showNotification('Изображение удалено', 'info');
}

// === ФУНКЦИЯ ПРОВЕРКИ ВЫБРАННОЙ МОДЕЛИ ===
function isModelSelected() {
    const selectedModel = modelSelect.value;
    if (!selectedModel || selectedModel === '') {
        showNotification('⚠️ Пожалуйста, выберите модель в настройках перед отправкой сообщения', 'error');
        return false;
    }
    return true;
}

function isSendBlocked() {
    if (!isBlocked) return false;

    const now = Date.now();
    if (now >= blockEndTime) {
        isBlocked = false;
        blockEndTime = null;
        cancelAttempts = [];
        if (blockTimer) {
            clearInterval(blockTimer);
            blockTimer = null;
        }
        showNotification('✅ Блокировка снята, можно отправлять сообщения', 'success');
        setStatus('Готов');
        return false;
    }
    return true;
}

function checkCancelLimit() {
    const now = Date.now();
    cancelAttempts = cancelAttempts.filter(time => now - time < CANCEL_WINDOW_MS);

    if (cancelAttempts.length >= CANCEL_MAX_ATTEMPTS) {
        isBlocked = true;
        blockEndTime = now + BLOCK_DURATION_MS;
        saveBlockState();
        startBlockTimer();
        return { allowed: false, reason: 'blocked', remaining: Math.ceil(BLOCK_DURATION_MS / 1000) };
    }
    return { allowed: true };
}

function registerCancelAttempt() {
    const now = Date.now();
    cancelAttempts.push(now);
    cancelAttempts = cancelAttempts.filter(time => now - time < CANCEL_WINDOW_MS);
    saveCancelAttempts();
    const remaining = CANCEL_MAX_ATTEMPTS - cancelAttempts.length;
    if (remaining > 0) {
        showNotification(`⚠️ Осталось ${remaining} отмена за ${CANCEL_WINDOW_MS/1000} сек`, 'info');
    }
}

function saveBlockState() {
    if (isBlocked && blockEndTime) {
        localStorage.setItem('cancel_blocked_until', blockEndTime.toString());
    } else {
        localStorage.removeItem('cancel_blocked_until');
    }
}

function saveCancelAttempts() {
    localStorage.setItem('cancel_attempts', JSON.stringify(cancelAttempts));
}

function loadBlockState() {
    const savedBlockEnd = localStorage.getItem('cancel_blocked_until');
    if (savedBlockEnd) {
        const blockEnd = parseInt(savedBlockEnd);
        if (blockEnd > Date.now()) {
            isBlocked = true;
            blockEndTime = blockEnd;
            startBlockTimer();
        } else {
            localStorage.removeItem('cancel_blocked_until');
        }
    }

    const savedAttempts = localStorage.getItem('cancel_attempts');
    if (savedAttempts) {
        cancelAttempts = JSON.parse(savedAttempts);
        const now = Date.now();
        cancelAttempts = cancelAttempts.filter(time => now - time < CANCEL_WINDOW_MS);
        saveCancelAttempts();
    }
}

function startBlockTimer() {
    if (blockTimer) clearInterval(blockTimer);

    blockTimer = setInterval(() => {
        if (!isBlocked || !blockEndTime) {
            if (blockTimer) clearInterval(blockTimer);
            blockTimer = null;
            return;
        }

        const now = Date.now();
        if (now >= blockEndTime) {
            isBlocked = false;
            blockEndTime = null;
            cancelAttempts = [];
            saveBlockState();
            saveCancelAttempts();
            if (blockTimer) clearInterval(blockTimer);
            blockTimer = null;
            showNotification('✅ Блокировка снята, можно отправлять сообщения', 'success');
            setStatus('Готов');
            updateUIForBlockState();
        } else {
            const remaining = Math.ceil((blockEndTime - now) / 1000);
            setStatus(`Блокировка ${remaining}с`, true);
            updateUIForBlockState();
        }
    }, 1000);
}

function updateUIForBlockState() {
    const isBlockedNow = isBlocked && blockEndTime && Date.now() < blockEndTime;

    if (isBlockedNow) {
        sendBtn.disabled = true;
        userInput.disabled = true;
        if (blockEndTime) {
            const remaining = Math.ceil((blockEndTime - Date.now()) / 1000);
            sendBtn.title = `Блокировка на ${remaining} секунд`;
            userInput.title = `Блокировка на ${remaining} секунд`;
        }
    } else if (!activeRequest && !isWaiting) {
        sendBtn.disabled = false;
        userInput.disabled = false;
        sendBtn.title = '';
        userInput.title = '';
    }
}

async function stopGeneration() {
    if (!activeRequest) {
        setStatus('Нет активного запроса');
        return;
    }

    registerCancelAttempt();
    const limitCheck = checkCancelLimit();
    setStatus('Отмена генерации...');

    const stopBtn = document.getElementById('stop-generation-btn');
    if (stopBtn) {
        stopBtn.disabled = true;
        stopBtn.style.opacity = '0.5';
    }

    if (currentAbortController) {
        currentAbortController.abort();
    }

    try {
        const response = await fetch('/cancel', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ request_id: currentRequestId })
        });

        if (limitCheck.allowed === false && limitCheck.reason === 'blocked') {
            showNotification(`⛔ Отдохни. Ты устал, выпей чаю, поговори с коллегами. Блокировка на ${limitCheck.remaining} секунд.`, 'error');
            setStatus(`Блокировка ${limitCheck.remaining}с`, true);
            updateUIForBlockState();
        } else {
            setStatus('Генерация отменена');
            showNotification('⚠️ Генерация прервана', 'info');
            setTimeout(() => {
                if (!isBlocked) setStatus('Готов');
            }, 2000);
        }
    } catch (error) {
        console.error('Ошибка при отмене:', error);
        setStatus('Ошибка при отмене', true);
    } finally {
        activeRequest = false;
        currentRequestId = null;
        currentAbortController = null;
        if (stopBtn) {
            stopBtn.style.display = 'none';
            stopBtn.disabled = false;
            stopBtn.style.opacity = '1';
        }
        setDeleteButtonsState(false);
    }
}

// === ОБНОВЛЁННАЯ ФУНКЦИЯ addMessageToUI с кнопкой удаления и копирования кода ===
function addMessageToUI(role, content, save = true) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${role}`;
    messageDiv.setAttribute('data-raw-text', content);

    const avatar = role === 'user' ? '👤' : '🤖';
    let formattedContent = '';
    if (role === 'assistant') {
        formattedContent = formatMessageWithCode(content);
    } else {
        formattedContent = `<div class="message-text">${escapeHtml(content).replace(/\n/g, '<br>')}</div>`;
    }

    messageDiv.innerHTML = `
        <div class="avatar">${avatar}</div>
        <div class="message-content">
            ${formattedContent}
        </div>
    `;

    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    // Добавляем кнопки
    addButtonsToMessage(messageDiv, role, content);

    // Подсветка кода для ассистента и добавление кнопок копирования для блоков кода
    if (role === 'assistant') {
        setTimeout(() => {
            const codeBlocks = messageDiv.querySelectorAll('pre code');
            codeBlocks.forEach(block => hljs.highlightElement(block));
            addCopyButtonsToCodeBlocks(messageDiv);
        }, 10);
    }

    if (save && role !== 'system') {
        saveHistory();
    }

    return messageDiv;
}

async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        const notification = document.getElementById('copy-notification');
        notification.classList.add('show');
        setTimeout(() => notification.classList.remove('show'), 2000);
        return true;
    } catch (err) {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        document.body.removeChild(textarea);
        const notification = document.getElementById('copy-notification');
        notification.classList.add('show');
        setTimeout(() => notification.classList.remove('show'), 2000);
        return true;
    }
}

function setStatus(status, isError = false) {
    const statusSpan = statusDiv.querySelector('span:last-child') || statusDiv;
    statusSpan.textContent = status;
    const dot = statusDiv.querySelector('.status-dot');
    if (isError) {
        dot?.classList.add('error');
    } else {
        dot?.classList.remove('error');
    }
}

function updateContextCount() {
    const messageCount = conversationHistory.length;
    contextCountSpan.textContent = messageCount;

    const indicator = document.getElementById('context-indicator');
    if (messageCount > 15) {
        indicator.style.background = 'rgba(239, 68, 68, 0.2)';
    } else if (messageCount > 8) {
        indicator.style.background = 'rgba(251, 191, 36, 0.2)';
    } else {
        indicator.style.background = 'rgba(74, 222, 128, 0.2)';
    }
}

function saveHistory() {
    localStorage.setItem('chat_history', JSON.stringify(conversationHistory));
}

function loadHistory() {
    const saved = localStorage.getItem('chat_history');
    if (saved) {
        try {
            conversationHistory = JSON.parse(saved);
            messagesContainer.innerHTML = '';
            for (const msg of conversationHistory) {
                addMessageToUI(msg.role, msg.content, false);
            }
            updateContextCount();
        } catch(e) {}
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatMessageWithCode(text) {
    if (!text) return '<div class="message-text">' + escapeHtml(text) + '</div>';

    const codeBlockRegex = /```(\w*)\n([\s\S]*?)```/g;
    let lastIndex = 0;
    let formatted = '';
    let match;

    while ((match = codeBlockRegex.exec(text)) !== null) {
        if (match.index > lastIndex) {
            const textBefore = text.slice(lastIndex, match.index);
            if (textBefore.trim()) {
                formatted += `<div class="message-text">${escapeHtml(textBefore).replace(/\n/g, '<br>')}</div>`;
            }
        }

        const language = match[1] || 'plaintext';
        const code = match[2].trim();

        formatted += `
            <div class="code-container">
                <div class="code-header">
                    <div class="code-lang">
                        <i class="fas fa-code"></i> ${language.toUpperCase()}
                    </div>
                </div>
                <pre class="code-block"><code class="language-${language}">${escapeHtml(code)}</code></pre>
            </div>
        `;

        lastIndex = match.index + match[0].length;
    }

    if (lastIndex < text.length) {
        const remainingText = text.slice(lastIndex);
        if (remainingText.trim()) {
            formatted += `<div class="message-text">${escapeHtml(remainingText).replace(/\n/g, '<br>')}</div>`;
        }
    }

    if (!formatted) {
        formatted = `<div class="message-text">${escapeHtml(text).replace(/\n/g, '<br>')}</div>`;
    }

    return formatted;
}

function clearChat() {
    conversationHistory = [];
    messagesContainer.innerHTML = `
        <div class="message assistant">
            <div class="avatar">🤖</div>
            <div class="message-content">
                <div class="message-text">
                    <strong>👋 Привет! Я готов помочь!</strong><br><br>
                    • 🔒 Лимит токенов: 4096<br>
                    • 🖼️ Поддержка изображений (модели Vision)<br>
                    Задавай вопросы или загружай изображения!
                </div>
            </div>
        </div>
    `;
    updateContextCount();
    saveHistory();
    setStatus('Диалог очищен');
    setTimeout(() => setStatus('Готов'), 2000);
    userInput.focus();
}

function resetSettings() {
    temperature.value = '0.7';
    topP.value = '0.9';
    topK.value = '50';
    frequencyPenalty.value = '0.0';
    presencePenalty.value = '0.0';
    repeatPenalty.value = '1.1';
    maxTokens.value = '2000';
    seedInput.value = '';
    systemPrompt.value = '';

    document.getElementById('temp-value').textContent = '0.7';
    document.getElementById('topp-value').textContent = '0.9';
    document.getElementById('topk-value').textContent = '50';
    document.getElementById('freq-value').textContent = '0.0';
    document.getElementById('presence-value').textContent = '0.0';
    document.getElementById('repeat-value').textContent = '1.1';
    document.getElementById('max-tokens-value').textContent = '2000';

    saveSettings();
    setStatus('Настройки сброшены');
    setTimeout(() => setStatus('Готов'), 2000);
}

async function loadModels() {
    try {
        const response = await fetch('/get_models');
        const data = await response.json();
        if (data.models && data.models.length > 0) {
            modelSelect.innerHTML = '<option value="">-- Выберите модель --</option>' +
                data.models.map(model => `<option value="${model}">${model}</option>`).join('');
            const savedModel = localStorage.getItem('selected_model');
            if (savedModel && data.models.includes(savedModel)) {
                modelSelect.value = savedModel;
            }
        } else {
            modelSelect.innerHTML = '<option value="">-- Модели не найдены --</option>';
        }
    } catch (error) {
        console.error('Ошибка загрузки моделей:', error);
        modelSelect.innerHTML = '<option value="">-- Ошибка загрузки моделей --</option>';
    }
}

function saveSettings() {
    const settings = {
        system_prompt: systemPrompt.value,
        temperature: temperature.value,
        top_p: topP.value,
        top_k: topK.value,
        frequency_penalty: frequencyPenalty.value,
        presence_penalty: presencePenalty.value,
        repeat_penalty: repeatPenalty.value,
        max_tokens: maxTokens.value,
        seed: seedInput.value
    };
    localStorage.setItem('chat_settings', JSON.stringify(settings));
}

function loadSettings() {
    const saved = localStorage.getItem('chat_settings');
    if (saved) {
        try {
            const settings = JSON.parse(saved);
            systemPrompt.value = settings.system_prompt || '';
            temperature.value = settings.temperature || 0.7;
            topP.value = settings.top_p || 0.9;
            topK.value = settings.top_k || 50;
            frequencyPenalty.value = settings.frequency_penalty || 0.0;
            presencePenalty.value = settings.presence_penalty || 0.0;
            repeatPenalty.value = settings.repeat_penalty || 1.0;
            maxTokens.value = settings.max_tokens || 1000;
            seedInput.value = settings.seed || '';

            document.getElementById('temp-value').textContent = temperature.value;
            document.getElementById('topp-value').textContent = topP.value;
            document.getElementById('topk-value').textContent = topK.value;
            document.getElementById('freq-value').textContent = frequencyPenalty.value;
            document.getElementById('presence-value').textContent = presencePenalty.value;
            document.getElementById('repeat-value').textContent = repeatPenalty.value;
            document.getElementById('max-tokens-value').textContent = maxTokens.value;
        } catch(e) {}
    }
}

function setWaitingMode(waitSeconds = null) {
    if (waitSeconds === false) {
        isWaiting = false;
        sendBtn.disabled = false;
        userInput.disabled = false;
        setStatus('Готов');
        if (waitTimeout) clearInterval(waitTimeout);
        return;
    }
    isWaiting = true;
    sendBtn.disabled = true;
    userInput.disabled = true;
    let remaining = waitSeconds;
    setStatus(`Ожидание ${remaining}с...`);
    if (waitTimeout) clearInterval(waitTimeout);
    waitTimeout = setInterval(() => {
        remaining--;
        if (remaining <= 0) {
            clearInterval(waitTimeout);
            setWaitingMode(false);
        } else {
            setStatus(`Ожидание ${remaining}с...`);
        }
    }, 1000);
}

function addStopButton() {
    const inputArea = document.querySelector('.input-area');
    if (document.getElementById('stop-generation-btn')) return;

    const stopBtn = document.createElement('button');
    stopBtn.id = 'stop-generation-btn';
    stopBtn.className = 'stop-btn';
    stopBtn.innerHTML = '<i class="fas fa-stop"></i> Стоп';
    stopBtn.onclick = () => stopGeneration();
    stopBtn.style.display = 'none';
    inputArea.appendChild(stopBtn);
}

// ========== ОСНОВНАЯ ФУНКЦИЯ ОТПРАВКИ С БЛОКИРОВКОЙ УДАЛЕНИЯ ==========
async function sendMessage() {
    // ПРОВЕРКА: выбрана ли модель
    if (!isModelSelected()) {
        return;
    }

    if (isSendBlocked()) {
        const remaining = Math.ceil((blockEndTime - Date.now()) / 1000);
        showNotification(`⛔ Вы заблокированы на ${remaining} секунд за частые отмены`, 'error');
        setStatus(`Блокировка ${remaining}с`, true);
        return;
    }

    if (activeRequest) {
        setStatus('Предыдущий запрос еще обрабатывается. Нажмите "Стоп" для отмены.', true);
        return;
    }

    if (isWaiting) {
        setStatus('Подождите, обрабатывается запрос', true);
        return;
    }

    const message = userInput.value.trim();
    if (!message && !currentImageBase64) {
        setStatus('Введите сообщение или загрузите изображение', true);
        return;
    }

    const approxTokens = Math.ceil((message ? message.length : 0) / 2);
    if (approxTokens > 4000) {
        showNotification(`⚠️ Слишком длинное сообщение (~${approxTokens} токенов). Лимит 4096 токенов.`, 'error');
        setStatus('Сообщение слишком длинное', true);
        return;
    }

    // === БЛОКИРУЕМ КНОПКИ УДАЛЕНИЯ И АКТИВИРУЕМ ЗАПРОС ===
    activeRequest = true;
    currentRequestId = Date.now().toString();
    setDeleteButtonsState(true);  // блокируем все существующие кнопки

    // Сохраняем флаг: было ли изображение при отправке
    const hadImage = !!currentImageBase64;

    // Формируем сообщение пользователя (с указанием изображения, если есть)
    let userDisplayMessage = message;
    if (hadImage) {
        if (message) {
            userDisplayMessage = `${message}\n\n🖼️ Изображение прикреплено`;
        } else {
            userDisplayMessage = "🖼️ Анализ изображения";
        }
    }

    addMessageToUI('user', userDisplayMessage);
    conversationHistory.push({ role: 'user', content: userDisplayMessage });
    updateContextCount();
    saveHistory();

    userInput.value = '';
    userInput.style.height = 'auto';

    const stopBtn = document.getElementById('stop-generation-btn');
    if (stopBtn) stopBtn.style.display = 'flex';

    const assistantMessageDiv = document.createElement('div');
    assistantMessageDiv.className = 'message assistant';
    assistantMessageDiv.id = 'streaming-message-' + currentRequestId;
    assistantMessageDiv.innerHTML = `
        <div class="avatar">🤖</div>
        <div class="message-content">
            <div class="message-text">
                <div class="typing-indicator" style="display: flex;">
                    <span></span><span></span><span></span>
                </div>
                <div style="font-size: 0.8rem; color: #888; margin-top: 8px;">
                    <i class="fas fa-hourglass-half"></i> Генерация ответа...
                </div>
            </div>
        </div>
    `;
    messagesContainer.appendChild(assistantMessageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    let fullResponse = "";
    let textDiv = null;

    try {
        const payload = {
            message: message,
            history: conversationHistory.slice(0, -1),
            model: modelSelect.value,
            system_prompt: systemPrompt.value,
            temperature: parseFloat(temperature.value),
            top_p: parseFloat(topP.value),
            top_k: parseInt(topK.value),
            frequency_penalty: parseFloat(frequencyPenalty.value),
            presence_penalty: parseFloat(presencePenalty.value),
            repeat_penalty: parseFloat(repeatPenalty.value),
            max_tokens: parseInt(maxTokens.value),
            request_id: currentRequestId
        };

        // Добавляем изображение, если есть
        if (hadImage) {
            payload.image = currentImageBase64;
            payload.image_mime_type = currentImageMimeType;
        }

        if (seedInput.value && seedInput.value !== '') payload.seed = parseInt(seedInput.value);

        currentAbortController = new AbortController();

        // Таймаут для запроса
        const timeoutId = setTimeout(() => {
            if (currentAbortController) {
                currentAbortController.abort();
                showNotification('Превышено время ожидания ответа (5 минут)', 'error');
            }
        }, REQUEST_TIMEOUT_MS);

        const response = await fetch('/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            signal: currentAbortController.signal
        });

        clearTimeout(timeoutId);

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || `Ошибка HTTP: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || "";

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));

                        if (data.cancelled) {
                            if (textDiv) {
                                textDiv.innerHTML = formatMessageWithCode(fullResponse + "\n\n⏹️ Генерация прервана");
                            }
                            break;
                        }

                        if (data.error) {
                            throw new Error(data.error);
                        }

                        if (data.content) {
                            fullResponse = data.full || (fullResponse + data.content);

                            if (!textDiv) {
                                const messageContent = assistantMessageDiv.querySelector('.message-content');
                                textDiv = document.createElement('div');
                                textDiv.className = 'message-text';
                                messageContent.innerHTML = '';
                                messageContent.appendChild(textDiv);
                            }

                            textDiv.innerHTML = formatMessageWithCode(fullResponse);
                            messagesContainer.scrollTop = messagesContainer.scrollHeight;

                            const codeBlocks = textDiv.querySelectorAll('pre code');
                            codeBlocks.forEach(block => hljs.highlightElement(block));
                            // Добавляем кнопки копирования для блоков кода при стриминге
                            addCopyButtonsToCodeBlocks(textDiv);
                        }

                        if (data.done) {
                            fullResponse = data.full || fullResponse;
                            if (textDiv) {
                                textDiv.innerHTML = formatMessageWithCode(fullResponse);
                                addCopyButtonsToCodeBlocks(textDiv);
                            }
                        }
                    } catch (e) {
                        console.error('Ошибка парсинга JSON:', e);
                    }
                }
            }
        }

        // Успешное завершение — добавляем кнопки
        if (fullResponse && !fullResponse.includes('Генерация прервана')) {
            addButtonsToMessage(assistantMessageDiv, 'assistant', fullResponse);
            addCopyButtonsToCodeBlocks(assistantMessageDiv);
            conversationHistory.push({ role: 'assistant', content: fullResponse });
            updateContextCount();
            saveHistory();
            setStatus('Готов');

            if (hadImage) {
                removeImage();
            }
        } else if (fullResponse.includes('Генерация прервана')) {
            // Добавляем кнопки даже для прерванного сообщения
            addButtonsToMessage(assistantMessageDiv, 'assistant', fullResponse);
            addCopyButtonsToCodeBlocks(assistantMessageDiv);
            conversationHistory.pop();
            updateContextCount();
            saveHistory();
        }

    } catch (error) {
        console.error('Ошибка:', error);
        let errorMessage = "";
        if (error.name === 'AbortError') {
            errorMessage = fullResponse ? fullResponse + "\n\n⏹️ Генерация отменена" : "⏹️ Генерация отменена";
            if (textDiv) {
                textDiv.innerHTML = formatMessageWithCode(errorMessage);
                addCopyButtonsToCodeBlocks(textDiv);
            } else {
                const messageContent = assistantMessageDiv.querySelector('.message-content');
                messageContent.innerHTML = `<div class="message-text">${escapeHtml(errorMessage)}</div>`;
            }
            // Добавляем кнопки для отменённого сообщения
            addButtonsToMessage(assistantMessageDiv, 'assistant', errorMessage);
            addCopyButtonsToCodeBlocks(assistantMessageDiv);
            conversationHistory.pop();
            updateContextCount();
            saveHistory();
        } else {
            errorMessage = error.message || 'Неизвестная ошибка';
            const errorText = `❌ Ошибка: ${errorMessage}`;
            if (textDiv) {
                textDiv.innerHTML = formatMessageWithCode(errorText);
                addCopyButtonsToCodeBlocks(textDiv);
            } else {
                const messageContent = assistantMessageDiv.querySelector('.message-content');
                messageContent.innerHTML = `<div class="message-text">${escapeHtml(errorText)}</div>`;
            }
            addButtonsToMessage(assistantMessageDiv, 'assistant', errorText);
            addCopyButtonsToCodeBlocks(assistantMessageDiv);
            conversationHistory.pop();
            updateContextCount();
            saveHistory();
            setStatus('Ошибка', true);
        }
    } finally {
        activeRequest = false;
        currentRequestId = null;
        currentAbortController = null;
        const stopBtn = document.getElementById('stop-generation-btn');
        if (stopBtn) stopBtn.style.display = 'none';
        setDeleteButtonsState(false);  // разблокируем кнопки удаления
        updateUIForBlockState();
    }
}

function showNotification(message, type = 'error') {
    const existing = document.querySelector('.custom-notification');
    if (existing) existing.remove();

    const notification = document.createElement('div');
    notification.className = `custom-notification ${type}`;
    notification.innerHTML = `
        <i class="fas ${type === 'error' ? 'fa-exclamation-triangle' : type === 'success' ? 'fa-check-circle' : 'fa-info-circle'}"></i>
        <span>${message}</span>
    `;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => notification.remove(), 300);
    }, 4000);
}

// === ОБРАБОТЧИКИ СОБЫТИЙ ===
function openDrawer() {
    drawerMenu.classList.add('open');
    drawerOverlay.classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeDrawer() {
    drawerMenu.classList.remove('open');
    drawerOverlay.classList.remove('active');
    document.body.style.overflow = '';
}

function toggleAdvanced() {
    isAdvancedOpen = !isAdvancedOpen;
    if (isAdvancedOpen) {
        advancedContent.classList.add('open');
        advancedToggle.classList.add('open');
        const icon = advancedToggle.querySelector('.expand-icon');
        if (icon) icon.style.transform = 'rotate(180deg)';
    } else {
        advancedContent.classList.remove('open');
        advancedToggle.classList.remove('open');
        const icon = advancedToggle.querySelector('.expand-icon');
        if (icon) icon.style.transform = 'rotate(0deg)';
    }
    localStorage.setItem('advanced_open', isAdvancedOpen);
}

// === ИНИЦИАЛИЗАЦИЯ ===
menuToggleBtn?.addEventListener('click', openDrawer);
openDrawerBtn?.addEventListener('click', openDrawer);
drawerClose?.addEventListener('click', closeDrawer);
drawerOverlay?.addEventListener('click', closeDrawer);
advancedToggle?.addEventListener('click', toggleAdvanced);

if (isAdvancedOpen && advancedContent) {
    advancedContent.classList.add('open');
    advancedToggle?.classList.add('open');
}

temperature?.addEventListener('input', () => {
    document.getElementById('temp-value').textContent = temperature.value;
    saveSettings();
});
topP?.addEventListener('input', () => {
    document.getElementById('topp-value').textContent = topP.value;
    saveSettings();
});
topK?.addEventListener('input', () => {
    document.getElementById('topk-value').textContent = topK.value;
    saveSettings();
});
frequencyPenalty?.addEventListener('input', () => {
    document.getElementById('freq-value').textContent = frequencyPenalty.value;
    saveSettings();
});
presencePenalty?.addEventListener('input', () => {
    document.getElementById('presence-value').textContent = presencePenalty.value;
    saveSettings();
});
repeatPenalty?.addEventListener('input', () => {
    document.getElementById('repeat-value').textContent = repeatPenalty.value;
    saveSettings();
});
maxTokens?.addEventListener('input', () => {
    document.getElementById('max-tokens-value').textContent = maxTokens.value;
    saveSettings();
});
systemPrompt?.addEventListener('change', saveSettings);
seedInput?.addEventListener('change', saveSettings);
modelSelect?.addEventListener('change', () => {
    localStorage.setItem('selected_model', modelSelect.value);
    showNotification(`Выбрана модель: ${modelSelect.value}`, 'success');
});

clearChatBtn?.addEventListener('click', clearChat);
resetSettingsBtn?.addEventListener('click', resetSettings);

// Обработчики для изображений
uploadImageBtn?.addEventListener('click', () => {
    imageInput.click();
});

imageInput?.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
        handleImageUpload(e.target.files[0]);
    }
});

removeImageBtn?.addEventListener('click', removeImage);

// Drag & drop для изображений
imageUploadArea?.addEventListener('dragover', (e) => {
    e.preventDefault();
    imageUploadArea.classList.add('drag-over');
});

imageUploadArea?.addEventListener('dragleave', () => {
    imageUploadArea.classList.remove('drag-over');
});

imageUploadArea?.addEventListener('drop', (e) => {
    e.preventDefault();
    imageUploadArea.classList.remove('drag-over');
    const files = e.dataTransfer.files;
    if (files.length > 0 && files[0].type.startsWith('image/')) {
        handleImageUpload(files[0]);
    } else {
        showNotification('Пожалуйста, перетащите файл изображения', 'error');
    }
});

userInput?.addEventListener('input', function() {
    this.style.height = 'auto';
    this.style.height = Math.min(this.scrollHeight, 150) + 'px';
});

userInput?.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

sendBtn?.addEventListener('click', sendMessage);

// === ЗАПУСК ===
addStopButton();
loadModels();
loadSettings();
loadHistory();
loadBlockState();
updateUIForBlockState();

console.log('💬 Чат с LM Studio готов!');
console.log('  - Лимит токенов: 4096');
console.log('  - Поддержка изображений (Vision)');
console.log('  - Изображение удаляется ТОЛЬКО после успешной генерации');

hljs.highlightAll();