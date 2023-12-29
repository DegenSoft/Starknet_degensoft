pip3 install virtualenv
virtualenv venv
source venv/bin/activate
pip install -r requirements.txt
pip install pyinstaller
pyinstaller --noconfirm starknet_degensoft.spec
cp config.json dist/config.json
