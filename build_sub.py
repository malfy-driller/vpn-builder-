import requests
import base64
import re
from urllib.parse import urlparse
from collections import defaultdict

# =========================
# SOURCES (Игорёк)
# =========================

SOURCES = [
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-checked.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-all.txt",
    "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
]

# =========================
# SETTINGS
# =========================

FULL_LIMIT = 150
BEST_LIMIT = 80

PREFERRED_DOMAINS = [
    "ads.x5.ru",
    "max.ru",
    "disk.yandex.ru",
    "vk.com",
    "rutube.ru",
]

# =========================
# UTILS
# =========================

def fetch(url):
    print(f"[+] Fetch {url}")
    return requests.get(url, timeout=15).text

def extract_configs(text):
    return [line.strip() for line in text.splitlines() if "://" in line]

def get_host(cfg):
    try:
        return urlparse(cfg).hostname
    except:
        return None

def get_sni(cfg):
    match = re.search(r"sni=([^&]+)", cfg)
    if match:
        return match.group(1)
    return ""

# =========================
# LOAD ALL
# =========================

all_configs = []

for src in SOURCES:
    data = fetch(src)
    cfgs = extract_configs(data)
    print(f"  -> {len(cfgs)} configs")
    all_configs.extend(cfgs)

print(f"\n[=] TOTAL RAW: {len(all_configs)}")

# =========================
# DEDUP HOST
# =========================

dedup = {}
for cfg in all_configs:
    host = get_host(cfg)
    if not host:
        continue
    if host not in dedup:
        dedup[host] = cfg

configs = list(dedup.values())
print(f"[=] AFTER DEDUP: {len(configs)}")

# =========================
# PRIORITY SCORE
# =========================

def score(cfg):
    sni = get_sni(cfg)
    for d in PREFERRED_DOMAINS:
        if d in sni:
            return 1
    return 0

configs.sort(key=lambda x: score(x), reverse=True)

# =========================
# OUTPUT
# =========================

full = configs[:FULL_LIMIT]
best = configs[:BEST_LIMIT]

open("full.txt", "w", encoding="utf-8").write("\n".join(full))
open("best.txt", "w", encoding="utf-8").write("\n".join(best))

print("\n[✓] DONE")
print(f"FULL: {len(full)}")
print(f"BEST: {len(best)}")