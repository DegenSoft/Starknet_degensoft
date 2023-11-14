call venv\Scripts\Activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller==6.1.0
pyinstaller --onefile --windowed --clean --name starknet_degensoft ^
    --add-binary="venv\Lib\site-packages\libcrypto_c_exports.dll;." ^
    --add-binary="starknet_degensoft\abi\starkgate.json;starknet_degensoft\abi" ^
    --add-binary="starknet_degensoft\abi\sithswap.json;starknet_degensoft\abi" ^
main.py
copy config.json dist\
pause
