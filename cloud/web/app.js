(() => {
  const TOKEN_KEY = "fennsill_user_token";
  const EMAIL_KEY = "fennsill_user_email";

  const authPanel = document.getElementById("auth-panel");
  const accountPanel = document.getElementById("account-panel");
  const authForm = document.getElementById("auth-form");
  const authError = document.getElementById("auth-error");
  const authSubmit = document.getElementById("auth-submit");
  const who = document.getElementById("who");
  const subStatus = document.getElementById("sub-status");
  const mcpUrlEl = document.getElementById("mcp-url");
  const userTokenEl = document.getElementById("user-token");
  const authHeaderEl = document.getElementById("auth-header");
  const deviceList = document.getElementById("device-list");
  const deviceError = document.getElementById("device-error");
  const deviceTokenRow = document.getElementById("device-token-row");
  const deviceTokenEl = document.getElementById("device-token");

  let mode = "signup";
  let mcpUrl = "https://mcp.fennsill.com/mcp";

  function token() {
    return localStorage.getItem(TOKEN_KEY) || "";
  }

  function setSession(tok, email) {
    localStorage.setItem(TOKEN_KEY, tok);
    localStorage.setItem(EMAIL_KEY, email || "");
  }

  function clearSession() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(EMAIL_KEY);
  }

  async function api(path, opts = {}) {
    const headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    if (token()) headers.Authorization = `Bearer ${token()}`;
    const res = await fetch(path, { ...opts, headers });
    const text = await res.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = { error: text || res.statusText };
    }
    if (!res.ok) {
      const err = new Error((body && (body.error || body.message)) || res.statusText);
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  }

  function showAuth() {
    authPanel.hidden = false;
    accountPanel.hidden = true;
  }

  const DEVICE_ID_RE = /^FS[0-9A-F]{12}$/i;
  let selectedDeviceId = "";

  function showAccount(me) {
    authPanel.hidden = true;
    accountPanel.hidden = false;
    who.textContent = me.email || localStorage.getItem(EMAIL_KEY) || "";
    const sub = me.subscribed
      ? `Access active until ${me.current_period_end || "—"}`
      : `Status: ${me.status || "pending"} (clock starts after panel heartbeat + first MCP call)`;
    subStatus.textContent = sub;
    mcpUrlEl.textContent = mcpUrl;
    userTokenEl.textContent = token();
    authHeaderEl.textContent = `Bearer ${token()}`;
    deviceList.innerHTML = "";
    const devices = me.devices || [];
    if (
      selectedDeviceId &&
      !devices.some((d) => d.device_id === selectedDeviceId)
    ) {
      selectedDeviceId = "";
    }
    if (!selectedDeviceId && devices[0]) selectedDeviceId = devices[0].device_id;
    devices.forEach((d) => {
      const li = document.createElement("li");
      const online = d.online ? " (online)" : d.last_seen_at ? " (offline)" : " (no heartbeat yet)";
      li.textContent = `${d.device_id}${d.label ? " — " + d.label : ""}${online}`;
      li.dataset.deviceId = d.device_id;
      li.tabIndex = 0;
      li.classList.toggle("selected", d.device_id === selectedDeviceId);
      li.addEventListener("click", () => {
        selectedDeviceId = d.device_id;
        deviceList.querySelectorAll("li").forEach((el) => {
          el.classList.toggle("selected", el.dataset.deviceId === selectedDeviceId);
        });
        document.getElementById("device-id").value = d.device_id;
      });
      deviceList.appendChild(li);
    });
  }

  function resolveMintDeviceId() {
    const typed = document.getElementById("device-id").value.trim().toUpperCase();
    const linked = Array.from(deviceList.querySelectorAll("li")).map((li) =>
      (li.dataset.deviceId || "").toUpperCase()
    );
    // Prefer an explicit linked selection — never mint a box serial from the text box.
    if (selectedDeviceId && linked.includes(selectedDeviceId.toUpperCase())) {
      return selectedDeviceId.toUpperCase();
    }
    if (DEVICE_ID_RE.test(typed) && linked.includes(typed)) return typed;
    if (DEVICE_ID_RE.test(typed)) return typed;
    if (linked[0]) return linked[0];
    return "";
  }

  async function refreshMe() {
    const me = await api("/api/me");
    showAccount(me);
    return me;
  }

  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      mode = btn.dataset.mode;
      document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b === btn));
      authSubmit.textContent = mode === "signup" ? "Create account" : "Log in";
      authError.hidden = true;
    });
  });

  authForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    authError.hidden = true;
    try {
      const body = await api("/api/session", {
        method: "POST",
        body: JSON.stringify({
          mode,
          email: document.getElementById("email").value.trim(),
          password: document.getElementById("password").value,
        }),
      });
      setSession(body.token, body.email);
      await refreshMe();
    } catch (err) {
      authError.textContent = err.message || "Could not sign in.";
      authError.hidden = false;
    }
  });

  document.getElementById("link-device").addEventListener("click", async () => {
    deviceError.hidden = true;
    try {
      await api("/api/devices", {
        method: "POST",
        body: JSON.stringify({
          device_id: document.getElementById("device-id").value.trim(),
          label: document.getElementById("device-label").value.trim(),
        }),
      });
      await refreshMe();
    } catch (err) {
      deviceError.textContent = err.message || "Could not link device.";
      deviceError.hidden = false;
    }
  });

  document.getElementById("mint-token").addEventListener("click", async () => {
    deviceError.hidden = true;
    const deviceId = resolveMintDeviceId();
    if (!deviceId) {
      deviceError.textContent =
        "Link a panel first (Device ID looks like FS + 12 hex digits from Fennsill.exe — not the box serial FS-YYMM-######).";
      deviceError.hidden = false;
      return;
    }
    if (!DEVICE_ID_RE.test(deviceId)) {
      deviceError.textContent =
        `"${deviceId}" is not a Device ID. Use the FS############ value from Fennsill.exe, not the serial.`;
      deviceError.hidden = false;
      return;
    }
    try {
      const body = await api("/api/device/token", {
        method: "POST",
        body: JSON.stringify({ device_id: deviceId }),
      });
      deviceTokenEl.textContent = body.token;
      deviceTokenRow.hidden = false;
      deviceError.hidden = true;
      const note = document.getElementById("device-token-note");
      if (note) {
        note.hidden = false;
        note.textContent =
          `Key for ${deviceId}. In Fennsill.exe click “Paste device key” (not the MCP Authorization header). Keep Fennsill open until it says Cloud: checked in.`;
      }
    } catch (err) {
      const msg = err.message || "Could not mint device key.";
      deviceError.textContent =
        err.status === 403
          ? `${msg} If access is inactive/expired, renew on this account, then mint again.`
          : msg;
      deviceError.hidden = false;
    }
  });

  document.getElementById("sign-out").addEventListener("click", () => {
    clearSession();
    showAuth();
  });

  document.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const el = document.getElementById(btn.dataset.copy);
      if (!el) return;
      try {
        await navigator.clipboard.writeText(el.textContent || "");
        btn.textContent = "Copied";
        setTimeout(() => {
          btn.textContent = btn.dataset.copy === "auth-header" ? "Copy header" : "Copy";
        }, 1200);
      } catch {
        /* ignore */
      }
    });
  });

  (async () => {
    try {
      const cfg = await api("/api/config");
      if (cfg && cfg.mcp_url) mcpUrl = cfg.mcp_url;
    } catch {
      /* defaults */
    }
    if (!token()) {
      showAuth();
      return;
    }
    try {
      await refreshMe();
    } catch {
      clearSession();
      showAuth();
    }
  })();
})();
