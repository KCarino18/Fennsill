const form = document.querySelector("#login-form");
const account = document.querySelector("#account");
const formError = document.querySelector("#form-error");
const who = document.querySelector("#who");
const subLine = document.querySelector("#sub-line");
const statusLine = document.querySelector("#status");

function showError(message) {
  formError.textContent = message;
  formError.classList.remove("hidden");
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || "That did not work.");
  return data;
}

function showAccount(me) {
  form.classList.add("hidden");
  account.classList.remove("hidden");
  who.textContent = me.email;
  subLine.textContent = me.subscription
    ? "Connected to the " + me.subscription + " subscription you pay for."
    : "No subscription connected yet. Pick the AI you use.";
  statusLine.textContent = me.devices && me.devices.length
    ? "Panel linked. Open Fennsill.exe — MCP for Claude/Cursor, Paste/Import for ChatGPT/Gemini/Grok."
    : "Plug in the panel with the data cable, then press the button below.";
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  formError.classList.add("hidden");
  const mode = form.querySelector("input[name=mode]:checked").value;
  try {
    await postJson("/api/session", {
      email: document.querySelector("#email").value.trim(),
      password: document.querySelector("#password").value,
      mode,
    });
    showAccount(await (await fetch("/api/me")).json());
  } catch (error) {
    showError(error.message || "That did not work.");
  }
});

document.querySelector("#providers").addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-provider]");
  if (!button) return;
  statusLine.textContent = "";
  try {
    await postJson("/api/subscription", { provider: button.dataset.provider });
    showAccount(await (await fetch("/api/me")).json());
  } catch (error) {
    statusLine.textContent = error.message;
  }
});

document.querySelector("#plug").addEventListener("click", async () => {
  statusLine.textContent = "";
  try {
    await postJson("/api/device/link", {});
    showAccount(await (await fetch("/api/me")).json());
  } catch (error) {
    statusLine.textContent = error.message;
  }
});

fetch("/api/me").then(async (response) => {
  if (response.ok) showAccount(await response.json());
});
