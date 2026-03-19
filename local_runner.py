"""
local_runner.py — Локальный запуск build_sub.py с расширенной статистикой.
Запуск: python local_runner.py
"""

import sys
import os
import time

# Добавляем папку проекта в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from build_sub import (
    fetch_source_group, SOURCES,
    dedup_by_host_port, dedup_by_backend,
    extract_label, extract_country, extract_params,
    build_full, build_best, build_mixed,
    save_file, OUTPUT_DIR,
)
from collections import defaultdict


def print_section(title: str):
    print(f"\n{'='*55}")
    print(f"  {title}")
    print(f"{'='*55}")


def detailed_stats(name: str, configs: list):
    """Подробная статистика по списку конфигов."""
    print(f"\n--- {name} ({len(configs)} конфигов) ---")

    country_counts = defaultdict(int)
    sni_counts = defaultdict(int)
    backend_counts = defaultdict(int)
    proto_counts = defaultdict(int)

    for cfg in configs:
        label = extract_label(cfg)
        country_counts[extract_country(label)] += 1

        params = extract_params(cfg)
        sni = params.get("sni", "—")
        sni_counts[sni] += 1

        pbk = params.get("pbk", "")
        sid = params.get("sid", "")
        if pbk:
            backend_counts[f"{pbk[:20]}|{sid[:8]}"] += 1

        for proto in ["vless", "trojan", "vmess", "ss", "hysteria2"]:
            if cfg.lower().startswith(proto + "://"):
                proto_counts[proto] += 1
                break

    print("  Протоколы:")
    for proto, cnt in sorted(proto_counts.items(), key=lambda x: -x[1]):
        print(f"    {cnt:4d}x  {proto}")

    print("  Страны (топ 10):")
    for country, cnt in sorted(country_counts.items(), key=lambda x: -x[1])[:10]:
        bar = "█" * min(cnt, 20)
        print(f"    {cnt:4d}x  {bar}  {country}")

    print("  SNI домены (топ 8):")
    for sni, cnt in sorted(sni_counts.items(), key=lambda x: -x[1])[:8]:
        print(f"    {cnt:4d}x  {sni}")

    dup_backends = {k: v for k, v in backend_counts.items() if v > 1}
    if dup_backends:
        print(f"  Повторяющихся бэкендов: {len(dup_backends)}")
        for bk, cnt in sorted(dup_backends.items(), key=lambda x: -x[1])[:5]:
            print(f"    {cnt:4d}x  pbk:{bk}")


def main():
    print_section("VPN Builder — Local Runner")
    start = time.monotonic()

    # --- Загрузка ---
    print_section("Загрузка источников")

    white_raw  = fetch_source_group("white",  SOURCES["white"])
    mobile_raw = fetch_source_group("mobile", SOURCES["mobile"])
    black_raw  = fetch_source_group("black",  SOURCES["black"])

    total_raw = len(white_raw) + len(mobile_raw) + len(black_raw)

    print(f"\nИтого загружено (с дублями):")
    print(f"  white:  {len(white_raw)}")
    print(f"  mobile: {len(mobile_raw)}")
    print(f"  black:  {len(black_raw)}")
    print(f"  TOTAL:  {total_raw}")

    # --- Дедуп статистика ---
    print_section("Дедупликация")

    all_raw = white_raw + mobile_raw + black_raw
    after_hostport = dedup_by_host_port(all_raw)
    after_backend  = dedup_by_backend(after_hostport, max_per_backend=2)

    print(f"  До дедупа (host:port):  {len(all_raw)}")
    print(f"  После дедупа host:port: {len(after_hostport)}")
    print(f"  После дедупа backend:   {len(after_backend)}")
    print(f"  Убрано всего:           {len(all_raw) - len(after_backend)}")

    # --- Сборка файлов ---
    print_section("Сборка выходных файлов")

    full_configs  = build_full(white_raw, mobile_raw, black_raw)
    best_configs  = build_best(white_raw, mobile_raw, black_raw)
    mixed_configs = build_mixed(white_raw, mobile_raw, black_raw)

    # --- Сохранение ---
    print_section("Сохранение")

    save_file(
        os.path.join(OUTPUT_DIR, "full.txt"),
        full_configs,
        title="VPN Full Pool",
        description="All sources, dedup by host:port only",
    )
    save_file(
        os.path.join(OUTPUT_DIR, "best.txt"),
        best_configs,
        title="VPN Best",
        description="Top configs by score, max 3/country, max 2/backend",
    )
    save_file(
        os.path.join(OUTPUT_DIR, "mixed.txt"),
        mixed_configs,
        title="VPN Mixed",
        description="50% white, 30% mobile, 20% black",
    )

    # --- Детальная статистика ---
    print_section("Детальная статистика")
    detailed_stats("full.txt",  full_configs)
    detailed_stats("best.txt",  best_configs)
    detailed_stats("mixed.txt", mixed_configs)

    elapsed = time.monotonic() - start
    print_section("Готово")
    print(f"  Время выполнения: {elapsed:.1f}с")
    print(f"  Файлы сохранены в: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
