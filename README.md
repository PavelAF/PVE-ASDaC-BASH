# #PROF39
**Конфиг стенда для регионального чемпионата 09.02.06-2025 (модуль Б)**
```
b=testing_api sh=PVE-ASDaC-BASH.sh c='https://disk.yandex.ru/d/Sg3Nrjw07kwrVw';curl -sOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/$b/$sh"&&{ chmod +x $sh&&./$sh -c "$c" -z;rm -f $sh;true;}||echo -e "\n\e[1;33mОшибка скачивания: проверьте подключение к Интернету и настройки DNS\ncurl exit code: $?\n\e[m">&2
```
**Пре-конфиг стендов демекзамена 09.02.06-2025, классический**
```
b=main sh=PVE-ASDaC-BASH.sh c='https://disk.yandex.ru/d/HDgvq-iMbduqag';curl -sOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/$b/$sh"&&{ chmod +x $sh&&./$sh -c "$c" -z;rm -f $sh;true;}||echo -e "\n\e[1;33mОшибка скачивания: проверьте подключение к Интернету и настройки DNS\ncurl exit code: $?\n\e[m">&2
```
**Пре-конфиг стендов демекзамена 09.02.06-2025, только ОС Альт**
```
b=main sh=PVE-ASDaC-BASH.sh c='https://disk.yandex.ru/d/259h8afDR9hqyQ';curl -sOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/$b/$sh"&&{ chmod +x $sh&&./$sh -c "$c" -z;rm -f $sh;true;}||echo -e "\n\e[1;33mОшибка скачивания: проверьте подключение к Интернету и настройки DNS\ncurl exit code: $?\n\e[m">&2
```
<br>
Скрипт простого авторазвертывания стендов с виртуальной ИТ-инфраструктурой на базе гипервизора Proxmox VE и Альт Сервер Виртуализация (PVE)

Поддерживаемые версии: Proxmox VE от 7 до 8.2 (latest), Альт Сервер Виртуализация 10.0 и выше (PVE 7.0+)

Скрипт позволяет просто и быстро автоматизировать развертывание стедов для различных мероприятий (Чемпионаты "Профессионалы", демонстрационый экзамен, учебные стенды и пр.), управлять конфигурацией, создавать свои конфигурации авторазвертывания

**Более подробная информация о скрипте на страницах [вики](../../wiki)**

#### Быстрый старт:

1.  Открываем Proxmox, выбираем нужную Node и переходим в раздел
    “Shell”.
<img src="screenshots/2.png"/>
2. Для того, чтобы развернуть базовые стенды, скопируйте строку ниже и вставьте в консоль (<kbd>Ctrl</kbd>+<kbd>Shift</kbd>+<kbd>V</kbd> или ПКМ -> Вставить):

```
sh='PVE-ASDaC-BASH.sh';curl -sOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/main/$sh"&&chmod +x $sh&&./$sh -c https://disk.yandex.ru/d/HDgvq-iMbduqag -z;rm -f $sh
```

После нажатия <kbd>Enter</kbd> скрипт скачается и запустится

<img src="screenshots/6.png"/>

При запуске скрипта в терминале выведется конфигурация развертывания и выбор опций развертывания

По окончанию выполнения скрипта все испольуемые файлы удаляются автоматически
