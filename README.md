Ветка с тестированием нового функционала. Использовать с осторожностью!

Версия с прямым доступом к API должна ощутимо сократить задержки ожидания выполнения запросов к PVE, тем самым повысить отзывчивость скрипта и скорость развёртки стендов.

## Автопроверка стендов

Инструмент для автоматизированного сбора информации с ВМ развёрнутых стендов (hostname, IP, маршруты, конфиги и т.д.). Подключение через QEMU Guest Agent или serial console.

**Запуск:**
```bash
./PVE-ASDaC-BASH.sh --autocheck autocheck/09.02.06-2026_module1.conf
```

**Скачать и запустить с удалённого сервера:**
```bash
bash <(curl -sSL <URL_ДО_СКРИПТА>) --autocheck <URL_ДО_ФАЙЛА_ПРОВЕРКИ> -z -v
```

Или через меню: Управление стендами → пункт 11.

**Документация:** [docs/autocheck-instruction.md](docs/autocheck-instruction.md)

---

**Для тестирования (использовать с осторожностью!)**

```
sh='PVE-ASDaC-BASH.sh';curl -sOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/testing_api/$sh"&&chmod +x $sh&&./$sh -c https://disk.yandex.ru/d/_20fjve5ERh5Sg -z;rm -f $sh
```

