# Официальный XIMEA SDK и драйверы

Для этой копии используются **xiAPI Python** и native xiAPI из **одного
официального XIMEA Software Package**, рекомендован проверенный по структуре
LTS 4.34.00. Python-библиотеки GUI отделены в requirements.txt; pypylon в этой
версии не используется. SDK не устанавливается приложением автоматически.

## Windows x64

1. Скачать [пакет XIMEA](https://www.ximea.com/software-downloads) или взять
   неизменённый установщик `vendor/sdk/XIMEA_Windows_SP_Stable.exe` из отдельного
   подготовленного архива. Его контрольная сумма — в manifest архива.
2. Запустить установщик от администратора. Выбрать USB3/xiQ camera drivers,
   xiAPI, **xiAPI Python v3**, xiCamTool, xiCOP. Установщик имеет собственную
   лицензию, сохранённую также в
   [XIMEA-SDK-LICENSE.txt](https://www.ximea.com/attachment/Linux-SP-Stable.tgz).
3. При запросе перезагрузить Windows. Подключить камеру к USB3; убедиться, что
   xiCOP и xiCamTool её видят. После проверки закрыть захват в этих утилитах.
4. Создать venv Python 3.11 x64 и установить requirements.txt, как в README.
5. Зарегистрировать каталог SDK для этой копии:

   ```powershell
   .\.venv\Scripts\python.exe scripts\configure_ximea_sdk.py --sdk-root "C:\XIMEA" --check
   ```

Структура официального Windows-пакета 4.34.00 проверена без исполнения:
`API/Python/v3/ximea/xiapi.py`, `xidefs.py` и `libs/windows/64bit/` с
`xiapi64.dll`/`xiArrOps64.dll`. Нужна вся папка модуля с DLL, а не один xiapi.py.
Код производителя не меняется. `--sdk-root` принимает корень SDK или папку,
содержащую `ximea/xiapi.py`. Путь сохраняется в ignored
`state/ximea-sdk-path.txt`, только для этого проекта.

Автопоиск также использует `XIMEA_SDK_ROOT`, `XI_API_DIR`, `C:\XIMEA` и
`C:\Program Files\XIMEA`; последнее слово остаётся за фактически установленной
структурой. При нескольких Python-модулях не смешивайте стороннюю старую
перепаковку с новыми DLL. Диагностика показывает путь реально загруженного
xiAPI. Python 32 bit нельзя смешивать с native SDK 64 bit.

Установка requirements без сети:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --find-links vendor\wheels\windows -r requirements.txt
```

Это не заменяет драйвер и SDK. Если ошибка WinError 126/193 — проверьте путь,
наличие DLL/компонентов SDK, архитектуру, установщик и перезагрузку; повторная
установка одних пакетов NumPy не устанавливает драйвер камеры.

## Linux

Следуйте [официальной инструкции](https://www.ximea.com/support/wiki/apis/XIMEA_Linux_Software_Package).
Актуальная LTS-ссылка:
[Linux-SP-Stable.tgz](https://www.ximea.com/attachment/Linux-SP-Stable.tgz).
Распакуйте пакет и запустите его штатный install для USB3 в соответствии с
инструкцией производителя; он может запрашивать sudo и настраивает доступ к
устройству. Не используйте опцию PCIe для USB3-камеры. В этой рабочей среде
инсталляция в систему не выполнялась.

Добавьте своего пользователя в группу доступа, созданную установщиком,
затем выйдите из сеанса и войдите снова, переподключите USB-камеру:

```bash
sudo gpasswd -a "$USER" plugdev
```

Зарегистрируйте папку распакованного официального пакета, которая содержит
`api/Python/v3/ximea`. Если он распакован в стандартный локальный каталог
проекта, выполните из корня проекта:

```bash
.venv/bin/python scripts/configure_ximea_sdk.py --sdk-root vendor/sdk/extracted/package --check
.venv/bin/python scripts/diagnose.py
```

У установщика SDK 4.34 каталог `/opt/XIMEA` содержит инструменты, библиотеки
и примеры, но Python-модуль копируется в site-packages найденного системного
интерпретатора. На Arch системный Python 3.14 и Python 3.11 в venv различаются.
Поэтому `--sdk-root /opt/XIMEA` не гарантирует нахождение Python-модуля;
использование неизменённого пакета из распакованного SDK устраняет это различие.
Копировать системный site-packages целиком в venv не требуется.

На проверенном ноутбуке Arch уже есть libusb, libraw1394, libtiff и библиотеки
Qt/xcb; Python-зависимости также установлены. Остались native SDK, правила
udev и членство в plugdev. Arch не входит в опубликованный список проверенных
производителем дистрибутивов; реальный USB-захват здесь ещё нужно проверить.

В официальном Python-модуле 4.34.00 native-библиотека загружается по пути
`/usr/lib/libm3api.so.2`, а xiArrOps.so — относительно Python-пакета. Поэтому
переноса одних Python-файлов в venv недостаточно. Приложение не переписывает
эти пути в SDK. Если module найден, но native library отсутствует, завершите
установку официального SDK и проверьте его зависимости/USB permissions.
Демонстрация не импортирует xiAPI и работает без native SDK.

## Что подготовлено локально

- Общие Python wheels Windows x64 / Python 3.11, без pypylon, в
  `vendor/wheels/windows/`.
- Оригинальный Windows-установщик XIMEA LTS 4.34.00 в `vendor/sdk/`.
- Оригинальный Linux SDK и извлечённые материалы для проверки в `vendor/sdk/`.
  В обычный архив программы они не включаются.
- Русские инструкции, официальный PDF S7 и offline-копии руководств в
  `docs/manufacturer/`, с исходными URL и SHA-256.

Нативная Linux-библиотека была загружена напрямую из распакованного SDK;
`xiGetNumberDevices` вернул XI_OK и 0 устройств. Это проверка загрузки и
перечисления, не тест реальной камеры. В этой Linux-среде Windows-установщик только скачан и
просмотрен как архив, не запускался. 10.11.2026 пользователь сообщил, что
большая часть функций работает на его стенде XIMEA; точный перечень режимов
пока не зафиксирован. Linux с физической камерой требует отдельной проверки.
