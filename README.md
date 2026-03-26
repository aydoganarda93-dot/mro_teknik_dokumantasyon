# MRO Teknik Dokümantasyon Sistemi

Havacılık MRO (Bakım, Onarım, Revizyon) PDF dokümanlarını işleyip **RAG (Retrieval Augmented Generation)** ile akıllı teknik arama yapan masaüstü + API uygulaması.

---

## Özellikler

- PDF'den otomatik metin, tablo ve bölüm çıkarma (PyMuPDF)
- ATA 100 bölüm numarası, parça no, SB/AD referansı tespiti
- Lokal embedding üretimi (internet bağlantısı gerekmez)
- ChromaDB ile kalıcı vektör indeksleme
- Groq LLM ile hızlı ve ücretsiz RAG sorgusu
- Kaynak referanslı yanıt (doküman, sayfa, ATA bölümü)
- FastAPI sunucusu üzerinden REST API
- Profesyonel customtkinter masaüstü arayüzü
- n8n webhook entegrasyonu

---

## Teknoloji Yığını

| Katman | Teknoloji |
|---|---|
| PDF İşleme | PyMuPDF 1.24+ |
| Embedding | sentence-transformers/all-MiniLM-L6-v2 (lokal, 384-dim) |
| Vektör DB | ChromaDB (kalıcı) |
| LLM | Groq — llama-3.3-70b-versatile (ücretsiz) |
| API Sunucusu | FastAPI + uvicorn (port 8100) |
| Masaüstü GUI | customtkinter 5.x |
| Otomasyon | n8n webhook |
| Yapılandırma | python-dotenv + mro_config.json |

---

## Kurulum

### 1. Repoyu klonlayın

```bash
git clone https://github.com/aydoganarda93-dot/mro_teknik_dokumantasyon.git
cd mro_teknik_dokumantasyon
```

### 2. Bağımlılıkları kurun

```bash
pip install -r requirements.txt
```

> İlk çalıştırmada embedding modeli (~90 MB) otomatik indirilir.

### 3. Groq API key alın

[console.groq.com](https://console.groq.com) adresinden ücretsiz kayıt olup API key oluşturun.

### 4. `.env` dosyasını oluşturun

```bash
copy .env.example .env
```

`.env` dosyasını açıp `GROQ_API_KEY` satırını doldurun:

```env
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
EMBEDDING_MODE=local
MRO_DOCS_DIR=D:\mro_docs
```

### 5. Uygulamayı başlatın

**Ingestion sunucusunu** ayrı bir terminalde başlatın:

```bash
baslat_server.bat
```

**Masaüstü arayüzünü** başlatın:

```bash
baslat_gui.bat
```

---

## Kullanım

### PDF Yükleme

1. GUI'de **PDF Seç ve Yükle** butonuna tıklayın.
2. PDF işlendikten sonra "Son Yüklemenin Özeti" kutusunda doküman metadata bilgileri gösterilir (tip, sayfa sayısı, ATA bölümleri, parça numaraları vb.).

Toplu yükleme için PDF'leri `D:\mro_docs\inbox` klasörüne bırakın ve **Toplu Yükle** butonuna tıklayın.

### Teknik Sorgu

Sorgu kutusuna ATA bölüm numarası, parça numarası veya serbest metin yazıp **Sorguyu Çalıştır** butonuna tıklayın.

**Örnek sorgular:**

```
ATA 32-10-01 iniş takımı sökme prosedürü nedir?
P/N 5001234-01 parçası hangi ATA bölümüne aittir?
Hydraulic system pressure check CAUTION uyarıları
```

Yanıtın altında kaynak doküman, sayfa numarası ve ATA referansı gösterilir.

---

## API Referansı (port 8100)

| Metot | Yol | Açıklama |
|---|---|---|
| `POST` | `/process` | Tek PDF işle ve indeksle |
| `POST` | `/search` | RAG sorgusu çalıştır |
| `POST` | `/batch` | inbox klasöründeki tüm PDF'leri işle |
| `GET` | `/stats` | Vektör deposu istatistikleri |
| `GET` | `/documents` | İndekslenmiş doküman listesi |
| `DELETE` | `/documents/{doc_id}` | Doküman sil |
| `GET` | `/health` | Sağlık kontrolü |
| `GET` | `/log` | İşleme geçmişi |

**Örnek sorgu:**

```bash
curl -X POST http://localhost:8100/search \
  -H "Content-Type: application/json" \
  -d '{"query": "landing gear retraction sequence", "top_k": 5}'
```

---

## Dizin Yapısı

```
mro_teknik_dokumantasyon/
├── main.py                     # Bağımsız GUI başlatıcı
├── mro_config.py               # Yapılandırma yöneticisi
├── requirements.txt
├── .env.example                # Örnek ortam değişkenleri
├── baslat_server.bat           # Ingestion sunucu başlatıcı
├── baslat_gui.bat              # GUI başlatıcı
├── mro/
│   ├── pdf_processor.py        # PDF ayrıştırma
│   ├── chunker.py              # ATA-farkında akıllı parçalama
│   ├── metadata_extractor.py   # Parça no, ATA, SB/AD çıkarma
│   ├── embedder.py             # Embedding üretimi
│   ├── vector_store.py         # ChromaDB işlemleri
│   ├── rag_engine.py           # RAG pipeline
│   ├── ingestion_server.py     # FastAPI sunucusu
│   ├── mro_domain.py           # ATA haritası, regex desenleri
│   └── n8n_mro_client.py       # n8n webhook istemcisi
├── ui/
│   └── mro_panel.py            # Masaüstü GUI paneli
└── n8n_workflows/
    ├── mro_ingest_workflow.json
    └── mro_batch_workflow.json

D:\mro_docs\                    # Veri klasörü (otomatik oluşturulur)
├── inbox\                      # PDF'leri buraya bırakın
├── processed\                  # İşlenen dokümanlar
├── failed\                     # Hatalı dokümanlar
├── chroma_db\                  # Vektör veritabanı
└── cache\                      # Metin önbelleği
```

---

## Alternatif LLM Sağlayıcıları

`.env` dosyasında `LLM_PROVIDER` değerini değiştirerek farklı sağlayıcılar kullanılabilir:

| Sağlayıcı | Hız | Maliyet | Gereksinim |
|---|---|---|---|
| `groq` | Çok hızlı | Ücretsiz | GROQ_API_KEY |
| `ollama` | Yavaş | Ücretsiz | Lokal Ollama kurulumu |
| `anthropic` | Hızlı | Ücretli | ANTHROPIC_API_KEY |

---

## Lisans

MIT
