// Front-end JavaScript logic connecting to local ADK playground server
const API_BASE = 'http://127.0.0.1:18081';
const USER_ID = 'user';
const APP_NAME = 'app';

// Local copy of cafeteria items for display
const menuItems = [
    {
        name: "Garden Salad",
        price: 8.50,
        desc: "Fresh mixed greens, cherry tomatoes, cucumbers, shredded carrots, balsamic vinaigrette.",
        category: "mains",
        tags: ["veg", "gf"],
        stock: 25
    },
    {
        name: "Turkey Club",
        price: 10.00,
        desc: "Sliced turkey breast, crispy bacon, lettuce, tomato, swiss cheese, and mayo on toasted sourdough.",
        category: "mains",
        tags: [],
        stock: 15
    },
    {
        name: "Quinoa Bowl",
        price: 11.50,
        desc: "Warm quinoa, roasted sweet potatoes, avocado, black beans, kale, and lemon-tahini dressing.",
        category: "mains",
        tags: ["veg", "gf", "v"],
        stock: 0 // Out of stock to test check_inventory
    },
    {
        name: "Drip Coffee",
        price: 3.00,
        desc: "House blend medium roast freshly brewed coffee.",
        category: "beverages",
        tags: [],
        stock: 50
    },
    {
        name: "Matcha Latte",
        price: 4.50,
        desc: "Uji matcha green tea whisked with steamed milk or oat milk.",
        category: "beverages",
        tags: ["veg"],
        stock: 20
    }
];

let sessionId = null;
let currentInvocationId = null;

// DOM Elements
const menuGrid = document.getElementById('menu-items-grid');
const searchInput = document.getElementById('menu-search-input');
const categoryTabs = document.querySelectorAll('.category-tab');
const chatMessages = document.getElementById('chat-messages-thread');
const chatForm = document.getElementById('chat-input-form');
const chatInput = document.getElementById('chat-user-input');
const resetBtn = document.getElementById('reset-session-btn');
const suggestionChips = document.querySelectorAll('.chip');
const hitlOverlay = document.getElementById('hitl-overlay');
const hitlText = document.getElementById('hitl-message-text');
const hitlApproveBtn = document.getElementById('hitl-approve-btn');
const hitlRejectBtn = document.getElementById('hitl-reject-btn');

// Initial Setup
document.addEventListener('DOMContentLoaded', () => {
    renderMenu(menuItems);
    setupEventListeners();
    initSession();
});

// Render menu items
function renderMenu(items) {
    menuGrid.innerHTML = '';
    items.forEach(item => {
        const isOutOfStock = item.stock <= 0;
        const card = document.createElement('div');
        card.className = `menu-card ${isOutOfStock ? 'out-of-stock' : ''}`;
        
        // Tags
        let tagsHtml = '';
        item.tags.forEach(tag => {
            let label = tag.toUpperCase();
            if (tag === 'veg') label = 'Vegetarian';
            if (tag === 'gf') label = 'Gluten-Free';
            if (tag === 'v') label = 'Vegan';
            tagsHtml += `<span class="card-tag tag-${tag}">${label}</span>`;
        });

        card.innerHTML = `
            <div class="card-top">
                <div class="card-tags">${tagsHtml}</div>
                ${isOutOfStock ? `<span class="stock-tag">OUT OF STOCK</span>` : ''}
                <h3 class="card-title">${item.name}</h3>
                <p class="card-desc">${item.desc}</p>
            </div>
            <div class="card-bottom">
                <div class="card-price">$${item.price.toFixed(2)}</div>
                <button class="add-order-btn" title="${isOutOfStock ? 'Out of Stock' : 'Order Now'}" onclick="quickOrder('${item.name}')">
                    <i class="fa-solid fa-plus"></i>
                </button>
            </div>
        `;
        menuGrid.appendChild(card);
    });
}

// Event Listeners setup
function setupEventListeners() {
    // Search Menu
    searchInput.addEventListener('input', () => {
        filterMenu();
    });

    // Category Tabs Filter
    categoryTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            categoryTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            filterMenu();
        });
    });

    // Chat form submit
    chatForm.addEventListener('submit', (e) => {
        e.preventDefault();
        sendMessage();
    });

    // Suggestion Chips
    suggestionChips.forEach(chip => {
        chip.addEventListener('click', () => {
            const query = chip.textContent.slice(2).trim(); // Slice emoji
            chatInput.value = query;
            sendMessage();
        });
    });

    // Reset button
    resetBtn.addEventListener('click', () => {
        resetSession();
    });

    // HITL Approve
    hitlApproveBtn.addEventListener('click', () => {
        submitHITLResponse("yes");
    });

    // HITL Reject
    hitlRejectBtn.addEventListener('click', () => {
        submitHITLResponse("no");
    });
}

// Filter Menu Items
function filterMenu() {
    const query = searchInput.value.toLowerCase().trim();
    const activeTab = document.querySelector('.category-tab.active').getAttribute('data-category');

    const filtered = menuItems.filter(item => {
        const matchesQuery = item.name.toLowerCase().includes(query) || 
                             item.desc.toLowerCase().includes(query) ||
                             item.tags.some(t => t.toLowerCase().includes(query));
        const matchesCategory = activeTab === 'all' || item.category === activeTab;
        return matchesQuery && matchesCategory;
    });

    renderMenu(filtered);
}

// Initialize ADK Session
async function initSession() {
    try {
        const res = await fetch(`${API_BASE}/apps/${APP_NAME}/users/${USER_ID}/sessions`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        const data = await res.json();
        sessionId = data.id;
        console.log("Initialized Session:", sessionId);
    } catch (err) {
        console.error("Failed to initialize session:", err);
        appendMessage('system', "⚠️ Connection Error: Failed to connect to ADK server on port 18081. Make sure the playground server is running.");
    }
}

// Reset Session
async function resetSession() {
    chatMessages.innerHTML = `
        <div class="message system-msg">
            <div class="msg-bubble">
                <p>🔄 Session reset. Hello! I am your AI Cafeteria Assistant. How can I help you today?</p>
            </div>
        </div>
    `;
    hitlOverlay.style.display = 'none';
    currentInvocationId = null;
    await initSession();
}

// Quick Order Helper from Menu Cards
function quickOrder(itemName) {
    chatInput.value = `I'd like to place an order for one ${itemName} please.`;
    sendMessage();
}

// Append message bubble to chat
function appendMessage(sender, text) {
    const isUser = sender === 'user';
    const isSystem = sender === 'system';
    
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${isUser ? 'user-msg' : (isSystem ? 'system-msg' : 'assistant-msg')}`;

    const now = new Date();
    const timeStr = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    msgDiv.innerHTML = `
        <div class="msg-bubble">
            <p>${text}</p>
        </div>
        ${!isSystem ? `<span class="msg-meta">${isUser ? 'You' : 'Assistant'} • ${timeStr}</span>` : ''}
    `;

    chatMessages.appendChild(msgDiv);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Show/Hide typing indicator
let typingIndicator = null;
function showTypingIndicator() {
    if (typingIndicator) return;
    
    typingIndicator = document.createElement('div');
    typingIndicator.className = 'typing-indicator';
    typingIndicator.innerHTML = `
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
        <span class="typing-dot"></span>
    `;
    chatMessages.appendChild(typingIndicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function hideTypingIndicator() {
    if (typingIndicator) {
        typingIndicator.remove();
        typingIndicator = null;
    }
}

// Send Message to Agent API
async function sendMessage() {
    const text = chatInput.value.trim();
    if (!text) return;

    appendMessage('user', text);
    chatInput.value = '';
    showTypingIndicator();

    if (!sessionId) {
        await initSession();
    }

    try {
        const payload = {
            appName: APP_NAME,
            userId: USER_ID,
            sessionId: sessionId,
            newMessage: {
                role: 'user',
                parts: [{ text: text }]
            }
        };

        const res = await fetch(`${API_BASE}/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (!res.ok) {
            throw new Error(`API returned ${res.status}`);
        }

        const events = await res.json();
        hideTypingIndicator();
        processEvents(events);

    } catch (err) {
        console.error("Error sending message:", err);
        hideTypingIndicator();
        appendMessage('system', "⚠️ Error: Failed to retrieve response from the agent. Is the server running?");
    }
}

// Process Response Events from Agent
function processEvents(events) {
    let assistantText = "";
    let isHitlTriggered = false;

    events.forEach(event => {
        // Log event details for debugging
        console.log("Received Event:", event);

        // Check if there is written content
        if (event.content && event.content.parts) {
            event.content.parts.forEach(part => {
                if (part.text && event.author !== 'user') {
                    assistantText += part.text;
                }
                
                // Catch request_input inside content parts
                if (part.functionCall && part.functionCall.name === 'adk_request_input') {
                    const args = part.functionCall.args;
                    currentInvocationId = event.invocationId;
                    triggerHITL(args.message);
                    isHitlTriggered = true;
                }
            });
        }
        
        // Alternate way HITL can manifest in action payloads
        if (event.actions && event.actions.requestedToolConfirmations && Object.keys(event.actions.requestedToolConfirmations).length > 0) {
            // Wait confirm
        }
    });

    if (assistantText.trim()) {
        appendMessage('assistant', assistantText);
    }
}

// Trigger Human-In-The-Loop Approval card
function triggerHITL(messageText) {
    hitlText.textContent = messageText;
    hitlOverlay.style.display = 'block';
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

// Submit Response to HITL
async function submitHITLResponse(responseVal) {
    if (!sessionId || !currentInvocationId) return;

    appendMessage('user', responseVal);
    hitlOverlay.style.display = 'none';
    showTypingIndicator();

    try {
        const payload = {
            appName: APP_NAME,
            userId: USER_ID,
            sessionId: sessionId,
            invocationId: currentInvocationId,
            newMessage: {
                role: 'user',
                parts: [{ text: responseVal }]
            }
        };

        const res = await fetch(`${API_BASE}/run`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        const events = await res.json();
        hideTypingIndicator();
        currentInvocationId = null;
        processEvents(events);

    } catch (err) {
        console.error("Error submitting approval:", err);
        hideTypingIndicator();
        appendMessage('system', "⚠️ Error: Failed to submit approval response.");
    }
}
