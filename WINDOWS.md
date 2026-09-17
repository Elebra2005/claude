# Запуск в Windows

Без git и без bash — они в Windows не установлены по умолчанию.

## 1. Python

Поставить с [python.org/downloads](https://www.python.org/downloads/) и **обязательно
отметить галочку «Add python.exe to PATH»** на первом экране установщика.

Проверка — открыть новое окно командной строки (`Win+R` → `cmd`) и ввести:

```
python --version
```

Должна показаться версия вроде `Python 3.12.x`.

## 2. ffmpeg

Нужен, чтобы сцены сцеплялись по последнему кадру и склеивались в ролик:

```
winget install Gyan.FFmpeg
```

После установки **закрыть и открыть окно консоли заново** — иначе `ffmpeg` не
найдётся. Проверка: `ffmpeg -version`.

## 3. Скачать проект

Открыть ссылку в браузере — скачается zip:

https://github.com/Elebra2005/claude/archive/refs/heads/claude/cool-darwin-cca52l.zip

Распаковать, например в `C:\claude-video`. Внутри должна лежать папка вроде
`claude-claude-cool-darwin-cca52l` с файлами `scenario.py`, `run_alexander.py`
и папкой `scenarios`.

## 4. Запустить

В командной строке (путь подставьте свой):

```
cd C:\claude-video\claude-claude-cool-darwin-cca52l
set HF_KEY=key_id:key_secret
python run_alexander.py
```

`key_id` и `key_secret` — из консоли Higgsfield ([cloud.higgsfield.ai](https://cloud.higgsfield.ai),
раздел API keys), склеенные через двоеточие, без кавычек и без пробелов.

Скрипт поставит недостающую библиотеку, покажет хронометраж и начнёт генерацию.
Готовые файлы появятся в `out\alexander`.

Дальше:

```
python run_alexander.py rolik-2
python run_alexander.py rolik-3
python run_alexander.py all
```

## Если что-то пошло не так

| Сообщение | Что делать |
|---|---|
| `"python" не является внутренней или внешней командой` | Python не в PATH: переустановить с галочкой «Add python.exe to PATH» или ввести полный путь, например `C:\Users\<имя>\AppData\Local\Programs\Python\Python312\python.exe run_alexander.py` |
| `не задан ключ Higgsfield` | Команда `set HF_KEY=...` выполняется в том же окне консоли, что и запуск. Новое окно — задавать заново |
| `ffmpeg не найден` | Установить по шагу 2 и перезапустить консоль; без него сцены всё равно сгенерируются, но склеивать придётся вручную |
| `Ошибка: Higgsfield API error 401` | Неверный ключ: проверьте, что это `key_id:key_secret` целиком |
| `Ошибка: Higgsfield API error 402` или про баланс | Пополнить баланс в консоли Higgsfield |
| Прогон прервался | Запустить ту же команду снова — доделает только недостающие сцены |

В PowerShell вместо `set HF_KEY=...` пишется `$env:HF_KEY="key_id:key_secret"`.
