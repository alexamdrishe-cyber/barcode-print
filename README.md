# BarcodeXP

Программа для печати штрихкодов на принтере Xprinter XP-365B.

## Возможности
- Ввод начального кода (цифры, буквы, смешанное)
- Автоинкремент хвостовой цифровой части
- Выбор размера этикетки (пресеты + свой)
- Живой предпросмотр
- Текст сверху этикетки
- Переворот на 180°
- Прямая печать без диалога Windows

## Установка
    pip install python-barcode pillow pywin32

## Запуск
    python barcode_print.py

## Сборка exe
    python -m PyInstaller --onefile --noconsole --name BarcodeXP barcode_print.py
