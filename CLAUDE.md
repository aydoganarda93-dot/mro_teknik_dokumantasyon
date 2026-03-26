# MRO Teknik Dokümantasyon Aracısı

Havacılık MRO (Bakım, Onarım, Revizyon) PDF'lerini ayrıştırıp RAG ile akıllı arama yapan masaüstü + API uygulaması.

---

## Teknoloji Yığını

| Katman | Teknoloji |
|---|---|
| PDF İşleme | PyMuPDF 1.24+ (tablo, çok sütun, header/footer) |
| Embedding | sentence-transformers/all-MiniLM-L6-v2 (lokal, 384-dim) |
| Vektör DB | ChromaDB (persistent, D:\mro_docs\chroma_db) |
| LLM | Anthropic Claude (claude-sonnet-4-6) |
| API Server | FastAPI + uvicorn (port 8100) |
| GUI | customtkinter 5.x (dark mode) |
| Otomasyon | n8n webhook entegrasyonu |
| Config | python-dotenv + mro_config.json |

---

## Dizin Yapısı

```
D:\mro_teknik_dokumantasyon\          # Proje kodu
├── main.py                           # Bağımsız GUI başlatıcı
├── mro_config.py                     # Yapılandırma (.env > JSON > defaults)
├── .env                              # API anahtarları
├── requirements.txt                  # Bağımlılıklar
├── baslat_server.bat                 # Ingestion server başlatıcı
├── baslat_gui.bat                    # GUI başlatıcı
├── mro/
│   ├── mro_domain.py                 # ATA 100 haritası, regex desenleri, sabitler
│   ├── pdf_processor.py              # PDF ayrıştırma (PyMuPDF)
│   ├── chunker.py                    # ATA-farkında akıllı parçalama
│   ├── metadata_extractor.py         # Parça no, ATA bölüm, SB/AD çıkarma
│   ├── embedder.py                   # Embedding üretimi (lokal / Voyage)
│   ├── vector_store.py               # ChromaDB işlemleri
│   ├── rag_engine.py                 # RAG pipeline (arama + reranking + üretim)
│   ├── ingestion_server.py           # FastAPI server (port 8100)
│   └── n8n_mro_client.py             # n8n webhook istemcisi
├── ui/
│   └── mro_panel.py                  # MRO dokümantasyon GUI paneli
└── n8n_workflows/
    ├── mro_ingest_workflow.json       # Tekli PDF işleme workflow'u
    └── mro_batch_workflow.json        # Toplu işleme workflow'u

D:\mro_docs\                          # Veri klasörü
├── inbox\                            # PDF'leri buraya bırak
├── processed\                        # İşlenen dokümanlar
├── failed\                           # Hatalı dokümanlar
├── chroma_db\                        # ChromaDB veritabanı
├── cache\                            # Çıkarılmış metin önbelleği
└── ingestion_log.json                # İşleme geçmişi
```

---

## Çalıştırma

```bash
# 1. .env dosyası oluştur
copy .env.example .env
# ANTHROPIC_API_KEY değerini ekle

# 2. Bağımlılıkları kur
pip install -r requirements.txt

# 3. Ingestion server başlat (ayrı terminal)
baslat_server.bat

# 4a. Bağımsız GUI
baslat_gui.bat

# 4b. multi_agent_ai entegrasyonu (otomatik)
# app_window.py topbar'da "📋 MRO Docs" butonu çıkar
```

---

## API Endpoints (port 8100)

| Metot | Yol | Açıklama |
|---|---|---|
| POST | /process | Tek PDF işle ve indeksle |
| POST | /search | RAG sorgusu çalıştır |
| POST | /batch | inbox'taki tüm PDF'leri işle |
| GET | /stats | Vektör deposu istatistikleri |
| GET | /documents | Doküman listesi |
| DELETE | /documents/{doc_id} | Doküman sil |
| GET | /health | Sağlık kontrolü |
| GET | /log | İşleme geçmişi |

---

## Entegrasyon

multi_agent_ai projesine entegrasyon `app_window.py` üzerinden yapılır:
- `D:\mro_teknik_dokumantasyon` sys.path'e eklenir
- MroDocsPanel import edilir
- Topbar'da "📋 MRO Docs" butonu eklenir
- MRO modülü bulunamazsa buton gösterilmez (graceful fallback)

---

## Geliştirme Notları

- Thread safety: Tüm widget güncellemeleri `self.after(0, lambda: ...)` ile
- ChromaDB collection'ları: doküman tipi başına ayrı (mro_cmm, mro_srm, vb.)
- Chunking: ATA bölüm başlıkları > prosedür sınırları > recursive split
- WARNING/CAUTION blokları ve tablolar asla bölünmez
- Embedding modeli ilk kullanımda indirilir (~90MB)
