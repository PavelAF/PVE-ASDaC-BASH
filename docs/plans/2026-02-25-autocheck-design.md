# Дизайн: Автопроверка стендов

## Цель

Инструмент для автоматизированного сбора информации с ВМ развёрнутых стендов.
Выполняет предопределённые команды на ВМ через QEMU Guest Agent или serial console (socat)
и выводит сырой результат. Без автоматической оценки правильности — пользователь сам
анализирует вывод.

## Архитектура

### Поток работы

1. Пользователь выбирает автопроверку (из меню `manage_stands` или через CLI-аргумент)
2. Скрипт загружает конфигурацию автопроверки из внешнего `.conf` файла
3. Скрипт обнаруживает развёрнутые стенды и предлагает выбрать один или несколько
4. Для каждого стенда, для каждой проверки, для каждой ВМ — выполняет команду и показывает вывод

### Механизмы выполнения команд

#### Guest Agent (`exec_agent`)

Два вызова PVE API:

1. `POST /nodes/{node}/qemu/{vmid}/agent/exec` с параметром `command` → возвращает `pid`
2. `GET /nodes/{node}/qemu/{vmid}/agent/exec-status?pid={pid}` → возвращает `out-data`, `err-data`, `exitcode`

Поллинг до `"exited": true` с таймаутом (10 секунд по умолчанию).

#### Serial Console (`exec_serial`)

Через socat с подключением к `/var/run/qemu-server/{VMID}.serial0`.

Алгоритм подключения:

1. Открыть socat-соединение
2. Отправить пустую строку (Enter)
3. Определить состояние:
   - Промпт (совпадает с `exec_serial_prompt`) → уже авторизован
   - Login-промпт (`login:` / `Username:`) → отправить логин, ждать `Password:`, отправить пароль
   - Password-промпт → отправить пароль
4. После авторизации — выполнить команду проверки
5. Захватить вывод, отбросить промпт/эхо команды

Настраиваемые параметры:

- `exec_serial_prompt` — regex для определения промпта
- `exec_serial_timeout` — таймаут ожидания (секунды)
- `exec_serial_login` / `exec_serial_password` — креденшелы (общие или per-VM)

### Обработка ошибок

- ВМ выключена → пропуск с сообщением "ВМ не запущена"
- Guest Agent не отвечает → сообщение "Guest Agent недоступен"
- Serial socket не найден → сообщение "Серийный порт не настроен"
- Таймаут → сообщение "Таймаут выполнения команды"

## Конфигурация

### Расположение файлов

```
/путь/к/скрипту/
├── PVE-ASDaC-BASH.sh
└── autocheck/
    ├── 09.02.03-2025_module1.conf
    ├── 09.02.03-2025_module2.conf
    └── custom_check.conf
```

### Формат файла конфига

Каждый `.conf` файл — bash-скрипт с простыми переменными:

```bash
# autocheck/09.02.03-2025_module1.conf

autocheck_name='Демэкзамен 09.02.03-2025, модуль 1'

# ВМ и способ подключения: exec_agent | exec_serial
autocheck_vms='
    ISP    = exec_agent
    HQ-RTR = exec_serial
    HQ-SRV = exec_agent
    HQ-CLI = exec_agent
    BR-RTR = exec_serial
    BR-SRV = exec_agent
'

# Настройки serial console (по умолчанию для всех exec_serial ВМ)
exec_serial_prompt='^[A-Za-z0-9._-]+[#>]\s*$'
exec_serial_timeout='3'
exec_serial_login='admin'
exec_serial_password='P@ssw0rd'

# Переопределение для конкретной ВМ (приоритетнее)
# BR-RTR_serial_login='root'
# BR-RTR_serial_password='toor'

# Проверки
check_1_name='IP-адреса'
check_1_vms='ISP HQ-RTR HQ-SRV BR-RTR BR-SRV'
check_1_cmd_exec_agent='ip -br a'
check_1_cmd_exec_serial='show ip interfaces brief'

check_2_name='Маршруты'
check_2_vms='HQ-RTR BR-RTR ISP'
check_2_cmd_exec_agent='ip route'
check_2_cmd_exec_serial='show ip route'
```

## Интеграция

### Меню

Новый пункт 11 в `manage_stands`:

```
  11. Автопроверка стенда
```

При выборе: скрипт сканирует папку `autocheck/`, показывает список конфигов, пользователь выбирает.

### Аргумент командной строки

```
-ac|--autocheck <файл>    Запустить автопроверку по указанному конфигу
```

Пример: `./PVE-ASDaC-BASH.sh --autocheck autocheck/09.02.03-2025_module1.conf`

### Маппинг ВМ

Имена ВМ из autocheck-конфига (ISP, HQ-RTR, ...) сопоставляются с `name` ВМ в пуле PVE.
Если ВМ из конфига не найдена в пуле — предупреждение и пропуск.

## Формат вывода

```
══════════════════════════════════════
 Автопроверка: демэкзамен 09.02.03-2025, модуль 1
 Стенд: Stand_01 (pool-01)
══════════════════════════════════════

── Проверка 1: IP-адреса ──

  [ISP] (exec_agent):
  lo       UNKNOWN  127.0.0.1/8
  ens18    UP       10.0.0.1/24
  ens19    UP       192.168.0.1/30

  [HQ-RTR] (exec_serial):
  Interface  IP-Address   Status
  eth0       192.168.0.2  up
  eth1       172.16.0.1   up

── Проверка 2: Маршруты ──

  [HQ-RTR] (exec_serial):
  S*   0.0.0.0/0 via 192.168.0.1
  C    172.16.0.0/24 directly connected
```

## Выбор стендов

При проверке нескольких стендов одной конфигурации:

- Один стенд → проверяем автоматически
- Несколько → пользователь выбирает по номерам (один, диапазон, или все)
- Вывод группируется по стенду
