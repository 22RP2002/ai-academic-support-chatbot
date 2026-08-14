const chatWindow = document.getElementById("chat-window");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const resetBtn = document.getElementById("reset-btn");
const suggestions = document.getElementById("suggestions");

function scrollToBottom() {
  chatWindow.scrollTop = chatWindow.scrollHeight;
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

function appendMessage(text, sender, meta, messageId) {
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
    wrapper.appendChild(createFeedbackElement(messageId, null));
  }

  chatWindow.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

async function submitFeedback(container, rating) {
  const messageId = Number(container.dataset.messageId);
  const buttons = container.querySelectorAll(".feedback-btn");
  const thanks = container.querySelector(".feedback-thanks");

  buttons.forEach((btn) => (btn.disabled = true));

  try {
    const res = await fetch("/api/feedback", {
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
    const res = await fetch("/api/chat", {
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

    appendMessage(
      data.response,
      "bot",
      `intent: ${data.intent} · confidence: ${data.confidence.toFixed(2)}`,
      data.message_id
    );
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

resetBtn.addEventListener("click", async () => {
  await fetch("/api/reset", { method: "POST" });
  chatWindow.innerHTML = "";
  appendMessage(
    "Hi! I'm your academic support assistant. Try asking me about exam schedules, assignment deadlines, attendance policy, or study tips.",
    "bot"
  );
});

scrollToBottom();
