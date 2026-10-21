#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
METAR Sentinel - monitor de anomalii pentru piete meteo (Polymarket)
Ruleaza pe GitHub Actions (gratuit). NU tranzactioneaza - doar vegheaza.
Nu are acces la bani: citeste doar API-ul public METAR si trimite Telegram.
"""
import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone

# ── CONFIG ─────────────────────────────────────────────
STATIONS = {
    "LTFM": "Istanbul",
    "LEMD": "Madrid",
    "FACT": "Cape Town",
    "EFHK": "Helsinki",
    "EGLL": "Londra",
}
API = "https://aviationweather.gov/api/data/metar?format=json&hours=6&ids="
T_SILENCE_MIN = 75      # alerta daca nu e METAR nou de 75 min
T_JUMP_C = 2.0          # alerta la salt >= 2C intre citiri consecutive
MAX_API_FAILS = 4       # alerta dupa 4 esecuri consecutive ale API-ului
HEARTBEAT_HOUR_UTC = 4  # "sunt viu" zilnic la 04:0x UTC = 07:0x ora ta
STATE_FILE = "state.json"

TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_state(s):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False)

def send(text):
    if not TOKEN or not CHAT_ID:
        print("TELEGRAM_TOKEN / CHAT_ID lipsesc. Mesajul era:\n" + text)
        return
    url = "https://api.telegram.org/bot%s/sendMessage" % TOKEN
    data = urllib.parse.urlencode({"chat_id": CHAT_ID, "text": text}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    try:
        urllib.request.urlopen(req, timeout=20).read()
        print("Trimis: " + text[:80])
    except Exception as e:
        print("Eroare Telegram: %s" % e)

def parse_time(s):
    try:
        s2 = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s2)
    except Exception:
        return None

def fetch(icao):
    req = urllib.request.Request(API + icao, headers={"User-Agent": "METAR-Sentinel/1.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8"))

def main():
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    st = load_state()
    alerts = []

    # 1) Sanatatea API-ului
    try:
        fetch("LEMD")
        st["api_fails"] = 0
    except Exception:
        st["api_fails"] = st.get("api_fails", 0) + 1
        if st["api_fails"] >= MAX_API_FAILS and st.get("api_alert") != today:
            alerts.append("🌐 API-ul METAR e indisponibil de %d rulari consecutive. Sursele de rezolutie pot fi afectate - verifica paginile wrh!" % st["api_fails"])
            st["api_alert"] = today
        save_state(st)
        return

    # 2) Verificare statii
    for icao, name in STATIONS.items():
        try:
            obs = fetch(icao)
        except Exception:
            continue
        obs = [o for o in obs if o.get("reportTime") and o.get("temp") is not None]
        obs.sort(key=lambda o: o["reportTime"])
        if len(obs) < 2:
            continue
        last, prev = obs[-1], obs[-2]
        t_last = parse_time(last["reportTime"])
        if not t_last:
            continue

        # a) STATIE MUTA
        age = (now - t_last).total_seconds() / 60.0
        if age > T_SILENCE_MIN and st.get("sil_" + icao) != today:
            alerts.append("🔇 STATIE MUTA: %s (%s) - ultimul METAR acum %d min. Verifica pagina de rezolutie wrh: daca e goala, piata e in pericol de 'cel mai jos bin'!" % (name, icao, int(age)))
            st["sil_" + icao] = today

        # b) SALT BRUSC
        d = abs(last["temp"] - prev["temp"])
        key = "%s:%s>%s" % (icao, prev["reportTime"], last["reportTime"])
        if d >= T_JUMP_C and st.get("jump") != key:
            alerts.append("🌡 SALT BRUSC: %s (%s) %g→%g°C intre %s si %s UTC. Verifica daca bin-urile pietei s-au miscat!" % (name, icao, prev["temp"], last["temp"], prev["reportTime"][11:16], last["reportTime"][11:16]))
            st["jump"] = key

    # 3) Heartbeat zilnic
    if now.hour == HEARTBEAT_HOUR_UTC and st.get("hb") != today:
        alerts.append("✅ Sentinel activ - %s. Toate cele %d statii sunt sub observatie." % (today, len(STATIONS)))
        st["hb"] = today

    save_state(st)
    if alerts:
        send("\n\n".join(alerts))
    else:
        print("OK, fara anomalii la %s UTC" % now.strftime("%H:%M"))

if __name__ == "__main__":
    main()
