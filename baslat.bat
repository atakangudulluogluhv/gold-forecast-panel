@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title Altin/TL Tahmin Paneli

echo.
echo  ===========================================
echo    Altin/TL Tahmin Paneli
echo  ===========================================
echo.

REM --- 1) Python bul -------------------------------------------------------
set "PY="
where py >nul 2>&1 && set "PY=py"
if not defined PY (where python >nul 2>&1 && set "PY=python")
if not defined PY (
  echo  [HATA] Python bulunamadi.
  echo         https://www.python.org/downloads/ adresinden kurun ve
  echo         kurulumda "Add Python to PATH" secenegini isaretleyin.
  echo.
  pause
  exit /b 1
)

REM --- 2) Sanal ortam ------------------------------------------------------
set "FIRSTRUN="
if not exist ".venv\Scripts\python.exe" (
  echo  [1/3] Sanal ortam olusturuluyor. Bu yalnizca ilk calistirmada olur.
  %PY% -m venv .venv
  if errorlevel 1 (
    echo  [HATA] Sanal ortam olusturulamadi.
    pause
    exit /b 1
  )
  set "FIRSTRUN=1"
) else (
  echo  [1/3] Sanal ortam hazir.
)

set "VPY=.venv\Scripts\python.exe"

REM --- 3) Bagimliliklar ----------------------------------------------------
"%VPY%" -c "import streamlit, anthropic, sklearn, plotly, feedparser" >nul 2>&1
if errorlevel 1 set "FIRSTRUN=1"

if defined FIRSTRUN (
  echo  [2/3] Paketler kuruluyor. Birkac dakika surebilir, lutfen bekleyin.
  "%VPY%" -m pip install --upgrade pip --quiet
  "%VPY%" -m pip install -r requirements.txt --quiet
  if errorlevel 1 (
    echo  [HATA] Paketler kurulamadi. Internet baglantinizi kontrol edin.
    pause
    exit /b 1
  )
) else (
  echo  [2/3] Paketler hazir.
)

REM --- 4) API anahtari -----------------------------------------------------
if not exist ".env" copy ".env.example" ".env" >nul

findstr /C:"sk-ant-..." ".env" >nul 2>&1
if not errorlevel 1 (
  echo.
  echo  [!] API anahtari tanimli degil.
  echo      Yapay zeka yorumu ve haber puanlamasi calismaz;
  echo      panelin geri kalani sorunsuz calisir.
  echo      Eklemek icin:  notepad .env
  echo.
)

REM --- 5) Streamlit ilk calistirma sorusunu sustur --------------------------
REM Streamlit ilk acilista e-posta soruyor ve cift tiklamada burada takiliyor.
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
  >"%USERPROFILE%\.streamlit\credentials.toml" echo [general]
  >>"%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

REM --- 6) Baslat -----------------------------------------------------------
echo  [3/3] Panel baslatiliyor, tarayici otomatik acilacak.
echo        Kapatmak icin bu pencerede Ctrl+C yapin.
echo.
"%VPY%" -m streamlit run app.py

echo.
echo  Panel kapandi.
pause
