# -*- coding: utf-8 -*-
import base64
import binascii
import hashlib

# import gnupg
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import PBKDF2
from Crypto.Util.Padding import unpad
from web3 import Web3

hex_symbols = "0123456789abcdef"


def has_non_hex_symbols(s):
    for i in s.strip().strip("0x"):
        if i.lower() not in hex_symbols: return True
    return False


def is_base64(s):
    if not s:
        return False
    if has_non_hex_symbols(s):
        return True
    try:
        Web3().eth.account.from_key("0x" + s.strip().strip("0x"))
        return False
    except Exception as e:
        ...

    try:
        decoded = base64.b64decode(s)
        decoded = decoded.decode('utf-8')
        if has_non_hex_symbols(decoded):
            return True
        else:
            return False
    except:
        return False


def get_cipher(password):
    salt = hashlib.sha256(password.encode('utf-8')).digest()
    key = PBKDF2(password.encode('utf-8'), salt, dkLen=32, count=1)
    return AES.new(key, AES.MODE_ECB)


def decrypt_private_key(encrypted_base64_pk, password):
    is_utf8 = encrypted_base64_pk.startswith("UTF8")
    if is_utf8: encrypted_base64_pk = encrypted_base64_pk[4:]
    cipher = get_cipher(password)
    encrypted_pk = base64.b64decode(encrypted_base64_pk)
    decrypted_unpadded = cipher.decrypt(encrypted_pk)
    try:
        decrypted_bytes = unpad(decrypted_unpadded, 16)
    except Exception:
        decrypted_bytes = decrypted_unpadded.strip(b"\xf0").strip(b"\x0f")
    if is_utf8:
        decrypted_hex = decrypted_bytes.decode('utf-8')
    else:
        decrypted_hex = binascii.hexlify(decrypted_bytes).decode()
        if len(decrypted_hex) in (66, 42):
            return '0x' + decrypted_hex[2:]
        else:
            return '0x' + decrypted_hex

    return decrypted_hex
