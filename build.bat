pyinstaller --onefile --windowed --clean ^
    --add-binary="c:\Users\Administrator\AppData\Local\Programs\Python\Python311\Lib\site-packages\libcrypto_c_exports.dll;." ^
    --add-binary="c:\Users\Administrator\AppData\Local\Programs\Python\Python311\Lib\site-packages\starknet_py\cairo\deprecated_parse\cairo.ebnf;starknet_py\cairo\deprecated_parse" ^
gui.py
