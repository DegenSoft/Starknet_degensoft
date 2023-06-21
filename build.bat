pyinstaller --onefile --windowed --clean --name starknet_degensoft ^
    --add-binary="c:\Users\Administrator\AppData\Local\Programs\Python\Python311\Lib\site-packages\libcrypto_c_exports.dll;." ^
    --add-binary="c:\Users\Administrator\AppData\Local\Programs\Python\Python311\Lib\site-packages\starknet_py\cairo\deprecated_parse\cairo.ebnf;starknet_py\cairo\deprecated_parse" ^
    --add-binary="starknet_degensoft\abi\starkgate.json;starknet_degensoft\abi" ^
gui.py
