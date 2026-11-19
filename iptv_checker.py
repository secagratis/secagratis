import concurrent.futures
import os
import re
import ssl
import threading
import time
import tkinter as tk
import urllib.error
import urllib.parse
import urllib.request
from tkinter import filedialog, messagebox, ttk


class IPTVCheckerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("IPTV M3U / M3U8 Playlist Validator & Cleaner")
        self.root.geometry("920x620")
        self.root.minsize(820, 540)

        self.default_ua = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36"
        )

        self.channels = []
        self.is_running = False
        self.stop_requested = False

        self._build_ui()

    def _build_ui(self):
        main_frame = ttk.Frame(self.root, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- Barra Superiore: Caricamento e Opzioni ---
        top_frame = ttk.LabelFrame(main_frame, text="1. Selezione Playlist & Parametri Controllo", padding="10")
        top_frame.pack(fill=tk.X, pady=(0, 10))

        row1 = ttk.Frame(top_frame)
        row1.pack(fill=tk.X, pady=(0, 8))

        ttk.Label(row1, text="File M3U:").pack(side=tk.LEFT, padx=(0, 5))
        self.file_path_var = tk.StringVar()
        ttk.Entry(row1, textvariable=self.file_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))

        ttk.Button(row1, text="Apri .m3u / .m3u8...", command=self._load_file).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(row1, text="Incolla Lista / URL", command=self._open_paste_dialog).pack(side=tk.LEFT)

        row2 = ttk.Frame(top_frame)
        row2.pack(fill=tk.X)

        ttk.Label(row2, text="Timeout (sec):").pack(side=tk.LEFT, padx=(0, 4))
        self.timeout_var = tk.IntVar(value=8)
        ttk.Spinbox(row2, from_=2, to=30, width=5, textvariable=self.timeout_var).pack(side=tk.LEFT, padx=(0, 15))

        ttk.Label(row2, text="Thread simultanei:").pack(side=tk.LEFT, padx=(0, 4))
        self.workers_var = tk.IntVar(value=10)
        ttk.Spinbox(row2, from_=1, to=30, width=5, textvariable=self.workers_var).pack(side=tk.LEFT, padx=(0, 15))

        self.deep_check_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            row2,
            text="Verifica contenuto manifest (#EXTM3U / segmenti)",
            variable=self.deep_check_var,
        ).pack(side=tk.LEFT, padx=(0, 15))

        self.stop_btn = ttk.Button(row2, text="Ferma", state=tk.DISABLED, command=self._stop_check)
        self.stop_btn.pack(side=tk.RIGHT)

        self.start_btn = ttk.Button(row2, text="Avvia Controllo", command=self._start_check)
        self.start_btn.pack(side=tk.RIGHT, padx=(0, 6))

        # --- Barra Statistiche e Filtri ---
        stats_frame = ttk.Frame(main_frame)
        stats_frame.pack(fill=tk.X, pady=(0, 8))

        self.stats_var = tk.StringVar(value="Totale: 0  |  Online: 0  |  Offline: 0  |  In attesa: 0")
        ttk.Label(stats_frame, textvariable=self.stats_var, font=("Segoe UI", 9, "bold")).pack(side=tk.LEFT)

        filter_box = ttk.Frame(stats_frame)
        filter_box.pack(side=tk.RIGHT)

        ttk.Label(filter_box, text="Mostra:").pack(side=tk.LEFT, padx=(0, 5))
        self.filter_var = tk.StringVar(value="ALL")
        for label, val in [("Tutti", "ALL"), ("Solo Online", "ONLINE"), ("Solo Offline", "OFFLINE")]:
            ttk.Radiobutton(
                filter_box,
                text=label,
                variable=self.filter_var,
                value=val,
                command=self._refresh_tree,
            ).pack(side=tk.LEFT, padx=(0, 8))

        # --- Tabella Risultati (Treeview) ---
        table_frame = ttk.Frame(main_frame)
        table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        columns = ("idx", "status", "name", "latency", "detail", "url")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="extended")

        self.tree.heading("idx", text="#")
        self.tree.heading("status", text="Stato")
        self.tree.heading("name", text="Canale")
        self.tree.heading("latency", text="Latenza")
        self.tree.heading("detail", text="Esito / Codice HTTP")
        self.tree.heading("url", text="URL Flusso")

        self.tree.column("idx", width=45, anchor=tk.CENTER, stretch=False)
        self.tree.column("status", width=90, anchor=tk.CENTER, stretch=False)
        self.tree.column("name", width=190, anchor=tk.W)
        self.tree.column("latency", width=75, anchor=tk.CENTER, stretch=False)
        self.tree.column("detail", width=180, anchor=tk.W)
        self.tree.column("url", width=310, anchor=tk.W)

        self.tree.tag_configure("ONLINE", foreground="#137333")
        self.tree.tag_configure("OFFLINE", foreground="#c5221f")
        self.tree.tag_configure("PENDING", foreground="#5f6368")

        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky=tk.NSEW)
        vsb.grid(row=0, column=1, sticky=tk.NS)
        hsb.grid(row=1, column=0, sticky=tk.EW)

        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        # Menu contestuale su riga
        self.ctx_menu = tk.Menu(self.root, tearoff=0)
        self.ctx_menu.add_command(label="Copia URL flusso", command=self._copy_selected_url)
        self.ctx_menu.add_command(label="Ricontrolla selezionati", command=self._recheck_selected)
        self.ctx_menu.add_command(label="Rimuovi selezionati dalla lista", command=self._remove_selected)
        self.tree.bind("<Button-3>", self._show_context_menu)

        # --- Barra Inferiore: Progresso ed Export ---
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X)

        self.progress = ttk.Progressbar(bottom_frame, mode="determinate")
        self.progress.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 12))

        self.export_online_btn = ttk.Button(
            bottom_frame,
            text="Esporta M3U Pulita (Solo Online)",
            command=lambda: self._export_m3u(only_online=True),
        )
        self.export_online_btn.pack(side=tk.RIGHT)

        self.export_all_btn = ttk.Button(
            bottom_frame,
            text="Esporta Tutto (.m3u)",
            command=lambda: self._export_m3u(only_online=False),
        )
        self.export_all_btn.pack(side=tk.RIGHT, padx=(0, 8))

    def _load_file(self):
        path = filedialog.askopenfilename(
            title="Seleziona playlist IPTV",
            filetypes=[("Playlist M3U / M3U8", "*.m3u *.m3u8"), ("Tutti i file", "*.*")],
        )
        if not path:
            return
        self.file_path_var.set(path)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            self._parse_m3u_content(content)
        except Exception as e:
            messagebox.showerror("Errore lettura file", f"Impossibile aprire il file:\n{e}")

    def _open_paste_dialog(self):
        win = tk.Toplevel(self.root)
        win.title("Incolla contenuto M3U o elenco URL")
        win.geometry("620x400")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="Incolla qui il testo della playlist M3U oppure uno o più URL (uno per riga):").pack(
            anchor=tk.W, padx=10, pady=(10, 5)
        )
        txt = tk.Text(win, wrap=tk.NONE)
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        try:
            clip = self.root.clipboard_get()
            if clip:
                txt.insert("1.0", clip)
        except tk.TclError:
            pass

        def on_confirm():
            raw = txt.get("1.0", tk.END).strip()
            if raw:
                self.file_path_var.set("[Lista incollata]")
                self._parse_m3u_content(raw)
            win.destroy()

        btn_row = ttk.Frame(win)
        btn_row.pack(fill=tk.X, padx=10, pady=(0, 10))
        ttk.Button(btn_row, text="Carica nella tabella", command=on_confirm).pack(side=tk.RIGHT)
        ttk.Button(btn_row, text="Annulla", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 6))

    def _parse_m3u_content(self, content):
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        parsed = []

        current_extinf = None
        current_name = None
        current_ua = ""
        current_ref = ""
        extra_opts = []

        for line in lines:
            if line.startswith("#EXTM3U"):
                continue
            elif line.startswith("#EXTINF:"):
                current_extinf = line
                if "," in line:
                    current_name = line.split(",", 1)[1].strip()
                else:
                    current_name = "Canale senza nome"
            elif line.startswith("#EXTVLCOPT:"):
                opt = line.split(":", 1)[1].strip()
                low = opt.lower()
                if low.startswith("http-user-agent="):
                    current_ua = opt.split("=", 1)[1].strip()
                elif low.startswith("http-referrer="):
                    current_ref = opt.split("=", 1)[1].strip()
                else:
                    extra_opts.append(line)
            elif line.startswith("#EXTGRP:"):
                extra_opts.append(line)
            elif line.startswith("#"):
                continue
            else:
                raw_url = line
                clean_url = raw_url
                ua = current_ua
                ref = current_ref

                # Gestione parametri inline stile Kodi/IPTV: url|User-Agent=...&Referer=...
                if "|" in raw_url:
                    base_part, pipe_part = raw_url.split("|", 1)
                    clean_url = base_part.strip()
                    for kv in pipe_part.split("&"):
                        if "=" in kv:
                            k, v = kv.split("=", 1)
                            kl = k.strip().lower()
                            val = urllib.parse.unquote(v.strip())
                            if kl == "user-agent" and not ua:
                                ua = val
                            elif kl in ("referer", "referrer") and not ref:
                                ref = val

                idx = len(parsed) + 1
                name = current_name or f"Canale {idx}"
                parsed.append(
                    {
                        "idx": idx,
                        "name": name,
                        "extinf": current_extinf or f"#EXTINF:-1,{name}",
                        "url": clean_url,
                        "raw_url": raw_url,
                        "ua": ua,
                        "referer": ref,
                        "extra_opts": list(extra_opts),
                        "status": "PENDING",
                        "latency": "-",
                        "detail": "In attesa",
                    }
                )

                current_extinf = None
                current_name = None
                current_ua = ""
                current_ref = ""
                extra_opts = []

        self.channels = parsed
        self.progress["value"] = 0
        self.progress["maximum"] = max(1, len(self.channels))
        self._refresh_tree()
        self._update_stats()

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        flt = self.filter_var.get()

        for ch in self.channels:
            if flt != "ALL" and ch["status"] != flt:
                continue
            status_label = {
                "ONLINE": "ONLINE",
                "OFFLINE": "OFFLINE",
                "PENDING": "IN ATTESA",
            }.get(ch["status"], ch["status"])

            self.tree.insert(
                "",
                tk.END,
                iid=str(ch["idx"]),
                values=(
                    ch["idx"],
                    status_label,
                    ch["name"],
                    ch["latency"],
                    ch["detail"],
                    ch["url"],
                ),
                tags=(ch["status"],),
            )

    def _update_stats(self):
        total = len(self.channels)
        online = sum(1 for c in self.channels if c["status"] == "ONLINE")
        offline = sum(1 for c in self.channels if c["status"] == "OFFLINE")
        pending = total - online - offline
        self.stats_var.set(
            f"Totale: {total}  |  Online: {online}  |  Offline: {offline}  |  In attesa: {pending}"
        )

    def _check_single_channel(self, ch, timeout, deep_check):
        if self.stop_requested:
            return ch

        url = ch["url"]
        ua = ch["ua"] or self.default_ua
        referer = ch["referer"]

        headers = {
            "User-Agent": ua,
            "Accept": "*/*",
            "Connection": "close",
        }
        if referer:
            headers["Referer"] = referer

        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

        start_t = time.perf_counter()
        try:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                code = resp.getcode()
                content_type = (resp.headers.get("Content-Type") or "").lower()
                chunk = resp.read(2048) if deep_check else resp.read(16)
                elapsed_ms = int((time.perf_counter() - start_t) * 1000)

                if code not in (200, 206):
                    ch["status"] = "OFFLINE"
                    ch["latency"] = f"{elapsed_ms} ms"
                    ch["detail"] = f"HTTP {code}"
                    return ch

                if deep_check:
                    if not chunk:
                        ch["status"] = "OFFLINE"
                        ch["latency"] = f"{elapsed_ms} ms"
                        ch["detail"] = "Risposta vuota (0 byte)"
                        return ch

                    text_sample = chunk.decode("utf-8", errors="ignore").lstrip()
                    is_m3u_url = ".m3u8" in url.lower() or ".m3u" in url.lower() or "mpegurl" in content_type

                    if text_sample.startswith("#EXTM3U"):
                        if "#EXT-X-ENDLIST" in text_sample and "#EXTINF" not in text_sample:
                            ch["status"] = "OFFLINE"
                            ch["latency"] = f"{elapsed_ms} ms"
                            ch["detail"] = "Manifest vuoto / scaduto"
                        else:
                            ch["status"] = "ONLINE"
                            ch["latency"] = f"{elapsed_ms} ms"
                            ch["detail"] = f"HTTP {code} (HLS valido)"
                    elif text_sample.lower().startswith("<!doctype html") or text_sample.lower().startswith("<html"):
                        ch["status"] = "OFFLINE"
                        ch["latency"] = f"{elapsed_ms} ms"
                        ch["detail"] = "Pagina HTML (no stream)"
                    elif is_m3u_url and "#EXT" not in text_sample:
                        ch["status"] = "OFFLINE"
                        ch["latency"] = f"{elapsed_ms} ms"
                        ch["detail"] = "Manifest non valido"
                    else:
                        # Flusso MPEG-TS diretto, MP4 o MPD
                        ch["status"] = "ONLINE"
                        ch["latency"] = f"{elapsed_ms} ms"
                        ch["detail"] = f"HTTP {code} (Flusso attivo)"
                else:
                    ch["status"] = "ONLINE"
                    ch["latency"] = f"{elapsed_ms} ms"
                    ch["detail"] = f"HTTP {code}"

        except urllib.error.HTTPError as e:
            elapsed_ms = int((time.perf_counter() - start_t) * 1000)
            ch["status"] = "OFFLINE"
            ch["latency"] = f"{elapsed_ms} ms"
            ch["detail"] = f"HTTP {e.code} ({e.reason})"
        except urllib.error.URLError as e:
            ch["status"] = "OFFLINE"
            ch["latency"] = "-"
            reason = str(getattr(e, "reason", e))
            if "timed out" in reason.lower():
                ch["detail"] = "Timeout connessione"
            else:
                ch["detail"] = f"Errore rete: {reason[:32]}"
        except socket.timeout:
            ch["status"] = "OFFLINE"
            ch["latency"] = "-"
            ch["detail"] = "Timeout lettura flusso"
        except Exception as e:
            ch["status"] = "OFFLINE"
            ch["latency"] = "-"
            ch["detail"] = f"Errore: {str(e)[:35]}"

        return ch

    def _start_check(self, subset=None):
        if self.is_running:
            return
        targets = subset if subset is not None else self.channels
        if not targets:
            messagebox.showwarning("Nessun canale", "Carica o incolla prima una playlist M3U.")
            return

        for ch in targets:
            ch["status"] = "PENDING"
            ch["latency"] = "-"
            ch["detail"] = "Verifica..."

        self._refresh_tree()
        self._update_stats()

        self.is_running = True
        self.stop_requested = False
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress["value"] = 0
        self.progress["maximum"] = len(targets)

        timeout = max(2, int(self.timeout_var.get()))
        workers = max(1, min(30, int(self.workers_var.get())))
        deep_check = self.deep_check_var.get()

        thread = threading.Thread(
            target=self._worker_pool,
            args=(list(targets), timeout, workers, deep_check),
            daemon=True,
        )
        thread.start()

    def _stop_check(self):
        if self.is_running:
            self.stop_requested = True
            self.stop_btn.config(state=tk.DISABLED)

    def _worker_pool(self, targets, timeout, workers, deep_check):
        completed = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = [
                executor.submit(self._check_single_channel, ch, timeout, deep_check)
                for ch in targets
            ]
            for fut in concurrent.futures.as_completed(futures):
                if self.stop_requested:
                    for f in futures:
                        f.cancel()
                    break
                ch = fut.result()
                completed += 1
                self.root.after(0, self._on_channel_checked, ch, completed)

        self.root.after(0, self._on_all_done)

    def _on_channel_checked(self, ch, completed):
        self.progress["value"] = completed
        self._update_stats()

        iid = str(ch["idx"])
        flt = self.filter_var.get()
        if self.tree.exists(iid):
            if flt != "ALL" and ch["status"] != flt:
                self.tree.delete(iid)
            else:
                self.tree.item(
                    iid,
                    values=(ch["idx"], ch["status"], ch["name"], ch["latency"], ch["detail"], ch["url"]),
                    tags=(ch["status"],),
                )
        elif flt == "ALL" or ch["status"] == flt:
            self._refresh_tree()

    def _on_all_done(self):
        self.is_running = False
        self.stop_requested = False
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self._update_stats()

    def _show_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            if row_id not in self.tree.selection():
                self.tree.selection_set(row_id)
            self.ctx_menu.post(event.x_root, event.y_root)

    def _get_selected_channels(self):
        selected_ids = set(self.tree.selection())
        return [ch for ch in self.channels if str(ch["idx"]) in selected_ids]

    def _copy_selected_url(self):
        sel = self._get_selected_channels()
        if not sel:
            return
        urls = "\n".join(ch["url"] for ch in sel)
        self.root.clipboard_clear()
        self.root.clipboard_append(urls)

    def _recheck_selected(self):
        sel = self._get_selected_channels()
        if sel and not self.is_running:
            self._start_check(subset=sel)

    def _remove_selected(self):
        if self.is_running:
            return
        selected_ids = set(self.tree.selection())
        if not selected_ids:
            return
        self.channels = [ch for ch in self.channels if str(ch["idx"]) not in selected_ids]
        for i, ch in enumerate(self.channels, start=1):
            ch["idx"] = i
        self._refresh_tree()
        self._update_stats()

    def _export_m3u(self, only_online=True):
        if not self.channels:
            messagebox.showwarning("Lista vuota", "Nessun canale da esportare.")
            return

        to_export = [ch for ch in self.channels if (not only_online or ch["status"] == "ONLINE")]
        if not to_export:
            messagebox.showwarning(
                "Nessun canale valido",
                "Non ci sono canali ONLINE da esportare. Esegui prima il controllo o scegli 'Esporta Tutto'.",
            )
            return

        default_name = "playlist_valida.m3u" if only_online else "playlist_esportata.m3u"
        save_path = filedialog.asksaveasfilename(
            title="Salva playlist M3U",
            defaultextension=".m3u",
            initialfile=default_name,
            filetypes=[("Playlist M3U", "*.m3u"), ("Playlist M3U8", "*.m3u8"), ("Tutti i file", "*.*")],
        )
        if not save_path:
            return

        out_lines = ["#EXTM3U"]
        for ch in to_export:
            out_lines.append(ch["extinf"])
            for opt in ch["extra_opts"]:
                out_lines.append(opt)
            if ch["ua"]:
                out_lines.append(f"#EXTVLCOPT:http-user-agent={ch['ua']}")
            if ch["referer"]:
                out_lines.append(f"#EXTVLCOPT:http-referrer={ch['referer']}")
            out_lines.append(ch["url"])

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write("\n".join(out_lines) + "\n")
            messagebox.showinfo(
                "Esportazione completata",
                f"Esportati {len(to_export)} canali in:\n{save_path}",
            )
        except Exception as e:
            messagebox.showerror("Errore salvataggio", f"Impossibile salvare il file:\n{e}")


if __name__ == "__main__":
    root = tk.Tk()
    app = IPTVCheckerApp(root)
    root.mainloop()
