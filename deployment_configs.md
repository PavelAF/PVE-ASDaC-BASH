<details>
  <summary><b>👉 Конфигурации авторазвертывания для СПО (ДЭ и РЧ)</b></summary>
  <br>
  
  - **[Архив] Стенды демекзамена 09.02.06-2025, классический**
  ```bash
  (b=testing_api opts=( PVE-ASDaC-BASH.sh -c 'https://disk.yandex.ru/d/_20fjve5ERh5Sg' -z ) ;curl -sfOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/$b/${opts[0]}"&&{ chmod +x ${opts[0]}&&./"${opts[@]}";rm -f ${opts[0]};:;}||echo -e "\e[1;33m\nОшибка скачивания: проверьте подключение к Интернету, настройки DNS, прокси и URL адрес\ncurl exit code: $?\n\e[m">&2)
  ```
  - **[Архив] Стенды демекзамена 09.02.06-2025, все ВМ - ОС Альт**
  ```bash
  (b=testing_api opts=( PVE-ASDaC-BASH.sh -c 'https://disk.yandex.ru/d/9b8nYPkE7UDHHA' -z ) ;curl -sfOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/$b/${opts[0]}"&&{ chmod +x ${opts[0]}&&./"${opts[@]}";rm -f ${opts[0]};:;}||echo -e "\e[1;33m\nОшибка скачивания: проверьте подключение к Интернету, настройки DNS, прокси и URL адрес\ncurl exit code: $?\n\e[m">&2)
  ```

  - **[Архив] Стенды регионального чемпионата СиСА 2025 (модуль Б)**
  ```bash
  (b=testing_api opts=( PVE-ASDaC-BASH.sh -c 'https://disk.yandex.ru/d/1-vlJJU_0mzefA' -z ) ;curl -sfOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/$b/${opts[0]}"&&{ chmod +x ${opts[0]}&&./"${opts[@]}";rm -f ${opts[0]};:;}||echo -e "\e[1;33m\nОшибка скачивания: проверьте подключение к Интернету, настройки DNS, прокси и URL адрес\ncurl exit code: $?\n\e[m">&2)
  ```
  <details>
    <summary>👉 Стенд РЧ: системные требования и <b>особенности установки</b></summary>
    <br>
    В предложенной конфигурации представлены две версии развертки: одна предполагает доступность к настройке виртуального коммутатора SW-DT участнику, как того требует задание. Во втором варианте участник не будет иметь доступ к SW-DT, но коммутатор уже будет преднастроен. Это противоречит заданию, однако это единственный безопасный вариант для тех, у кого версия PVE младше 8.x (Альт Виртуализация и Proxmox VE <= 7.4). Т.к. в более ранних версиях PVE нет возможности тонко разграничить права для сетевых интерфейсов, в первом варианте участники будут иметь доступ к прикриплению всех хостовых bridge интерфейсов к ВМ, что может привести к неспортивному поведению.<br>
    <b>UPD</b>: На виртуальные машины SW{X}-HQ был предустановлен пакет <b>Open vSwitch</b>
    <br>
    <br>
    
  ![image](https://github.com/user-attachments/assets/eb105561-d312-4c71-94c1-37d01cd88453)
  ___
  </details>

  ___
</details>
<details>
  <summary><b>👉 Конфигурации авторазвертывания для юниоров </b></summary>
  <br>
  
  - **[Ред., Архив] Стенды для регионального чемпионата ССА Юниоры 2025 (модуль Б и Г)**
  ```bash
  (b=testing_api opts=( PVE-ASDaC-BASH.sh -c 'https://disk.yandex.ru/d/YR3eelCZR_JVXQ/Script-Images/ASDaC_RCJ-2025_multi.conf_v2.txt' -z ) ;curl -sfOL "https://raw.githubusercontent.com/PavelAF/PVE-ASDaC-BASH/$b/${opts[0]}"&&{ chmod +x ${opts[0]}&&./"${opts[@]}";rm -f ${opts[0]};:;}||echo -e "\e[1;33m\nОшибка скачивания: проверьте подключение к Интернету, настройки DNS, прокси и URL адрес\ncurl exit code: $?\n\e[m">&2)
  ```
  <details>
    <summary>👉 <b>Информация</b>: автор конфигурации, инструкция по развертыванию</summary>
    <br>
    Разработчик: Рачеев А.В.<br>
    Под редакцией <a href="https://github.com/PavelAF">@PavelAF</a>
    <br><br>
    
Ссылка на инструкцию [README](https://disk.yandex.ru/d/YR3eelCZR_JVXQ/Script-Images/README.txt)<br>
Ссылка общую папку с файлами по заданию: [https://disk.yandex.ru/d/YR3eelCZR_JVXQ](https://disk.yandex.ru/d/YR3eelCZR_JVXQ)
    
  </details>
  
  ___
</details>
