# Пакеты для Windows

`wheels/windows/` содержит шесть Python-пакетов для Windows x64 / Python 3.11:
PySide6-Essentials, shiboken6, NumPy, pyqtgraph, Pillow, colorama. Камерного
пакета pypylon здесь нет. Модуль XIMEA берётся из официального SDK.

`sdk/XIMEA_Windows_SP_Stable.exe`
содержит оригинальный установщик XIMEA Windows SDK 4.34.00, скачанный с
[официального сайта](https://www.ximea.com/attachment/XIMEA_Windows_SP_Stable.exe).
Он не изменён и не запускался в этой среде. Оператор устанавливает его
отдельно с драйвером USB3 и xiAPI Python v3. Условия — производителя.

Воспроизвести загрузку Python wheels:

```bash
python -m pip download --only-binary=:all: --platform win_amd64 --python-version 311 --dest vendor/wheels/windows -r requirements.txt
```

Создать архив с SDK и wheels после коммита:

```bash
.venv/bin/python scripts/make_release.py --with-wheels --with-sdk
```

Распакуйте его поверх архива программы. В Windows после создания venv:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --find-links vendor\wheels\windows -r requirements.txt
.\.venv\Scripts\python.exe scripts\configure_ximea_sdk.py --sdk-root "C:\XIMEA" --check
```

Вторая команда выполняется после отдельной установки SDK. Бинарные пакеты,
извлечённый SDK и пользовательские пути находятся вне Git; архив содержит
manifest с размерами и SHA-256. Официальные Python/native-компоненты SDK
должны оставаться из одного пакета и не патчатся приложением.
