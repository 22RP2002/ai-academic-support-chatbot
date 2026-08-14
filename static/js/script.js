const chatWindow = document.getElementById("chat-window");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const suggestions = document.getElementById("suggestions");

const sidebar = document.getElementById("sidebar");
const sidebarToggle = document.getElementById("sidebar-toggle");
const sidebarBackdrop = document.getElementById("sidebar-backdrop");
const newChatBtn = document.getElementById("new-chat-btn");
const conversationList = document.getElementById("conversation-list");
const shareBtn = document.getElementById("share-btn");
const profileBtn = document.getElementById("profile-btn");
const profileDropdown = document.getElementById("profile-dropdown");
const toast = document.getElementById("toast");

let currentConversationId =
  (window.__INITIAL_STATE__ && window.__INITIAL_STATE__.conversationId) || null;
let toastTimer = null;

function scrollToBottom() {
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 2500);
}

// Wraps fetch() for the protected /api/* endpoints: if the session has
// expired or logged out in another tab, the backend returns 401 — send
// the user back to the login page instead of showing a confusing error.
async function apiFetch(url, options) {
  const res = await fetch(url, options);
  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("unauthenticated");
  }
  return res;
}

function createFeedbackElement(messageId, existingRating) {
  const container = document.createElement("div");
  container.className = "feedback";
  container.dataset.messageId = messageId;

  ["up", "down"].forEach((rating) => {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `feedback-btn feedback-${rating}` + (existingRating === rating ? " selected" : "");
    btn.dataset.rating = rating;
    btn.setAttribute("aria-label", rating === "up" ? "Helpful" : "Not helpful");
    btn.textContent = rating === "up" ? "👍" : "👎";
    btn.disabled = Boolean(existingRating);
    container.appendChild(btn);
  });

  const thanks = document.createElement("span");
  thanks.className = "feedback-thanks";
  thanks.textContent = "Thanks for your feedback!";
  thanks.hidden = !existingRating;
  container.appendChild(thanks);

  return container;
}

function appendMessage(text, sender, meta, messageId, existingRating) {
  const wrapper = document.createElement("div");
  wrapper.className = `message ${sender}`;

  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrapper.appendChild(bubble);

  if (meta) {
    const metaEl = document.createElement("div");
    metaEl.className = "meta";
    metaEl.textContent = meta;
    wrapper.appendChild(metaEl);
  }

  if (sender === "bot" && messageId != null) {
    wrapper.appendChild(createFeedbackElement(messageId, existingRating || null));
  }

  chatWindow.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

function renderTurn(turn) {
  appendMessage(turn.message, "user");
  appendMessage(
    turn.response,
    "bot",
    `intent: ${turn.intent} · confidence: ${Number(turn.confidence).toFixed(2)}`,
    turn.id,
    turn.feedback_rating
  );
}

function showWelcome() {
  appendMessage(
    "Hi! I'm your academic support assistant. Try asking me about exam schedules, assignment deadlines, attendance policy, or study tips.",
    "bot"
  );
}

async function submitFeedback(container, rating) {
  const messageId = Number(container.dataset.messageId);
  const buttons = container.querySelectorAll(".feedback-btn");
  const thanks = container.querySelector(".feedback-thanks");

  buttons.forEach((btn) => (btn.disabled = true));

  try {
    const res = await apiFetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId, rating }),
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      throw new Error(data.error || "request failed");
    }

    buttons.forEach((btn) => {
      btn.classList.toggle("selected", btn.dataset.rating === rating);
    });
    thanks.hidden = false;
  } catch (err) {
    buttons.forEach((btn) => (btn.disabled = false));
    let errorEl = container.querySelector(".feedback-error");
    if (!errorEl) {
      errorEl = document.createElement("span");
      errorEl.className = "feedback-error";
      container.appendChild(errorEl);
    }
    errorEl.textContent = "Couldn't save feedback — try again.";
  }
}

chatWindow.addEventListener("click", (e) => {
  const btn = e.target.closest(".feedback-btn");
  if (!btn || btn.disabled) return;
  const container = btn.closest(".feedback");
  if (!container) return;
  submitFeedback(container, btn.dataset.rating);
});

function appendTyping() {
  const wrapper = document.createElement("div");
  wrapper.className = "message bot typing";
  wrapper.innerHTML = '<div class="bubble">Typing…</div>';
  chatWindow.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

async function sendMessage(text) {
  appendMessage(text, "user");
  const typingEl = appendTyping();

  try {
    const res = await apiFetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    const data = await res.json();
    typingEl.remove();

    if (data.error) {
      appendMessage("Something went wrong: " + data.error, "bot");
      return;
    }

    currentConversationId = data.conversation_id;

    appendMessage(
      data.response,
      "bot",
      `intent: ${data.intent} · confidence: ${data.confidence.toFixed(2)}`,
      data.message_id
    );

    loadConversations();
  } catch (err) {
    typingEl.remove();
    appendMessage("Network error — is the Flask server running?", "bot");
  }
}

chatForm.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = messageInput.value.trim();
  if (!text) return;
  messageInput.value = "";
  sendMessage(text);
});

suggestions.addEventListener("click", (e) => {
  if (e.target.classList.contains("chip")) {
    sendMessage(e.target.textContent);
  }
});

// --- Sidebar: conversation list ------------------------------------------

function renderConversationList(items) {
  conversationList.innerHTML = "";

  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "empty-history";
    empty.id = "empty-history";
    empty.textContent = "No conversations yet — start chatting!";
    conversationList.appendChild(empty);
    return;
  }

  items.forEach((conv) => {
    const item = document.createElement("div");
    item.className = "conversation-item" + (conv.id === currentConversationId ? " active" : "");
    item.dataset.conversationId = conv.id;

    const openBtn = document.createElement("button");
    openBtn.type = "button";
    openBtn.className = "conversation-open";
    openBtn.dataset.conversationId = conv.id;
    const titleSpan = document.createElement("span");
    titleSpan.className = "conversation-title";
    titleSpan.textContent = conv.title;
    openBtn.appendChild(titleSpan);

    const delBtn = document.createElement("button");
    delBtn.type = "button";
    delBtn.className = "conversation-delete";
    delBtn.dataset.conversationId = conv.id;
    delBtn.setAttribute("aria-label", "Delete conversation");
    delBtn.title = "Delete conversation";
    delBtn.textContent = "🗑";

    item.appendChild(openBtn);
    item.appendChild(delBtn);
    conversationList.appendChild(item);
  });
}

function highlightActiveConversation() {
  conversationList.querySelectorAll(".conversation-item").forEach((item) => {
    item.classList.toggle("active", item.dataset.conversationId === currentConversationId);
  });
}

async function loadConversations() {
  try {
    const res = await apiFetch("/api/conversations");
    if (!res.ok) return;
    renderConversationList(await res.json());
  } catch (err) {
    // Sidebar refresh is best-effort; a failure here shouldn't break chat.
  }
}

async function openConversation(conversationId) {
  try {
    const res = await apiFetch(`/api/conversations/${conversationId}`);
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(data.error || "Couldn't open that conversation.");
      return;
    }

    currentConversationId = data.conversation.id;
    chatWindow.innerHTML = "";
    data.messages.forEach(renderTurn);
    scrollToBottom();
    highlightActiveConversation();
    closeSidebarDrawer();
  } catch (err) {
    showToast("Network error — couldn't open that conversation.");
  }
}

async function deleteConversationHandler(conversationId) {
  if (!window.confirm("Delete this conversation? This cannot be undone.")) return;

  try {
    const res = await apiFetch(`/api/conversations/${conversationId}`, { method: "DELETE" });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(data.error || "Couldn't delete that conversation.");
      return;
    }

    if (conversationId === currentConversationId) {
      currentConversationId = null;
      chatWindow.innerHTML = "";
      showWelcome();
    }

    loadConversations();
  } catch (err) {
    showToast("Network error — couldn't delete that conversation.");
  }
}

sidebar.addEventListener("click", (e) => {
  const delBtn = e.target.closest(".conversation-delete");
  if (delBtn) {
    e.stopPropagation();
    deleteConversationHandler(delBtn.dataset.conversationId);
    return;
  }

  const openBtn = e.target.closest(".conversation-open");
  if (openBtn) {
    openConversation(openBtn.dataset.conversationId);
  }
});

newChatBtn.addEventListener("click", async () => {
  try {
    await apiFetch("/api/reset", { method: "POST" });
  } catch (err) {
    // Fall through and clear the local view even if the request failed.
  }
  currentConversationId = null;
  chatWindow.innerHTML = "";
  showWelcome();
  highlightActiveConversation();
  closeSidebarDrawer();
});

// --- Sidebar: mobile drawer -----------------------------------------------

function openSidebarDrawer() {
  sidebar.classList.add("open");
  sidebarBackdrop.hidden = false;
}

function closeSidebarDrawer() {
  sidebar.classList.remove("open");
  sidebarBackdrop.hidden = true;
}

sidebarToggle.addEventListener("click", () => {
  if (sidebar.classList.contains("open")) {
    closeSidebarDrawer();
  } else {
    openSidebarDrawer();
  }
});

sidebarBackdrop.addEventListener("click", closeSidebarDrawer);

// --- Share ------------------------------------------------------------

shareBtn.addEventListener("click", async () => {
  if (!currentConversationId) {
    showToast("Start a conversation first.");
    return;
  }

  try {
    const res = await apiFetch(`/api/conversations/${currentConversationId}/share`, {
      method: "POST",
    });
    const data = await res.json();

    if (!res.ok || data.error) {
      showToast(data.error || "Couldn't create a share link.");
      return;
    }

    const shareUrl = `${window.location.origin}${data.share_url}`;
    try {
      await navigator.clipboard.writeText(shareUrl);
      showToast("Link copied!");
    } catch (clipboardErr) {
      window.prompt("Copy this link:", shareUrl);
    }
  } catch (err) {
    showToast("Network error — couldn't create a share link.");
  }
});

// --- Profile menu -----------------------------------------------------
// "Profile"/"Settings" are real links and "Logout" a real form (see
// templates/index.html) — no JS wiring needed for them beyond the
// open/close toggle below.

profileBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const isOpen = !profileDropdown.hidden;
  profileDropdown.hidden = isOpen;
  profileBtn.setAttribute("aria-expanded", String(!isOpen));
});

document.addEventListener("click", (e) => {
  if (!profileDropdown.hidden && !e.target.closest(".profile-menu")) {
    profileDropdown.hidden = true;
    profileBtn.setAttribute("aria-expanded", "false");
  }
});

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !profileDropdown.hidden) {
    profileDropdown.hidden = true;
    profileBtn.setAttribute("aria-expanded", "false");
  }
});

scrollToBottom();
