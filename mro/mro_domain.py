"""Havacılık MRO domain sabitleri — ATA bölüm haritası, regex desenleri, doküman tipleri."""
import re
from typing import Optional

# ── ATA 100 Bölüm Haritası (iSpec 2200) ──────────────────────────────────────

ATA_CHAPTERS: dict[str, str] = {
    "00": "Genel",
    "01": "Bakım Politikası",
    "04": "Hava Değerliliği Sınırlamaları",
    "05": "Zaman Limitleri / Bakım Kontrolleri",
    "06": "Boyutlar ve Alanlar",
    "07": "Kaldırma ve Destekleme",
    "08": "Seviye ve Tartma",
    "09": "Çekme ve Taksileme",
    "10": "Park ve Bağlama",
    "11": "Plakartlar ve İşaretler",
    "12": "Servis — Rutin Bakım",
    "18": "Titreşim ve Gürültü Analizi",
    "20": "Standart Uygulamalar — Gövde",
    "21": "Klima Sistemi",
    "22": "Otomatik Uçuş",
    "23": "Haberleşme",
    "24": "Elektrik Gücü",
    "25": "Ekipman / Mobilya",
    "26": "Yangın Koruması",
    "27": "Uçuş Kumandaları",
    "28": "Yakıt",
    "29": "Hidrolik Güç",
    "30": "Buz ve Yağmur Koruması",
    "31": "Gösterge Sistemleri",
    "32": "İniş Takımı",
    "33": "Işıklar",
    "34": "Navigasyon",
    "35": "Oksijen",
    "36": "Pnömatik",
    "37": "Vakum",
    "38": "Su / Atık Su",
    "45": "Merkezi Bakım Sistemi",
    "46": "Bilgi Sistemleri",
    "49": "Yardımcı Güç Ünitesi (APU)",
    "51": "Standart Uygulamalar — Yapı",
    "52": "Kapılar",
    "53": "Gövde",
    "54": "Nasel / Pylon",
    "55": "Stabilizatörler",
    "56": "Pencereler",
    "57": "Kanatlar",
    "71": "Güç Ünitesi",
    "72": "Motor — Turbin / Turboprop",
    "73": "Motor Yakıt ve Kontrolü",
    "74": "Ateşleme",
    "75": "Motor Havası",
    "76": "Motor Kontrolleri",
    "77": "Motor İndikasyonu",
    "78": "Egzoz",
    "79": "Yağ",
    "80": "Çalıştırma",
    "81": "Türbin Sistemi",
    "82": "Su Enjeksiyonu",
    "83": "Aksesuarlar — Tahrik Kutusu",
    "85": "Yakıt Hücresi",
    "91": "Çizelgeler",
    "92": "Elektrik Kablo Bağlantısı",
}

# ── Doküman Tipleri ───────────────────────────────────────────────────────────

DOC_TYPES = {
    "CMM": "Component Maintenance Manual",
    "SRM": "Structural Repair Manual",
    "IPC": "Illustrated Parts Catalog",
    "AMM": "Aircraft Maintenance Manual",
    "SB":  "Service Bulletin",
    "AD":  "Airworthiness Directive",
    "TSM": "Troubleshooting Manual",
    "WDM": "Wiring Diagram Manual",
    "FIM": "Fault Isolation Manual",
    "MEL": "Minimum Equipment List",
}

DOC_TYPE_KEYWORDS: dict[str, list[str]] = {
    "CMM": ["COMPONENT MAINTENANCE MANUAL", "CMM", "OVERHAUL MANUAL", "SHOP MANUAL"],
    "SRM": ["STRUCTURAL REPAIR MANUAL", "SRM", "DAMAGE LIMITS", "REPAIR SCHEME"],
    "IPC": ["ILLUSTRATED PARTS CATALOG", "IPC", "ILLUSTRATED PARTS LIST", "IPL"],
    "AMM": ["AIRCRAFT MAINTENANCE MANUAL", "AMM", "MAINTENANCE MANUAL"],
    "SB":  ["SERVICE BULLETIN", "SERVICE LETTER", "ALL OPERATORS LETTER"],
    "AD":  ["AIRWORTHINESS DIRECTIVE", "EMERGENCY AD", "EASA AD"],
    "TSM": ["TROUBLESHOOTING MANUAL", "TSM", "FAULT ISOLATION"],
    "WDM": ["WIRING DIAGRAM MANUAL", "WDM", "WIRING MANUAL"],
}

# ── Regex Desenleri ───────────────────────────────────────────────────────────

# ATA bölüm numaraları: 32-10, 32-10-01, 72-00-00
ATA_SECTION_RE = re.compile(
    r'\b(\d{2})-(\d{2})(?:-(\d{2}))?\b'
)

# ATA başlık deseni (bölüm numarası + başlık metni)
ATA_HEADING_RE = re.compile(
    r'^\s*(\d{2}-\d{2}(?:-\d{2})?)\s+[A-ZÇĞİÖŞÜa-zçğıöşü]',
    re.MULTILINE,
)

# Parça numarası desenleri
PART_NUMBER_PATTERNS = [
    re.compile(r'\bPN[:\s]+([A-Z0-9][\w-]{3,20})\b', re.IGNORECASE),
    re.compile(r'\bP/N[:\s]+([A-Z0-9][\w-]{3,20})\b', re.IGNORECASE),
    re.compile(r'\bPart\s+(?:No|Number|#)[.:\s]+([A-Z0-9][\w-]{3,20})\b', re.IGNORECASE),
    re.compile(r'\b(\d{2}[A-Z]\d{4,6}-\d{1,4})\b'),           # Boeing: 65C26851-1
    re.compile(r'\b([A-Z]{1,4}\d{4,7}-\d{1,5})\b'),            # Genel: ABCD1234-56
    re.compile(r'\b(\d{4,8}-\d{1,5})\b'),                       # Numerik: 123456-789
]

# Service Bulletin referansları
SB_RE = re.compile(
    r'\bSB\s+(\d{3}-\d{2}-\d{3,5})\b', re.IGNORECASE
)

# Airworthiness Directive referansları
AD_RE = re.compile(
    r'\bAD\s+(\d{4}-\d{2}-\d{2,4})\b', re.IGNORECASE
)

# Revizyon bilgisi
REVISION_RE = re.compile(
    r'\b(?:Rev(?:ision)?|REV)[.\s]*(\d+|[A-Z])\b', re.IGNORECASE
)

# Effectivity (uçak seri numarası aralıkları)
EFFECTIVITY_RE = re.compile(
    r'\b(?:Effectivity|EFFECTIVITY|Eff)[:\s]*(.+?)(?:\n|$)',
    re.IGNORECASE,
)

# Prosedür sınır anahtar kelimeleri
PROCEDURE_BOUNDARY_KEYWORDS = [
    "TASK", "SUBTASK", "WARNING", "CAUTION", "NOTE",
    "REMOVAL", "INSTALLATION", "INSPECTION", "REPAIR",
    "DISASSEMBLY", "ASSEMBLY", "CLEANING", "CHECK",
    "TEST", "ADJUSTMENT", "SERVICING", "STORAGE",
    "GÖREV", "ALT GÖREV", "UYARI", "DİKKAT", "NOT",
    "SÖKME", "TAKMA", "MUAYENİ", "ONARIM",
]

# WARNING/CAUTION blok başlangıcı
WARNING_CAUTION_RE = re.compile(
    r'^\s*(WARNING|CAUTION|UYARI|DİKKAT)\s*[:\n]',
    re.MULTILINE | re.IGNORECASE,
)


# ── Yardımcı Fonksiyonlar ────────────────────────────────────────────────────

def get_ata_chapter_name(chapter_code: str) -> str:
    """ATA bölüm kodundan Türkçe adını döndür."""
    code = chapter_code.strip().split("-")[0]
    return ATA_CHAPTERS.get(code, f"Bilinmeyen Bölüm ({code})")


def detect_doc_type(text: str) -> Optional[str]:
    """İlk sayfa metninden doküman tipini tespit et."""
    upper = text[:3000].upper()
    for doc_type, keywords in DOC_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in upper:
                return doc_type
    return None


def extract_ata_sections(text: str) -> list[dict]:
    """Metinden ATA bölüm referanslarını çıkar."""
    results = []
    for m in ATA_SECTION_RE.finditer(text):
        chapter, section, subject = m.group(1), m.group(2), m.group(3)
        entry = {
            "full": m.group(0),
            "chapter": chapter,
            "section": f"{chapter}-{section}",
            "subject": f"{chapter}-{section}-{subject}" if subject else None,
            "chapter_name": get_ata_chapter_name(chapter),
            "position": m.start(),
        }
        results.append(entry)
    return results


def extract_part_numbers(text: str) -> list[str]:
    """Metinden parça numaralarını çıkar (tekrarsız)."""
    found: set[str] = set()
    for pattern in PART_NUMBER_PATTERNS:
        for m in pattern.finditer(text):
            pn = m.group(1) if pattern.groups else m.group(0)
            if len(pn) >= 4:
                found.add(pn.strip())
    return sorted(found)


def extract_sb_references(text: str) -> list[str]:
    """Metinden Service Bulletin referanslarını çıkar."""
    return [m.group(1) for m in SB_RE.finditer(text)]


def extract_ad_references(text: str) -> list[str]:
    """Metinden Airworthiness Directive referanslarını çıkar."""
    return [m.group(1) for m in AD_RE.finditer(text)]


def extract_revision(text: str) -> Optional[str]:
    """Metinden revizyon bilgisini çıkar."""
    m = REVISION_RE.search(text[:2000])
    return m.group(1) if m else None


def extract_effectivity(text: str) -> Optional[str]:
    """Metinden effectivity bilgisini çıkar."""
    m = EFFECTIVITY_RE.search(text[:5000])
    return m.group(1).strip() if m else None
