# backend.py - RENDER UYUMLU, SADECE DASHBOARD + QUERY + APILER (RATE LİMİT YOK)
import os
import re
import json
import time
import logging
import secrets
import ipaddress
import threading
from datetime import datetime, timedelta
from collections import deque, OrderedDict

import requests
from flask import Flask, request, jsonify, render_template, session, redirect, url_for, flash, g
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# ---------- Basic config ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', template_folder='templates')

# SECRET_KEY
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

# Session cookie hardening
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('SESSION_COOKIE_SECURE', 'true').lower() in ('1','true','yes')
)

# CORS
CORS(app)

# ---------- Security headers ----------
@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    return response

# ---------- API endpoints list (TÜMÜ AÇIK) ----------
API_ENDPOINTS = {
    # TC Ad-Soyad sorguları
    "tc_adsoyad": "http://188.132.130.66:5000/adsoyad?adi={adi}&soyadi={soyadi}",
    "tc_adsoyad_il": "http://188.132.130.66:5000/adsoyad?adi={adi}&soyadi={soyadi}&il={il}",

    # Sülale sorguları
    "sulale_tumu": "http://188.132.130.66:5000/sulale?tc={tc}",
    "sulale_kendisi": "http://188.132.130.66:5000/sulale/kendisi?tc={tc}",
    "sulale_cocuk": "http://188.132.130.66:5000/sulale/cocuk?tc={tc}",
    "sulale_es": "http://188.132.130.66:5000/sulale/es?tc={tc}",
    "sulale_anne": "http://188.132.130.66:5000/sulale/anne?tc={tc}",
    "sulale_baba": "http://188.132.130.66:5000/sulale/baba?tc={tc}",
    "sulale_kardes": "http://188.132.130.66:5000/sulale/kardes?tc={tc}",
    "sulale_anneanne": "http://188.132.130.66:5000/sulale/anneanne?tc={tc}",
    "sulale_babanne": "http://188.132.130.66:5000/sulale/babanne?tc={tc}",
    "sulale_dede": "http://188.132.130.66:5000/sulale/dede?tc={tc}",
    "sulale_amca_hala": "http://188.132.130.66:5000/sulale/amca-hala?tc={tc}",
    "sulale_dayi_teyze": "http://188.132.130.66:5000/sulale/dayi-teyze?tc={tc}",
    "sulale_kuzen": "http://188.132.130.66:5000/sulale/kuzen?tc={tc}",

    # Adres ve iş yeri
    "adres_sorgu": "http://188.132.130.66:5000/adres?tc={tc}",
    "isyeri_sorgu": "http://188.132.130.66:5000/isyeri?tc={tc}",

    # GSM-TC dönüşüm
    "gsmden_tc": "http://188.132.130.66:5000/gsm-tc?gsm={gsm}",
    "tcden_gsm": "http://188.132.130.66:5000/tc-gsm?tc={tc}",

    # Plaka sorguları
    "plaka_sorgu": "https://plakaya.onrender.com/f3api/plaka?plaka={plaka}",
    "plaka_ad": "https://plakaya.onrender.com/f3api/adsoyadplaka?ad={ad}",
    "plaka_adsoyad": "https://plakaya.onrender.com/f3api/adsoyadplaka?ad={ad}&soyad={soyad}",
    "plaka_soyad": "https://plakaya.onrender.com/f3api/adsoyadplaka?soyad={soyad}",

    # Seri no sorguları
    "serino_tc": "https://serinodatan.onrender.com/serino?tc={tc}",
    "serino_ad": "https://serinodatan.onrender.com/serino?ad={ad}",
    "serino_adsoyad": "https://serinodatan.onrender.com/serino?ad={ad}&soyad={soyad}",
    "serino_soyad": "https://serinodatan.onrender.com/serino?soyad={soyad}",
    "serino_no": "https://serinodatan.onrender.com/serino?seri_no={seri_no}",
    "serino_ad_il": "https://serinodatan.onrender.com/serino?ad={ad}&il={il}&limit={limit}",

    # Vergi sorguları
    "vergi_isim": "https://vergidatamf.onrender.com/f3system/api/vergi?isim={isim}",
    "vergi_ilce": "https://vergidatamf.onrender.com/f3system/api/vergi?ilce={ilce}&vergi_dairesi={vergi_dairesi}",
    "vergi_no": "https://vergidatamf.onrender.com/f3system/api/vergi?vergi_no={vergi_no}",

    # Öğretmen sorguları
    "ogretmen_ilce": "https://ogretmendatamf.onrender.com/f3system/api/ogretmen?ilce={ilce}&limit={limit}",
    "ogretmen_il_brans": "https://ogretmendatamf.onrender.com/f3system/api/ogretmen?il={il}&brans={brans}",
    "ogretmen_isim": "https://ogretmendatamf.onrender.com/f3system/api/ogretmen?isim={isim}",

    # Eczane sorguları
    "eczane_il": "https://eczanedatamf.onrender.com/f3system/api/eczane?il={il}",
    "eczane_ad": "https://eczanedatamf.onrender.com/f3system/api/eczane?ad={ad}",
    "eczane_il_ad": "https://eczanedatamf.onrender.com/f3system/api/eczane?il={il}&ad={ad}",

    # Papara sorguları
    "papara_no": "https://paparadatamf.onrender.com/f3system/api/papara?paparano={paparano}",
    "papara_ad": "https://paparadatamf.onrender.com/f3system/api/papara?ad={ad}",
    "papara_adsoyad": "https://paparadatamf.onrender.com/f3system/api/papara?ad={ad}&soyad={soyad}",
}

# ---------- Query names for display ----------
QUERY_NAMES = {
    "tc_adsoyad": "TC Ad-Soyad Sorgu",
    "tc_adsoyad_il": "TC Ad-Soyad (İl ile)",
    "sulale_tumu": "Sülale - Tümü",
    "sulale_kendisi": "Sülale - Kendisi",
    "sulale_cocuk": "Sülale - Çocuk",
    "sulale_es": "Sülale - Eş",
    "sulale_anne": "Sülale - Anne",
    "sulale_baba": "Sülale - Baba",
    "sulale_kardes": "Sülale - Kardeş",
    "sulale_anneanne": "Sülale - Anneanne",
    "sulale_babanne": "Sülale - Babaanne",
    "sulale_dede": "Sülale - Dede",
    "sulale_amca_hala": "Sülale - Amca/Hala",
    "sulale_dayi_teyze": "Sülale - Dayı/Teyze",
    "sulale_kuzen": "Sülale - Kuzen",
    "adres_sorgu": "Adres Sorgu",
    "isyeri_sorgu": "İş Yeri Sorgu",
    "gsmden_tc": "GSM'den TC Sorgu",
    "tcden_gsm": "TC'den GSM Sorgu",
    "plaka_sorgu": "Plaka Sorgu",
    "plaka_ad": "Plaka - Ad Sorgu",
    "plaka_adsoyad": "Plaka - Ad Soyad Sorgu",
    "plaka_soyad": "Plaka - Soyad Sorgu",
    "serino_tc": "Seri No - TC Sorgu",
    "serino_ad": "Seri No - Ad Sorgu",
    "serino_adsoyad": "Seri No - Ad Soyad Sorgu",
    "serino_soyad": "Seri No - Soyad Sorgu",
    "serino_no": "Seri No - Numara Sorgu",
    "serino_ad_il": "Seri No - Ad İl Sorgu",
    "vergi_isim": "Vergi - İsim Sorgu",
    "vergi_ilce": "Vergi - İlçe Sorgu",
    "vergi_no": "Vergi - Vergi No Sorgu",
    "ogretmen_ilce": "Öğretmen - İlçe Sorgu",
    "ogretmen_il_brans": "Öğretmen - İl Branş Sorgu",
    "ogretmen_isim": "Öğretmen - İsim Sorgu",
    "eczane_il": "Eczane - İl Sorgu",
    "eczane_ad": "Eczane - Ad Sorgu",
    "eczane_il_ad": "Eczane - İl Ad Sorgu",
    "papara_no": "Papara - No Sorgu",
    "papara_ad": "Papara - Ad Sorgu",
    "papara_adsoyad": "Papara - Ad Soyad Sorgu",
}

# ---------- Ana Sayfa (Dashboard) ----------
@app.route('/')
def index():
    return render_template('dashboard.html', query_names=QUERY_NAMES)

# ---------- Query Sayfası ----------
@app.route('/query/<query_key>')
def query_page(query_key):
    if query_key not in API_ENDPOINTS:
        return "Sorgu bulunamadı", 404

    query_name = QUERY_NAMES.get(query_key, query_key)
    return render_template('query.html', query_key=query_key, query_name=query_name)

# ---------- API: Query bilgilerini getir ----------
@app.route('/api/get_query_info/<query_key>')
def get_query_info(query_key):
    if query_key not in API_ENDPOINTS:
        return jsonify({'error': 'Sorgu bulunamadı'}), 404

    url = API_ENDPOINTS[query_key]
    import re
    params = re.findall(r'{([^}]+)}', url)

    return jsonify({
        'query_key': query_key,
        'required_params': params
    })

# ---------- API: Sorgu çalıştır ----------
@app.route('/api/execute_query', methods=['POST'])
def execute_query():
    data = request.get_json()
    query_key = data.get('query_key')
    params = data.get('params', {})

    if query_key not in API_ENDPOINTS:
        return jsonify({'success': False, 'error': 'Geçersiz sorgu tipi'}), 400

    # Parametreleri temizle
    clean_params = {}
    for k, v in params.items():
        if v:
            clean_params[k] = str(v).strip()

    try:
        # API URL'ini oluştur
        url_template = API_ENDPOINTS[query_key]
        url = url_template.format(**clean_params)

        # API isteği yap
        response = requests.get(url, timeout=30)

        # Yanıtı döndür
        return jsonify({
            'success': True,
            'response': response.text
        })

    except requests.exceptions.Timeout:
        return jsonify({'success': False, 'error': 'API zaman aşımı'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'success': False, 'error': 'API bağlantı hatası'}), 502
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ---------- Health Check ----------
@app.route('/health')
def health():
    return jsonify({'status': 'ok', 'time': time.time()})

# ---------- Main ----------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
