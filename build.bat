call venv\Scripts\Activate
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --onefile --windowed --clean --name starknet_degensoft ^
    --add-binary="venv\Lib\site-packages\libcrypto_c_exports.dll;." ^
    --add-binary="starknet_degensoft\abi\starkgate.json;starknet_degensoft\abi" ^
main.py
copy config.json dist\
pause
