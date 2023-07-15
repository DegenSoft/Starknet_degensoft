# -*- coding: utf-8 -*-
import base64
import binascii
import hashlib

# import gnupg
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util.Padding import unpad
from web3 import Web3


def is_base64(s):
    try:
        if len(s) == 64:
            Web3().eth.account.from_key(s)
            return False
    except Exception:
        ...
    try:
        # Attempt to decode the string as Base64
        decoded = base64.b64decode(s)
        # Ensure that the decoded string can be encoded back to the original input
        reencoded = base64.b64encode(decoded)
        return reencoded == s.encode()
    except Exception:
        return False


# def decrypt_gpg_file(file_name, password):
#     gpg = gnupg.GPG()
#     with open(file_name, 'rb') as f:
#         encrypted_data = f.read()
#     decrypted_data = gpg.decrypt(encrypted_data, passphrase=password)
#     if decrypted_data.ok:
#         try:
#             return io.StringIO(decrypted_data.wallets.decode('utf-8'))
#         except UnicodeDecodeError:
#             return io.BytesIO(decrypted_data.wallets)
#     else:
#         raise RuntimeError('decryption failed')


def get_cipher(password):
    salt = hashlib.sha256(password.encode('utf-8')).digest()
    key = PBKDF2(password.encode('utf-8'), salt, dkLen=32, count=1)
    return AES.new(key, AES.MODE_ECB)


def decrypt_private_key(encrypted_base64_pk, password):
    cipher = get_cipher(password)
    encrypted_pk = base64.b64decode(encrypted_base64_pk)
    # decrypted_bytes = unpad(cipher.decrypt(encrypted_pk), 16)
    decrypted_bytes = cipher.decrypt(encrypted_pk)
    decrypted_hex = binascii.hexlify(decrypted_bytes).decode()
    if len(decrypted_hex) in (66, 42):
        return '0x' + decrypted_hex[2:]
    else:
        return '0x' + decrypted_hex
