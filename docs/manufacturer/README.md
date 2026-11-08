# Официальные материалы XIMEA

Файлы получены 08.11.2026 с официального сайта XIMEA; документация на
исходном английском языке. Правообладатель — XIMEA. Исходные адреса, время,
размеры и SHA-256 указаны в `manifest.json`.

- [Страница точной модели MQ042MG-CM-S7](MQ042MG-CM-S7.html).
- [Полный technical manual xiQ-S7, PDF, v260902](xiq-s7-technical-manual.pdf),
  101 страница. Модель/сенсор: стр. 25; скорость: стр. 33; Binder pinout:
  стр. 48; электрические требования GPI: стр. 50.
- [xiAPI Python manual](xiAPI-Python-manual.html).
- [xiAPI parameter manual](xiAPI-manual.html).
- [Trigger and synchronization signals](trigger-and-synchronization.html).
- [Windows Software Package](windows-software-package.html),
  [Linux Software Package](linux-software-package.html).
- [Python/Windows installation](python-windows-installation.html),
  [Python/Linux installation](python-linux-installation.html).
- [Страница текущих загрузок](software-downloads.html).
- [Лицензия официального SDK](XIMEA-SDK-LICENSE.txt), сохранена без изменений
  из скачанного Linux SDK 4.34.00.

PDF полностью доступен без сети. В HTML сохранён текст исходной страницы,
удалены исполняемые скрипты/формы, ссылки сделаны абсолютными. Внешние картинки,
стили и переходы могут требовать интернет. Для электрического подключения
используйте именно PDF S7 и рисунок разъёма, не только общее описание семейства.

Обновить reference snapshots:

```bash
.venv/bin/python scripts/fetch_manufacturer_docs.py
```

Загрузчик использует urllib, а при отказе сервера — установленный curl.
Обновление внешних материалов и manifest желательно делать отдельным
коммитом. Код/библиотеки производителя не патчатся. Native SDK EXE/TGZ не
входят в Git; установщик и Python wheels поставляются отдельным архивом.
Условия производителя не заменяются лицензией приложения.
