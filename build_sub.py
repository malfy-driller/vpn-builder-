"""
build_sub.py — VPN Config Aggregator
Fetches configs from upstream sources, deduplicates, scores, and outputs
full.txt / best.txt / mixed.txt
"""

import os
import re
import socket
import time
from collections import defaultdict
from urllib.parse import urlparse, parse_qs, unquote

import requests

# ============================================================
# SETTINGS
# ============================================================

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")

FULL_LIMIT  = 200
BEST_LIMIT  = 80
MIXED_LIMIT = 120

# Распределение для mixed.txt
MIXED_WHITE_RATIO  = 0.50  # 50% белые
MIXED_MOBILE_RATIO = 0.30  # 30% mobile
MIXED_BLACK_RATIO  = 0.20  # 20% чёрные

# Лимиты для best.txt
BEST_MAX_PER_COUNTRY = 3
BEST_MAX_PER_BACKEND = 2  # дедуп по pbk+sid+sni

# Бонусные SNI домены
PREFERRED_SNI = [
    "ads.x5.ru",
    "max.ru",
    "disk.yandex.ru",
    "vk.com",
    "rutube.ru",
    "api-maps.yandex.ru",
    "eh.vk.com",
    "api-maps.yandex.ru",
    "ipa.market.yandex.ru",
]

PROTOCOLS = ["vless://", "trojan://", "vmess://", "ss://", "hysteria2://"]

# ============================================================
# SOURCES
# ============================================================

SOURCES = {
    "white": [
        "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-checked.txt",
        "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-CIDR-RU-all.txt",
        "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/WHITE-SNI-RU-all.txt",
    ],
    "mobile": [
        "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile.txt",
        "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/Vless-Reality-White-Lists-Rus-Mobile-2.txt",
    ],
    "black": [
        "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_VLESS_RUS.txt",
        "https://raw.githubusercontent.com/igareck/vpn-configs-for-russia/main/BLACK_SS%2BAll_RUS.txt",
    ],
}

# ============================================================
# FETCH
# ============================================================

def fetch_url(url: str) -> str:
    """Скачиваем текст по URL. Возвращаем пустую строку при ошибке."""
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        print(f"  [WARN] Не удалось загрузить {url}: {e}")
        return ""


def extract_configs(text: str) -> list:
    """Извлекаем строки конфигов из текста."""
    configs = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for proto in PROTOCOLS:
            if line.lower().startswith(proto):
                configs.append(line)
                break
    return configs


def fetch_source_group(group_name: str, urls: list) -> list:
    """Загружаем все URL из группы, возвращаем список конфигов."""
    all_configs = []
    for url in urls:
        print(f"  Загружаю [{group_name}]: {url.split('/')[-1]}")
        text = fetch_url(url)
        found = extract_configs(text)
        print(f"    → найдено конфигов: {len(found)}")
        all_configs.extend(found)
    return all_configs

# ============================================================
# PARSE
# ============================================================

def extract_label(config: str) -> str:
    """Достаём label из #fragment части URL."""
    if "#" not in config:
        return ""
    return unquote(config.split("#", 1)[1]).strip()


def extract_host_port(config: str):
    """Парсим host и port из конфига."""
    try:
        parsed = urlparse(config.split("#")[0])
        host = parsed.hostname or ""
        port = parsed.port or 0
        return host, port
    except Exception:
        return "", 0


def extract_params(config: str) -> dict:
    """Парсим query-параметры конфига (sni, pbk, sid, fp и т.д.)."""
    try:
        raw = config.split("#")[0]
        qs = raw.split("?", 1)[1] if "?" in raw else ""
        params = parse_qs(qs)
        return {k: v[0] for k, v in params.items()}
    except Exception:
        return {}


def extract_country(label: str) -> str:
    """Достаём страну из label конфига."""
    if not label:
        return "Unknown"
    if "Anycast" in label:
        return "Anycast"
    # Ищем слово после эмодзи-флага
    match = re.search(
        r'[\U0001F1E0-\U0001F1FF]{2}\s+([A-Za-z ]+?)(?:\s*[\|【\[★]|$)',
        label
    )
    if match:
        return match.group(1).strip()
    return "Unknown"


def make_host_port_key(config: str) -> str:
    """Ключ для дедупликации по host:port."""
    host, port = extract_host_port(config)
    return f"{host}:{port}" if host and port else ""


def make_backend_key(config: str) -> str:
    """
    Ключ для дедупликации по бэкенду.
    Один бэкенд = одинаковые pbk + sid + sni.
    Это отсеивает most-xx.harknmav.fun и прямые IP на одном сервере.
    """
    params = extract_params(config)
    pbk = params.get("pbk", "")
    sid = params.get("sid", "")
    sni = params.get("sni", "")
    if pbk and sni:
        return f"{pbk}|{sid}|{sni}"
    return ""  # пустой ключ = не дедуплицируем по бэкенду

# ============================================================
# DEDUP
# ============================================================

def dedup_by_host_port(configs: list) -> list:
    """
    Дедупликация по host:port.
    Если несколько конфигов на одном host:port — оставляем первый.
    """
    seen = set()
    result = []
    for cfg in configs:
        key = make_host_port_key(cfg)
        if not key:
            result.append(cfg)  # не можем распарсить — оставляем
            continue
        if key not in seen:
            seen.add(key)
            result.append(cfg)
    return result


def dedup_by_backend(configs: list, max_per_backend: int = 2) -> list:
    """
    Дедупликация по бэкенду (pbk+sid+sni).
    Оставляем не более max_per_backend конфигов на один бэкенд.
    """
    backend_counts = defaultdict(int)
    result = []
    for cfg in configs:
        key = make_backend_key(cfg)
        if not key:
            result.append(cfg)
            continue
        if backend_counts[key] < max_per_backend:
            backend_counts[key] += 1
            result.append(cfg)
    return result

# ============================================================
# SCORING
# ============================================================

def compute_score(config: str, selected_countries: set) -> int:
    """
    Считаем score для одного конфига.
    +10 base
    +20 если sni из preferred списка
    +5  если страна новая (diversity bonus)
    """
    score = 10  # base

    params = extract_params(config)
    sni = params.get("sni", "").lower()

    # Бонус за preferred SNI
    for preferred in PREFERRED_SNI:
        if preferred.lower() in sni:
            score += 20
            break

    # Бонус за разнообразие стран
    label = extract_label(config)
    country = extract_country(label)
    if country not in selected_countries and country != "Unknown":
        score += 5

    return score


def score_and_sort(configs: list) -> list:
    """
    Сортируем конфиги по score (убывание).
    Возвращаем список (config, score, country).
    """
    selected_countries = set()
    scored = []

    for cfg in configs:
        score = compute_score(cfg, selected_countries)
        label = extract_label(cfg)
        country = extract_country(label)
        selected_countries.add(country)
        scored.append((cfg, score, country))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored

# ============================================================
# BUILD OUTPUT FILES
# ============================================================

def build_full(white: list, mobile: list, black: list) -> list:
    """
    full.txt — до 200 конфигов, все источники, только дедуп по host:port.
    """
    all_configs = white + mobile + black
    deduped = dedup_by_host_port(all_configs)
    return deduped[:FULL_LIMIT]


def build_best(white: list, mobile: list, black: list) -> list:
    """
    best.txt — до 80 конфигов.
    Scoring + лимит 3 на страну + лимит 2 на бэкенд.
    """
    # Берём все источники, дедупим по host:port и бэкенду
    all_configs = white + mobile + black
    deduped = dedup_by_host_port(all_configs)
    deduped = dedup_by_backend(deduped, max_per_backend=BEST_MAX_PER_BACKEND)

    # Scoring
    scored = score_and_sort(deduped)

    # Применяем лимит по стране
    country_counts = defaultdict(int)
    result = []

    for cfg, score, country in scored:
        if len(result) >= BEST_LIMIT:
            break
        if country_counts[country] >= BEST_MAX_PER_COUNTRY:
            continue
        result.append(cfg)
        country_counts[country] += 1

    return result


def build_mixed(white: list, mobile: list, black: list) -> list:
    """
    mixed.txt — до 120 конфигов, сбалансированный микс.
    50% white, 30% mobile, 20% black.
    """
    white_limit  = int(MIXED_LIMIT * MIXED_WHITE_RATIO)   # 60
    mobile_limit = int(MIXED_LIMIT * MIXED_MOBILE_RATIO)  # 36
    black_limit  = int(MIXED_LIMIT * MIXED_BLACK_RATIO)   # 24

    # Дедуп внутри каждой группы
    w = dedup_by_host_port(white)[:white_limit]
    m = dedup_by_host_port(mobile)[:mobile_limit]
    b = dedup_by_host_port(black)[:black_limit]

    # Финальный дедуп по host:port чтобы убрать пересечения между группами
    combined = dedup_by_host_port(w + m + b)
    return combined[:MIXED_LIMIT]

# ============================================================
# SAVE
# ============================================================

def build_header(title: str, count: int, description: str) -> str:
    """Заголовок файла подписки."""
    from datetime import datetime, timezone, timedelta
    moscow_tz = timezone(timedelta(hours=3))
    now = datetime.now(moscow_tz).strftime("%Y-%m-%d %H:%M")
    return (
        f"# profile-title: {title}\n"
        f"# profile-update-interval: 120\n"
        f"# Date: {now} MSK\n"
        f"# Count: {count}\n"
        f"# {description}\n\n"
    )


def save_file(path: str, configs: list, title: str, description: str):
    """Сохраняем конфиги в файл с заголовком."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = build_header(title, len(configs), description)
    with open(path, "w", encoding="utf-8") as f:
        f.write(header)
        for cfg in configs:
            f.write(cfg + "\n")
    print(f"  Сохранено: {os.path.basename(path)} ({len(configs)} конфигов)")

# ============================================================
# STATS
# ============================================================

def print_stats(label: str, configs: list):
    """Выводим статистику по группе конфигов."""
    country_counts = defaultdict(int)
    sni_counts = defaultdict(int)

    for cfg in configs:
        lbl = extract_label(cfg)
        country_counts[extract_country(lbl)] += 1
        params = extract_params(cfg)
        sni = params.get("sni", "—")
        sni_counts[sni] += 1

    print(f"\n  [{label}] Всего: {len(configs)}")
    print("  Страны:")
    for country, cnt in sorted(country_counts.items(), key=lambda x: -x[1])[:8]:
        print(f"    {cnt:3d}x  {country}")
    print("  Топ SNI:")
    for sni, cnt in sorted(sni_counts.items(), key=lambda x: -x[1])[:5]:
        print(f"    {cnt:3d}x  {sni}")

# ============================================================
# MAIN
# ============================================================

def main():
    print("\n" + "=" * 55)
    print("  VPN Config Builder")
    print("=" * 55 + "\n")

    # --- Загружаем источники ---
    print("📥 Загрузка источников...\n")

    white_raw  = fetch_source_group("white",  SOURCES["white"])
    mobile_raw = fetch_source_group("mobile", SOURCES["mobile"])
    black_raw  = fetch_source_group("black",  SOURCES["black"])

    print(f"\nЗагружено сырых конфигов:")
    print(f"  white:  {len(white_raw)}")
    print(f"  mobile: {len(mobile_raw)}")
    print(f"  black:  {len(black_raw)}")

    # --- Строим выходные файлы ---
    print("\n📦 Сборка файлов...\n")

    full_configs  = build_full(white_raw, mobile_raw, black_raw)
    best_configs  = build_best(white_raw, mobile_raw, black_raw)
    mixed_configs = build_mixed(white_raw, mobile_raw, black_raw)

    # --- Сохраняем ---
    print("\n💾 Сохранение...\n")

    save_file(
        os.path.join(OUTPUT_DIR, "full.txt"),
        full_configs,
        title="VPN Full Pool | White + Mobile + Black",
        description="All sources, dedup by host:port only",
    )
    save_file(
        os.path.join(OUTPUT_DIR, "best.txt"),
        best_configs,
        title="VPN Best | Scored + Filtered",
        description="Top configs by score, max 3/country, max 2/backend",
    )
    save_file(
        os.path.join(OUTPUT_DIR, "mixed.txt"),
        mixed_configs,
        title="VPN Mixed | Balanced White+Mobile+Black",
        description="50% white, 30% mobile, 20% black",
    )

    # --- Статистика ---
    print("\n📊 Статистика:\n")
    print_stats("full",  full_configs)
    print_stats("best",  best_configs)
    print_stats("mixed", mixed_configs)

    print("\n" + "=" * 55)
    print("✅ Готово!")
    print("=" * 55 + "\n")

    # Возвращаем данные для local_runner.py
    return {
        "white_raw":  len(white_raw),
        "mobile_raw": len(mobile_raw),
        "black_raw":  len(black_raw),
        "full":       len(full_configs),
        "best":       len(best_configs),
        "mixed":      len(mixed_configs),
    }


if __name__ == "__main__":
    main()
