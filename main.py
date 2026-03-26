"""MRO Teknik Dokümantasyon Aracısı — Ana giriş noktası.

Bağımsız masaüstü uygulaması olarak veya multi_agent_ai'ye entegre çalışır.
"""
import sys
import os
from pathlib import Path

# SSL fix for PyInstaller
import ssl
ssl._create_default_https_context = ssl._create_unverified_context

# Proje kökünü sys.path'e ekle
ROOT = Path(__file__).parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# .env yükle
from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import customtkinter as ctk
from ui.mro_panel import MroDocsPanel

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class MROApp(ctk.CTk):
    """Bağımsız MRO Dokümantasyon uygulaması."""

    def __init__(self):
        super().__init__()
        self.title("📋 MRO Teknik Dokümantasyon Aracısı")
        self.geometry("400x200")
        self.minsize(400, 200)
        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        frame = ctk.CTkFrame(self, fg_color="#0D1117")
        frame.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="📋 MRO Teknik Dokümantasyon",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(20, 8))

        ctk.CTkLabel(
            frame,
            text="Havacılık MRO PDF Analizi ve RAG Arama",
            font=ctk.CTkFont(size=12),
            text_color="#8B949E",
        ).grid(row=1, column=0, padx=20, pady=(0, 16))

        ctk.CTkButton(
            frame,
            text="📋 Dokümantasyon Panelini Aç",
            height=42,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1E88E5",
            hover_color="#1565C0",
            command=self._open_panel,
        ).grid(row=2, column=0, padx=20, pady=(0, 20), sticky="ew")

    def _open_panel(self):
        MroDocsPanel(self)


if __name__ == "__main__":
    app = MROApp()
    app.mainloop()
