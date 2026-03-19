# VPN Config Builder

Агрегатор VPN-конфигов из upstream источников с умной фильтрацией и scoring.

## Структура проекта

```
vpn-builder/
├── build_sub.py        ← основной скрипт сборки
├── local_runner.py     ← локальный запуск с детальной статистикой
├── requirements.txt
├── outputs/
│   ├── full.txt        ← до 200 конфигов, все источники
│   ├── best.txt        ← до 80 конфигов, лучшие по scoring
│   └── mixed.txt       ← до 120 конфигов, сбалансированный микс
└── .github/workflows/
    └── main.yml        ← автозапуск каждые 2 часа
```

## Источники

**White (белые списки):**
- `WHITE-CIDR-RU-checked.txt` — CIDR только VK/Yandex/CDNVideo/Beeline
- `WHITE-CIDR-RU-all.txt` — полный CIDR
- `WHITE-SNI-RU-all.txt` — SNI-список

**Mobile:**
- `Vless-Reality-White-Lists-Rus-Mobile.txt` — топ-150 для телефона
- `Vless-Reality-White-Lists-Rus-Mobile-2.txt` — следующие 150

**Black (чёрные списки):**
- `BLACK_VLESS_RUS.txt`
- `BLACK_SS+All_RUS.txt`

## Выходные файлы

| Файл | Лимит | Описание |
|------|-------|----------|
| `full.txt` | 200 | Все источники, только дедуп по host:port |
| `best.txt` | 80 | Scoring + макс 3/страну + макс 2/бэкенд |
| `mixed.txt` | 120 | 50% white + 30% mobile + 20% black |

## Scoring (для best.txt)

- **+10** base за каждый конфиг
- **+20** если SNI из приоритетного списка (`ads.x5.ru`, `max.ru`, `vk.com`, `disk.yandex.ru`, `rutube.ru`, `api-maps.yandex.ru`)
- **+5** diversity bonus если страна новая в выборке

## Запуск локально

```bash
pip install -r requirements.txt

# Быстрый запуск
python build_sub.py

# С детальной статистикой
python local_runner.py
```

## Подписки в VPN-клиенте

Добавь raw-ссылку в Hiddify / v2rayN / Streisand:

```
https://raw.githubusercontent.com/ВАШ_РЕПО/main/outputs/best.txt
https://raw.githubusercontent.com/ВАШ_РЕПО/main/outputs/mixed.txt
https://raw.githubusercontent.com/ВАШ_РЕПО/main/outputs/full.txt
```

## Подключение deep-tester (следующий шаг)

`full.txt` или `best.txt` можно использовать как входной файл для локального
deep-tester через Xray — реальная проверка Telegram / YouTube / Instagram.
