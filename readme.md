# Установка

Для установки под Windows 10 64 нужно скачать и поставить следующие пакеты:

## Python 3.10 или 3.11

* https://www.python.org/downloads/windows/
* https://www.python.org/ftp/python/3.11.3/python-3.11.3-amd64.exe

При установке ставим галочку "Add Python to environment variables"

![image](https://github.com/slavik-investor/starknetArs/assets/591138/7031d644-d6c2-42b5-90e9-f7560f65cbe2)


## Git Bash
* https://git-scm.com/download/win
* https://github.com/git-for-windows/git/releases/download/v2.40.1.windows.1/Git-2.40.1-64-bit.exe

Обратить внимание на эту опцию:

![image](https://github.com/slavik-investor/starknetArs/assets/591138/4ccd9fe7-af20-485b-9bbc-d789098b9aca)


# Сборка

* Клонировать код репозитория в любое место
* Запустить командную строку и перейти в папку с кодом
* Выполнить `pip install -r requirements.txt`
* Попробовать запустить `python gui.py`, если всё ок переходим непосредственно к сборке
* Открыть файл `build.bat` и проверить, что имя пользователя и пути к файлам соответствуют реальным (`c:\Users\Administrator\`)
* Набрать команду `build`
* В результате появится папка `dist` и которой файл `starknet_degensoft.exe`

# Запуск

* Рядом с `starknet_degensoft.exe` в ту же папку необходимо положить файл `config.json`
* Убрать из него наш тестовый API ключ, если он там присутствует, перед публикацией
* Заполнить файл `private_keys.csv` нужными значениями с ключами и адресами кошельков Ethereum и Starknet
* Если приватный ключ Ethereum отсутствует в csv файле (первый столбец), то для таких кошельков мосты будут пропущены, даже если они отмечены галочкой в интерфейсе
