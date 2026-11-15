"""
Fennsill Factory — SEPARATE from Fennsill.exe.

Window flow: select device → Check → Flash (wipe TRMNL + install Fennsill + lock IDs).
"""

from __future__ import annotations

import queue
import secrets
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "firmware"))

from device_crypto import DEFAULT_MASTER_PATH  # noqa: E402
from panel_ports import assert_factory_flash_port, list_factory_flash_targets  # noqa: E402
from provision import provision  # noqa: E402


def ensure_master_key() -> Path:
    path = DEFAULT_MASTER_PATH
    if not path.is_file():
        path.write_bytes(secrets.token_bytes(32))
    return path


class FactoryApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Fennsill Factory")
        self.geometry("640x520")
        self.minsize(560, 440)
        self.configure(bg="#1c1c1c")

        self._targets: list[dict] = []
        self._checked: dict | None = None
        self._busy = False
        self._q: queue.Queue = queue.Queue()

        ensure_master_key()
        self._build_style()
        self._build_ui()
        self.refresh_ports()
        self.after(200, self._drain)

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"), background="#1c1c1c", foreground="#f2f2f2")
        style.configure("Body.TLabel", font=("Segoe UI", 10), background="#1c1c1c", foreground="#c8c8c8")
        style.configure("Ok.TLabel", font=("Segoe UI", 10, "bold"), background="#1c1c1c", foreground="#7dcea0")
        style.configure("Bad.TLabel", font=("Segoe UI", 10, "bold"), background="#1c1c1c", foreground="#e74c3c")
        style.configure("Action.TButton", font=("Segoe UI", 11, "bold"), padding=10)
        style.configure("Flash.TButton", font=("Segoe UI", 14, "bold"), padding=14)

    def _build_ui(self):
        pad = {"padx": 18, "pady": 6}

        ttk.Label(self, text="Fennsill Factory", style="Title.TLabel").pack(anchor="w", padx=18, pady=(18, 2))
        ttk.Label(
            self,
            text="Separate from Fennsill.exe — wipe TRMNL, install Fennsill, lock serial + key.",
            style="Body.TLabel",
            wraplength=580,
        ).pack(anchor="w", padx=18, pady=(0, 12))

        # Step 1 — select
        step1 = ttk.LabelFrame(self, text=" 1. Select device ", padding=12)
        step1.pack(fill="x", padx=18, pady=6)
        row = ttk.Frame(step1)
        row.pack(fill="x")
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(row, textvariable=self.port_var, width=56, state="readonly")
        self.port_box.pack(side="left", fill="x", expand=True)
        self.port_box.bind("<<ComboboxSelected>>", self._on_port_changed)
        ttk.Button(row, text="Refresh", command=self.refresh_ports).pack(side="left", padx=(8, 0))

        # Step 2 — check
        step2 = ttk.LabelFrame(self, text=" 2. Check ", padding=12)
        step2.pack(fill="x", padx=18, pady=6)
        self.check_btn = ttk.Button(step2, text="Check selected device", style="Action.TButton", command=self.start_check)
        self.check_btn.pack(anchor="w")
        self.check_label = ttk.Label(step2, text="Not checked yet.", style="Body.TLabel", wraplength=560)
        self.check_label.pack(anchor="w", pady=(8, 0))

        # Step 3 — flash
        step3 = ttk.LabelFrame(self, text=" 3. Flash ", padding=12)
        step3.pack(fill="x", padx=18, pady=6)
        self.flash_btn = ttk.Button(
            step3,
            text="Flash Fennsill (erase TRMNL + install)",
            style="Flash.TButton",
            command=self.start_flash,
            state="disabled",
        )
        self.flash_btn.pack(fill="x")
        ttk.Label(
            step3,
            text="Enabled only after Check passes. Erases chip, uploads Fennsill, locks serial + key.",
            style="Body.TLabel",
            wraplength=560,
        ).pack(anchor="w", pady=(8, 0))

        self.log = tk.Text(self, height=10, wrap="word", bg="#111", fg="#ddd", insertbackground="#fff", relief="flat")
        self.log.pack(fill="both", expand=True, padx=18, pady=(8, 18))

    def _write(self, text: str):
        self.log.insert("end", text + "\n")
        self.log.see("end")

    def _on_port_changed(self, _event=None):
        self._checked = None
        self.flash_btn.configure(state="disabled")
        self.check_label.configure(text="Selection changed — run Check again.", style="Body.TLabel")

    def refresh_ports(self):
        if self._busy:
            return
        self._checked = None
        self.flash_btn.configure(state="disabled")
        self._targets = list_factory_flash_targets()
        labels = []
        for p in self._targets:
            kind = p.get("kind", "?")
            label = f"{p['port']}  |  {kind}  |  {p.get('description', '')}"
            labels.append(label)
        self.port_box["values"] = labels
        if labels:
            self.port_box.current(0)
            self.check_label.configure(
                text=f"Found {len(labels)} candidate(s). Select one, then Check.",
                style="Body.TLabel",
            )
            self._write(f"Listed {len(labels)} e-ink / XIAO candidate(s).")
        else:
            self.port_var.set("")
            self.check_label.configure(
                text="No panel found. Plug in the XIAO e-ink panel (not a random COM adapter).",
                style="Bad.TLabel",
            )
            self._write("No flash targets.")

    def _selected_port(self) -> str | None:
        raw = self.port_var.get().strip()
        if not raw:
            return None
        return raw.split()[0]

    def _selected_target(self) -> dict | None:
        port = self._selected_port()
        if not port:
            return None
        for row in self._targets:
            if row.get("port") == port:
                return row
        return None

    def start_check(self):
        if self._busy:
            return
        port = self._selected_port()
        if not port:
            messagebox.showerror("Fennsill Factory", "Select a device first.")
            return
        self._busy = True
        self.check_btn.configure(state="disabled")
        self.flash_btn.configure(state="disabled")
        self.check_label.configure(text=f"Checking {port}…", style="Body.TLabel")
        self._write(f"CHECK {port}")

        def work():
            try:
                target = assert_factory_flash_port(port)
                self._q.put(("check_ok", target))
            except Exception as exc:
                self._q.put(("check_err", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def start_flash(self):
        if self._busy:
            return
        if not self._checked:
            messagebox.showerror("Fennsill Factory", "Run Check first.")
            return
        port = self._checked.get("port")
        if port != self._selected_port():
            messagebox.showerror("Fennsill Factory", "Selection changed — run Check again.")
            self.flash_btn.configure(state="disabled")
            return
        if not messagebox.askokcancel(
            "Flash panel?",
            f"Port: {port}\n"
            f"Kind: {self._checked.get('kind')}\n\n"
            "This will ERASE the chip (wipe TRMNL), install Fennsill, and lock serial + key.\n"
            "Continue?",
        ):
            return

        ensure_master_key()
        self._busy = True
        self.check_btn.configure(state="disabled")
        self.flash_btn.configure(state="disabled", text="Flashing…")
        self._write(f"FLASH {port} (erase + Fennsill)")

        def work():
            try:
                result = provision(port, flash=True, box_serial=None)
                self._q.put(("flash_ok", result))
            except Exception as exc:
                self._q.put(("flash_err", str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def _drain(self):
        try:
            while True:
                kind, payload = self._q.get_nowait()
                self._busy = False
                self.check_btn.configure(state="normal")
                self.flash_btn.configure(text="Flash Fennsill (erase TRMNL + install)")

                if kind == "check_ok":
                    self._checked = payload
                    kind_name = payload.get("kind")
                    reason = payload.get("reason", "")
                    detail = (
                        f"OK — {payload.get('port')} is a Fennsill e-ink / XIAO panel.\n"
                        f"{kind_name}: {reason}"
                    )
                    if payload.get("id"):
                        detail += f"\nid={payload.get('id')}"
                    if payload.get("serial"):
                        detail += f"  serial={payload.get('serial')}"
                    if payload.get("fw_version"):
                        detail += f"  fw={payload.get('fw_version')}"
                    self.check_label.configure(text=detail, style="Ok.TLabel")
                    self.flash_btn.configure(state="normal")
                    self._write(f"CHECK OK [{kind_name}] {reason}")

                elif kind == "check_err":
                    self._checked = None
                    self.flash_btn.configure(state="disabled")
                    self.check_label.configure(text=f"Failed — {payload}", style="Bad.TLabel")
                    self._write(f"CHECK FAILED: {payload}")
                    messagebox.showerror("Check failed", payload)

                elif kind == "flash_ok":
                    self._checked = None
                    self.flash_btn.configure(state="disabled")
                    self.check_label.configure(
                        text=f"Flashed — serial {payload['serial']}  id {payload['device_id']}",
                        style="Ok.TLabel",
                    )
                    self._write("FLASH OK")
                    self._write(f"  serial:    {payload['serial']}")
                    self._write(f"  device_id: {payload['device_id']}")
                    self._write(f"  key_fp:    {payload['key_fingerprint']}")
                    messagebox.showinfo(
                        "Flashed",
                        f"Serial: {payload['serial']}\nDevice ID: {payload['device_id']}\n\n"
                        "This serial never changes across PCs.",
                    )
                    self.refresh_ports()

                elif kind == "flash_err":
                    self.flash_btn.configure(state="normal" if self._checked else "disabled")
                    self._write(f"FLASH FAILED: {payload}")
                    messagebox.showerror("Flash failed", payload)

        except queue.Empty:
            pass
        self.after(200, self._drain)


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ("--flash", "--go"):
        # Headless still available; GUI is the normal path.
        ensure_master_key()
        ports = list_factory_flash_targets()
        if len(ports) != 1:
            print(f"Need exactly one panel. Found {len(ports)}.", file=sys.stderr)
            raise SystemExit(2)
        assert_factory_flash_port(ports[0]["port"])
        result = provision(ports[0]["port"], flash=True)
        print(f"OK serial={result['serial']} device_id={result['device_id']}")
        return
    app = FactoryApp()
    app.mainloop()


if __name__ == "__main__":
    main()
