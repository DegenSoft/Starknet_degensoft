pip3 install virtualenv
~/Library/Python/3.11/bin/virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller

pyinstaller --onefile --windowed --clean --name starknet_degensoft --add-binary="starknet_degensoft/abi/starkgate.json:starknet_degensoft/abi" --add-binary="venv/lib/python3.11/site-packages/libcrypto_c_exports.dylib:." main.py
cp config.json dist/config.json
