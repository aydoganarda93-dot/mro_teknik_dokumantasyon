"""MRO Teknik Dokümantasyon Paneli — Profesyonel Havacılık Arayüzü."""
import threading
import tkinter as tk
import tkinter.ttk as ttk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

import sys

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from mro.n8n_mro_client import (
    is_ingestion_server_running,
    get_stats,
    get_documents,
    process_pdf,
    search_query,
    delete_document,
    trigger_batch_processing,
    open_docs_folder,
    open_inbox_folder,
)

# ── Renk Paleti ───────────────────────────────────────────────────────────────
_C = {
    "bg":          "#070C14",
    "panel":       "#0C1220",
    "card":        "#101826",
    "border":      "#1A2B3D",
    "header_bg":   "#060A12",
    "btn_primary": "#1A4F8C",
    "btn_p_hover": "#153F72",
    "btn_success": "#1A5C3A",
    "btn_s_hover": "#144B2F",
    "btn_danger":  "#7A1A1A",
    "btn_d_hover": "#621515",
    "btn_neutral": "#1C2D42",
    "btn_n_hover": "#162234",
    "text":        "#C4D3E8",
    "text_dim":    "#546A82",
    "text_hdr":    "#E4EEF8",
    "accent":      "#3278C8",
    "ok":          "#2A9860",
    "err":         "#C03030",
    "warn":        "#B88010",
    "code_bg":     "#060B12",
}


class MroDocsPanel(ctk.CTkToplevel):
    """MRO Teknik Dokümantasyon Sistemi."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("MRO Teknik Dokümantasyon Sistemi")
        self.geometry("1340x880")
        self.minsize(1080, 700)
        self.configure(fg_color=_C["bg"])
        self.grab_set()

        self._processing = False
        self._searching = False
        self._build_ui()
        self._check_server_status()
        self._load_documents()

    # ── UI İnşası ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self._build_header()
        self._build_content()
        self._build_statusbar()

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=_C["header_bg"], corner_radius=0, height=62)
        hdr.grid(row=0, column=0, sticky="ew")
        hdr.grid_columnconfigure(1, weight=1)
        hdr.grid_propagate(False)

        # Üst vurgu çizgisi
        accent_bar = tk.Frame(hdr, bg=_C["accent"], height=3)
        accent_bar.place(x=0, y=0, relwidth=1.0)

        title_frm = ctk.CTkFrame(hdr, fg_color="transparent")
        title_frm.grid(row=0, column=0, padx=18, pady=12, sticky="w")

        ctk.CTkLabel(
            title_frm, text="MRO DOKÜMANTASYON",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color=_C["text_hdr"],
        ).pack(side="left")

        ctk.CTkLabel(
            title_frm, text="   Havacılık Teknik Doküman RAG Sistemi",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=_C["text_dim"],
        ).pack(side="left")

        self._status_lbl = ctk.CTkLabel(
            hdr, text="Sistem durumu kontrol ediliyor...",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=_C["text_dim"],
        )
        self._status_lbl.grid(row=0, column=1, padx=10, sticky="w")

        self._stats_hdr_lbl = ctk.CTkLabel(
            hdr, text="",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=_C["accent"],
        )
        self._stats_hdr_lbl.grid(row=0, column=2, padx=18, sticky="e")

    def _build_content(self):
        content = ctk.CTkFrame(self, fg_color="transparent")
        content.grid(row=1, column=0, sticky="nsew", padx=10, pady=(8, 4))
        content.grid_columnconfigure(0, weight=2)
        content.grid_columnconfigure(1, weight=3)
        content.grid_rowconfigure(0, weight=1)
        self._build_left_panel(content)
        self._build_right_panel(content)

    def _build_statusbar(self):
        bar = ctk.CTkFrame(self, fg_color=_C["header_bg"], corner_radius=0, height=26)
        bar.grid(row=2, column=0, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)
        bar.grid_propagate(False)

        self._statusbar_lbl = ctk.CTkLabel(
            bar, text="Hazır.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=_C["text_dim"], anchor="w",
        )
        self._statusbar_lbl.grid(row=0, column=0, padx=12, pady=4, sticky="w")

        ctk.CTkLabel(
            bar, text="FastAPI  |  ChromaDB  |  Groq LLM",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=_C["text_dim"], anchor="e",
        ).grid(row=0, column=1, padx=12, pady=4, sticky="e")

    # ── Yardımcı: Bölüm başlığı ───────────────────────────────────────────────

    def _sec(self, parent, text: str, row: int, pady=(10, 4)):
        frm = ctk.CTkFrame(parent, fg_color="transparent")
        frm.grid(row=row, column=0, padx=14, pady=pady, sticky="ew")
        tk.Frame(frm, bg=_C["accent"], width=3, height=14).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            frm, text=text,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=_C["text_hdr"],
        ).pack(side="left")

    # ── Sol Panel: Yükleme + Sorgu ────────────────────────────────────────────

    def _build_left_panel(self, parent):
        frame = ctk.CTkFrame(
            parent, corner_radius=5, fg_color=_C["panel"],
            border_width=1, border_color=_C["border"],
        )
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))
        frame.grid_columnconfigure(0, weight=1)

        # ── Doküman Yükleme ───────────────────────────────────────────────
        self._sec(frame, "DOKÜMAN YÜKLEMESİ", row=0, pady=(12, 4))

        self._file_label = ctk.CTkLabel(
            frame, text="Dosya seçilmedi.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=_C["text_dim"], anchor="w",
        )
        self._file_label.grid(row=1, column=0, padx=14, pady=(0, 4), sticky="ew")

        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.grid(row=2, column=0, padx=14, pady=(0, 6), sticky="ew")

        self._upload_btn = ctk.CTkButton(
            btn_row, text="PDF Seç ve Yükle",
            height=33, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_C["btn_primary"], hover_color=_C["btn_p_hover"],
            corner_radius=4, command=self._on_upload,
        )
        self._upload_btn.pack(side="left", fill="x", expand=True, padx=(0, 4))

        self._batch_btn = ctk.CTkButton(
            btn_row, text="Toplu Yükle",
            height=33, font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=_C["btn_success"], hover_color=_C["btn_s_hover"],
            corner_radius=4, command=self._on_batch,
        )
        self._batch_btn.pack(side="left", fill="x", expand=True, padx=(4, 0))

        # ── Son Yükleme Özeti ─────────────────────────────────────────────
        self._sec(frame, "SON YÜKLEMENİN ÖZETİ", row=3, pady=(4, 4))

        self._summary_box = ctk.CTkTextbox(
            frame, height=108, state="disabled",
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=_C["code_bg"], text_color=_C["text"],
            border_color=_C["border"], border_width=1, corner_radius=4,
        )
        self._summary_box.grid(row=4, column=0, padx=14, pady=(0, 8), sticky="ew")
        self._write_box(self._summary_box, "Henüz bir doküman yüklenmedi.")

        # ── Teknik Sorgu ──────────────────────────────────────────────────
        self._sec(frame, "TEKNİK SORGU", row=5, pady=(4, 4))

        ctk.CTkLabel(
            frame,
            text="ATA bölüm no, parça no veya serbest metin ile sorgulayın.",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=_C["text_dim"], anchor="w",
        ).grid(row=6, column=0, padx=14, pady=(0, 4), sticky="w")

        self._query_entry = ctk.CTkEntry(
            frame,
            placeholder_text="örn: ATA 32-10-01 iniş takımı sökme prosedürü",
            height=33,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=_C["card"], border_color=_C["border"],
            text_color=_C["text"], corner_radius=4,
        )
        self._query_entry.grid(row=7, column=0, padx=14, pady=(0, 4), sticky="ew")
        self._query_entry.bind("<Return>", lambda e: self._on_search())

        self._search_btn = ctk.CTkButton(
            frame, text="Sorguyu Çalıştır",
            height=34, font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            fg_color=_C["btn_primary"], hover_color=_C["btn_p_hover"],
            corner_radius=4, command=self._on_search,
        )
        self._search_btn.grid(row=8, column=0, padx=14, pady=(0, 8), sticky="ew")

        # ── Yanıt ─────────────────────────────────────────────────────────
        self._sec(frame, "YANIT", row=9, pady=(4, 4))

        frame.grid_rowconfigure(10, weight=1)
        self._answer_box = ctk.CTkTextbox(
            frame, state="disabled",
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=_C["code_bg"], text_color=_C["text"],
            border_color=_C["border"], border_width=1, corner_radius=4,
            wrap="word",
        )
        self._answer_box.grid(row=10, column=0, padx=14, pady=(0, 6), sticky="nsew")

        # ── Referans Kaynaklar ────────────────────────────────────────────
        self._sec(frame, "REFERANS KAYNAKLAR", row=11, pady=(2, 2))

        self._sources_box = ctk.CTkTextbox(
            frame, height=76, state="disabled",
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=_C["code_bg"], text_color=_C["text_dim"],
            border_color=_C["border"], border_width=1, corner_radius=4,
        )
        self._sources_box.grid(row=12, column=0, padx=14, pady=(0, 8), sticky="ew")

        # ── Inbox Bilgisi ─────────────────────────────────────────────────
        info = ctk.CTkFrame(
            frame, fg_color=_C["card"],
            corner_radius=4, border_width=1, border_color=_C["border"],
        )
        info.grid(row=13, column=0, padx=14, pady=(0, 12), sticky="ew")
        info_row = ctk.CTkFrame(info, fg_color="transparent")
        info_row.pack(padx=10, pady=6, fill="x")

        ctk.CTkLabel(
            info_row, text="Gelen Kutusu: D:\\mro_docs\\inbox",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=_C["text_dim"], anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            info_row, text="Klasörü Aç", width=90, height=22,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color="transparent", border_width=1, border_color=_C["border"],
            hover_color=_C["btn_neutral"], text_color=_C["text_dim"],
            corner_radius=3, command=open_inbox_folder,
        ).pack(side="right")

    # ── Sağ Panel: Doküman Listesi ────────────────────────────────────────────

    def _build_right_panel(self, parent):
        frame = ctk.CTkFrame(
            parent, corner_radius=5, fg_color=_C["panel"],
            border_width=1, border_color=_C["border"],
        )
        frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        # Başlık satırı
        hdr = ctk.CTkFrame(frame, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(12, 6))
        hdr.grid_columnconfigure(0, weight=1)

        title_frm = ctk.CTkFrame(hdr, fg_color="transparent")
        title_frm.grid(row=0, column=0, sticky="w")
        tk.Frame(title_frm, bg=_C["accent"], width=3, height=14).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            title_frm, text="İNDEKSLENMİŞ DOKÜMANLAR",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=_C["text_hdr"],
        ).pack(side="left")

        self._stats_lbl = ctk.CTkLabel(
            hdr, text="",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=_C["text_dim"],
        )
        self._stats_lbl.grid(row=0, column=1, sticky="e")

        ctk.CTkButton(
            hdr, text="Yenile", width=68, height=25,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            fg_color="transparent", border_width=1, border_color=_C["border"],
            hover_color=_C["btn_neutral"], text_color=_C["text_dim"],
            corner_radius=3, command=self._load_documents,
        ).grid(row=0, column=2, padx=(8, 0))

        # Treeview
        style = ttk.Style()
        style.theme_use("default")
        style.configure(
            "MRO.Treeview",
            background=_C["code_bg"], foreground=_C["text"],
            fieldbackground=_C["code_bg"], rowheight=25,
            font=("Segoe UI", 10), borderwidth=0,
        )
        style.configure(
            "MRO.Treeview.Heading",
            background=_C["card"], foreground=_C["text_dim"],
            font=("Segoe UI", 10, "bold"), relief="flat",
        )
        style.map(
            "MRO.Treeview",
            background=[("selected", _C["btn_primary"])],
            foreground=[("selected", "#FFFFFF")],
        )

        tree_frm = tk.Frame(
            frame, bg=_C["code_bg"],
            highlightbackground=_C["border"], highlightthickness=1,
        )
        tree_frm.grid(row=1, column=0, sticky="nsew", padx=14, pady=(0, 6))
        tree_frm.grid_columnconfigure(0, weight=1)
        tree_frm.grid_rowconfigure(0, weight=1)

        self._tree = ttk.Treeview(
            tree_frm,
            columns=("tip", "ata", "chunks", "rev", "dosya"),
            show="headings", style="MRO.Treeview",
        )
        for col, lbl, w, anchor in [
            ("tip",    "TİP",          65,  "center"),
            ("ata",    "ATA",          60,  "center"),
            ("chunks", "BÖLÜM",        68,  "center"),
            ("rev",    "REV",          52,  "center"),
            ("dosya",  "KAYNAK DOSYA", 270, "w"),
        ]:
            self._tree.heading(col, text=lbl)
            self._tree.column(col, width=w, minwidth=w - 10, anchor=anchor)

        vsb = ttk.Scrollbar(tree_frm, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._tree.bind("<Double-1>", self._on_tree_double_click)

        # Doküman Detayı
        self._sec(frame, "DOKÜMAN DETAYI", row=2, pady=(4, 4))

        self._detail = ctk.CTkTextbox(
            frame, height=112, state="disabled",
            font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=_C["code_bg"], text_color=_C["text"],
            border_color=_C["border"], border_width=1, corner_radius=4,
        )
        self._detail.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 6))

        # Butonlar
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 12))

        ctk.CTkButton(
            btn_row, text="Doküman Klasörü", width=138, height=30,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=_C["btn_success"], hover_color=_C["btn_s_hover"],
            corner_radius=4, command=open_docs_folder,
        ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Seçili Dokümanı Sil", width=152, height=30,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=_C["btn_danger"], hover_color=_C["btn_d_hover"],
            corner_radius=4, command=self._on_delete_document,
        ).pack(side="left")

    # ── İş Mantığı ────────────────────────────────────────────────────────────

    def _check_server_status(self):
        def _check():
            ok = is_ingestion_server_running()
            if ok:
                stats = get_stats()
                total = stats.get("total_chunks", 0)
                docs  = stats.get("total_documents", 0)
                self.after(0, lambda: self._status_lbl.configure(
                    text=f"Sistem Aktif  —  {docs} doküman  /  {total} bölüm",
                    text_color=_C["ok"],
                ))
                self.after(0, lambda: self._set_status("Ingestion serveri aktif ve hazır."))
            else:
                self.after(0, lambda: self._status_lbl.configure(
                    text="Sistem Pasif  —  baslat_server.bat ile serveri başlatın",
                    text_color=_C["err"],
                ))
                self.after(0, lambda: self._set_status(
                    "HATA: Ingestion server bağlantısı kurulamadı."
                ))
        threading.Thread(target=_check, daemon=True).start()

    def _load_documents(self):
        def _load():
            try:
                docs = get_documents()
                self.after(0, lambda: self._populate_tree(docs))
            except Exception:
                pass
        threading.Thread(target=_load, daemon=True).start()

    def _populate_tree(self, docs: list):
        self._tree.delete(*self._tree.get_children())
        for doc in docs:
            source = Path(doc.get("source_file", "")).name
            self._tree.insert(
                "", "end",
                values=(
                    doc.get("doc_type",    "—"),
                    doc.get("ata_chapter", "—"),
                    doc.get("chunk_count", 0),
                    doc.get("revision",    "—"),
                    source,
                ),
                tags=(doc.get("doc_id", ""),),
            )
        self._stats_lbl.configure(text=f"{len(docs)} doküman kayıtlı")

    def _on_upload(self):
        if self._processing:
            return
        file_path = filedialog.askopenfilename(
            title="PDF Dosyası Seç",
            filetypes=[("PDF Dosyaları", "*.pdf"), ("Tüm Dosyalar", "*.*")],
        )
        if not file_path:
            return

        self._processing = True
        self._upload_btn.configure(state="disabled", text="İşleniyor...")
        self._file_label.configure(text=f"İşleniyor: {Path(file_path).name}")
        self._write_box(self._summary_box, f"İşleniyor: {Path(file_path).name}\nLütfen bekleyin...")
        self._set_status(f"PDF işleniyor: {Path(file_path).name}")

        def on_result(result):
            self._processing = False
            ata = ", ".join(result.get("ata_chapters", [])) or "—"
            lines = [
                f"Doküman ID    : {result.get('doc_id', '—')}",
                f"Tip           : {result.get('doc_type', '—')}",
                f"Toplam Sayfa  : {result.get('total_pages', '—')}",
                f"Bölüm Sayısı  : {result.get('chunks_count', 0)}",
                f"Revizyon      : {result.get('revision') or '—'}",
                f"Etkilenim     : {result.get('effectivity') or '—'}",
                f"ATA Bölümleri : {ata}",
                f"Parça No      : {result.get('part_numbers_count', 0)} adet tespit edildi",
                f"SB Referansı  : {result.get('sb_count', 0)} adet",
                f"AD Referansı  : {result.get('ad_count', 0)} adet",
                f"Tablo Sayısı  : {result.get('table_count', 0)} adet",
            ]
            self.after(0, lambda: self._upload_btn.configure(
                state="normal", text="PDF Seç ve Yükle",
            ))
            self.after(0, lambda: self._file_label.configure(text="Dosya seçilmedi."))
            self.after(0, lambda: self._write_box(self._summary_box, "\n".join(lines)))
            self.after(0, lambda: self._set_status(
                f"Başarıyla yüklendi: {result.get('doc_id', '')} "
                f"— {result.get('chunks_count', 0)} bölüm indekslendi."
            ))
            self.after(300, self._load_documents)
            self.after(300, self._check_server_status)

        def on_error(err):
            self._processing = False
            self.after(0, lambda: self._upload_btn.configure(
                state="normal", text="PDF Seç ve Yükle",
            ))
            self.after(0, lambda: self._file_label.configure(text="Dosya seçilmedi."))
            self.after(0, lambda: self._write_box(self._summary_box, f"HATA: {err}"))
            self.after(0, lambda: self._set_status(f"Yükleme hatası: {err}"))

        process_pdf(file_path, on_result=on_result, on_error=on_error)

    def _on_batch(self):
        if self._processing:
            return
        self._processing = True
        self._batch_btn.configure(state="disabled", text="İşleniyor...")
        self._set_status("Toplu işleme başlatıldı (inbox klasörü taranıyor)...")

        def on_result(result):
            self._processing = False
            s, f = result.get("success", 0), result.get("failed", 0)
            self.after(0, lambda: self._batch_btn.configure(
                state="normal", text="Toplu Yükle",
            ))
            self.after(0, lambda: self._set_status(
                f"Toplu işleme tamamlandı — {s} başarılı, {f} hatalı."
            ))
            self.after(300, self._load_documents)
            self.after(300, self._check_server_status)

        def on_error(err):
            self._processing = False
            self.after(0, lambda: self._batch_btn.configure(
                state="normal", text="Toplu Yükle",
            ))
            self.after(0, lambda: self._set_status(f"Toplu işleme hatası: {err}"))

        trigger_batch_processing(on_result=on_result, on_error=on_error)

    def _on_search(self):
        if self._searching:
            return
        query = self._query_entry.get().strip()
        if not query:
            return

        self._searching = True
        self._search_btn.configure(state="disabled", text="Sorgu İşleniyor...")
        self._clear_answer()
        self._log_answer(
            f"SORGU: {query}\n"
            f"{'─' * 58}\n\n"
            f"Yanıt hazırlanıyor, lütfen bekleyin...\n"
        )
        self._write_box(self._sources_box, "")
        self._set_status("RAG sorgusu çalıştırılıyor (Groq LLM)...")

        def on_result(result):
            self._searching = False
            answer  = result.get("answer", "Yanıt alınamadı.")
            sources = result.get("sources", [])

            self.after(0, lambda: self._search_btn.configure(
                state="normal", text="Sorguyu Çalıştır",
            ))
            self.after(0, lambda: self._clear_answer())
            self.after(0, lambda: self._log_answer(answer))

            if sources:
                lines = [f"{'─' * 40}", " REFERANS KAYNAKLAR", f"{'─' * 40}"]
                for i, s in enumerate(sources):
                    lines.append(
                        f"[{i+1}]  {s.get('doc_id','—')}  |  "
                        f"ATA: {s.get('ata_ref','—')}  |  "
                        f"Sayfa: {s.get('page','—')}  |  "
                        f"Tip: {s.get('doc_type','—')}"
                    )
                st = "\n".join(lines)
                self.after(0, lambda t=st: self._write_box(self._sources_box, t))

            self.after(0, lambda: self._set_status("Sorgu tamamlandı."))

        def on_error(err):
            self._searching = False
            self.after(0, lambda: self._search_btn.configure(
                state="normal", text="Sorguyu Çalıştır",
            ))
            self.after(0, lambda: self._clear_answer())
            self.after(0, lambda e=err: self._log_answer(
                f"HATA: Sorgu işlenemedi.\n\n{e}\n\n"
                f"Olası nedenler:\n"
                f"  1. Ingestion server çalışmıyor  (baslat_server.bat)\n"
                f"  2. GROQ_API_KEY .env dosyasında tanımlı değil\n"
                f"  3. Ağ bağlantısı yok\n"
                f"  4. Sorgu zaman aşımına uğradı (>120 sn)"
            ))
            self.after(0, lambda e=err: self._set_status(f"Sorgu hatası: {str(e)[:100]}"))

        search_query(query, on_result=on_result, on_error=on_error)

    def _on_delete_document(self):
        sel = self._tree.selection()
        if not sel:
            return
        tags   = self._tree.item(sel[0], "tags")
        doc_id = tags[0] if tags else ""
        if not doc_id:
            return

        def on_result(result):
            deleted = result.get("chunks_deleted", 0)
            self.after(0, lambda: self._set_status(
                f"{doc_id} silindi ({deleted} bölüm kaldırıldı)."
            ))
            self.after(300, self._load_documents)
            self.after(300, self._check_server_status)

        def on_error(err):
            self.after(0, lambda: self._set_status(f"Silme hatası: {err}"))

        delete_document(doc_id, on_result=on_result, on_error=on_error)

    def _on_tree_double_click(self, _event):
        sel = self._tree.selection()
        if not sel:
            return
        vals   = self._tree.item(sel[0], "values")
        tags   = self._tree.item(sel[0], "tags")
        doc_id = tags[0] if tags else ""

        detail = (
            f"Doküman ID    : {doc_id}\n"
            f"Doküman Tipi  : {vals[0]}\n"
            f"ATA Bölümü    : {vals[1]}\n"
            f"Bölüm Sayısı  : {vals[2]}\n"
            f"Revizyon      : {vals[3]}\n"
            f"Kaynak Dosya  : {vals[4]}"
        )
        self._write_box(self._detail, detail)

    # ── Yardımcılar ───────────────────────────────────────────────────────────

    def _write_box(self, box: ctk.CTkTextbox, text: str):
        box.configure(state="normal")
        box.delete("1.0", "end")
        if text:
            box.insert("1.0", text)
        box.configure(state="disabled")

    def _log_answer(self, text: str):
        self._answer_box.configure(state="normal")
        self._answer_box.insert("end", text)
        self._answer_box.see("end")
        self._answer_box.configure(state="disabled")

    def _clear_answer(self):
        self._answer_box.configure(state="normal")
        self._answer_box.delete("1.0", "end")
        self._answer_box.configure(state="disabled")

    def _set_status(self, text: str):
        self._statusbar_lbl.configure(text=text)
