# Документация и библиотеки производителя

Материалы в этой папке получены с официальных сайтов Basler и репозитория
[basler/pypylon](https://github.com/basler/pypylon). Авторские права на
документацию принадлежат Basler AG; собственные инструкции проекта находятся
на уровень выше. Внешние документы сохранены на исходном английском языке.

- [Спецификация acA2500-14gm](acA2500-14gm.html): сенсор, размеры, питание,
  электрические требования входа, распиновка, иллюстрации.
- [Triggered acquisition](triggered-image-acquisition.html).
- [Electronic shutter types](electronic-shutter-types.html).
- [Exposure time](exposure-time.html), [Gain](gain.html).
- [GigE network configuration](network-configuration.html).
- [Установка pypylon](pypylon-installation.html).
- `programmers_guide/`: все 17 глав официального руководства программиста
  pypylon, от установки до захвата, настройки, потоков и обработки ошибок.
- `pypylon-LICENSE.txt`: лицензия upstream.
- `manifest.json`: исходные URL, время загрузки, SHA-256, размер файла и
  upstream-коммит руководства.

HTML содержит основную статью с исходными ссылками; доступные иллюстрации
встроены для чтения без сети. Ссылки на другие статьи и некоторые внешние
ресурсы требуют интернета. Таблицы общих функций могут включать другие
модели: ищите именно `acA2500-14gm`.

Старые PDF EMVA1288 и Windows Installation Guide остаются по ссылкам
`optional_legacy_pdf_links` в manifest.json. Домен www2.baslerweb.com оказался
недоступен для загрузки из этой среды, поэтому PDF не включены. Спецификация
и современное руководство программиста включены как HTML/Markdown. При
доступности старого домена их можно дополнительно скачать командой:

```bash
.venv/bin/python scripts/fetch_manufacturer_docs.py --with-legacy-pdfs
```

Обычное обновление локальных копий без старых PDF:

```bash
.venv/bin/python scripts/fetch_manufacturer_docs.py
```

Код downloader использует только стандартную библиотеку; менять snapshot
желательно отдельным коммитом, сохраняя manifest. Условия лицензирования
внешних материалов не заменяются лицензией исходной исторической программы.

Библиотека производителя **pypylon 4.2.0** включена в `requirements.txt`.
Windows wheel и остальные Python-зависимости подготовлены в
`vendor/wheels/windows/` вне Git. Wheel включает pylon runtime, но не
полноценный Windows-установщик GigE-драйверов/Viewer. Его скачайте с
[официальной страницы pylon](https://www.baslerweb.com/en/software/downloads/software-downloads/).
Автоматический запуск сторонних установщиков программой не выполняется.
