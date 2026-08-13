const chatWindow = document.getElementById("chat-window");
const chatForm = document.getElementById("chat-form");
const messageInput = document.getElementById("message-input");
const resetBtn = document.getElementById("reset-btn");
const suggestions = document.getElementById("suggestions");

function scrollToBottom() {
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function appendMessage(text, sender, meta) {
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

  chatWindow.appendChild(wrapper);
  scrollToBottom();
  return wrapper;
}

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
      `intent: ${data.intent} · confidence: ${data.confidence.toFixed(2)}`
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
