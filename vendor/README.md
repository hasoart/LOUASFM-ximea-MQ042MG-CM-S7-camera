# Windows wheels

`wheels/windows/` содержит официальный pypylon и остальные зависимости для
Python 3.11 x64 / Windows. Бинарные пакеты не включены в Git, но входят в
отдельный ZIP, созданный `scripts/make_release.py --with-wheels`.

Воспроизвести загрузку на машине с интернетом:

```bash
python -m pip download --only-binary=:all: --platform win_amd64 --python-version 311 --dest vendor/wheels/windows -r requirements.txt
```

На Windows распакуйте архив wheels поверх архива исходников, создайте venv и:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\vendor\wheels\windows -r requirements.txt
```

Это пакеты с PyPI под их собственными лицензиями. Установщик pylon Software
Suite / сетевых драйверов скачивается отдельно с сайта Basler.
