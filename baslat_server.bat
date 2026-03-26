@echo off
echo ======================================
echo  MRO Ingestion Server Baslatiliyor...
echo ======================================
cd /d D:\mro_teknik_dokumantasyon
python -m uvicorn mro.ingestion_server:app --host 0.0.0.0 --port 8100 --reload
pause
