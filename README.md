# #PROF39
**Пре-конфиг стендов демекзамена 09.02.06-2025, классический**
```
sh='PVE-ASDaC-BASH.sh';curl -sOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/main/$sh"&&chmod +x $sh&&./$sh -c https://disk.yandex.ru/d/HDgvq-iMbduqag -z;rm -f $sh
```
**Пре-конфиг стендов демекзамена 09.02.06-2025, только ОС Альт**
```
sh='PVE-ASDaC-BASH.sh';curl -sOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/main/$sh"&&chmod +x $sh&&./$sh -c https://disk.yandex.ru/d/259h8afDR9hqyQ -z;rm -f $sh
```


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
