# -*- coding: utf-8 -*-
import functools
import logging
import os
import random
import platform
import re
import sys
from decimal import Decimal

import colorlog
import requests
from web3 import Web3


def load_lines(filename):
    with open(filename) as f:
        return [row.strip() for row in f if row and not row.startswith('#')]


# log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%Y-%m-%d %H:%M:%S')
log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', '%m-%d %H:%M:%S')

color_formatter = colorlog.ColoredFormatter(
    '%(log_color)s%(asctime)s - %(levelname)s - %(message)s',
    log_colors={
        'DEBUG': 'cyan',
        'INFO': 'white,bold',
        'WARNING': 'yellow',
        'ERROR': 'red',
        'CRITICAL': 'red,bg_white',
    },
    reset=True,
    style='%'
)


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


def random_float(a, b, diff=1):
    random_number = random.uniform(a, b)
    try:
        precision_a = len(str(a).split('.')[1])
    except IndexError:
        precision_a = 0
    try:
        precision_b = len(str(b).split('.')[1])
    except IndexError:
        precision_b = 0
    precision = max(precision_a, precision_b)
    return round(random_number, precision + diff)


def setup_file_logging(logger, log_file):
    # logging file handler
    if(platform.system() == 'Darwin'):
        log_file = os.path.expanduser(f"~/Desktop/StarkNet/{log_file}")
    file_handler = logging.FileHandler(log_file, mode='a')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)


def setup_color_logging(logger):
    handler = logging.StreamHandler()
    # handler.setLevel(logging.DEBUG)
    handler.setFormatter(color_formatter)
    # handler.setFormatter(log_formatter)
    logger.addHandler(handler)


def get_explorer_address_url(address, base_explorer_url):
    return f'{base_explorer_url}address/{address}'


def get_explorer_tx_url(tx_hash, base_explorer_url):
    return f'{base_explorer_url}tx/{Web3.to_hex(tx_hash)}'


def uniswap_v2_calculate_tokens_and_price(x, y, amount_x, fee=0.003):
    # Учет комиссии
    x = Decimal(x)
    y = Decimal(y)
    delta_x_prime = Decimal(int(amount_x * (1 - fee)))

    # Обновление количества токенов A и B в пуле после обмена
    k = x * y
    x_prime = x + delta_x_prime
    y_prime = k / x_prime

    # Расчет количества полученных токенов B
    delta_y = y - y_prime

    return int(delta_y)


def convert_urls_to_links(text):
    # Regular expression pattern to match URLs
    url_pattern = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

    def replace_url(match):
        url = match.group(0)
        return '<a href="{0}">{0}</a>'.format(url)

    # Replace URLs with clickable links
    result = re.sub(url_pattern, replace_url, text)
    return result


def mask_hex_in_string(input_string):
    # Разделяем входную строку на части с использованием тегов "a href"
    pattern_link = re.compile(r'(<a href=".*?".*?>)', re.DOTALL)
    parts = pattern_link.split(input_string)
    pattern_hex = re.compile(r'(0x)([0-9a-fA-F]+)')
    # Обрабатываем каждую часть
    for i in range(len(parts)):
        # Если часть содержит ссылку, оставляем её без изменений
        if pattern_link.fullmatch(parts[i]):
            continue
        # Если нет, заменяем hex на звездочки, оставив первые и последние 4 символа
        else:
            parts[i] = pattern_hex.sub(
                lambda m: m.group(1) + m.group(2)[:4] + '*' * (len(m.group(2)) - 8) + m.group(2)[-4:], parts[i])
    return ''.join(parts)


def get_ethereum_gas():
    url1 = "https://api.etherscan.io/api?module=gastracker&action=gasoracle"
    url2 = "https://etherscan.io/autoUpdateGasTracker.ashx?sid=2d7306740787df76b0251564d7b71bc5"
    try:
        r = requests.get(url1)
        r1 = float(r.json()['result']['SafeGasPrice'])
        return r1
    except:
        pass
    try:
        r = requests.get(url2, headers={
            "X-Requested-With": "XMLHttpRequest",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            "Cookie": "ASP.NET_SessionId=v4bk44fd1wl2qtjfeqffchrn; _gid=GA1.2.646646230.1691738384; __cflb=02DiuFnsSsHWYH8WqVXaqGvd6BSBaXQLUn3pDNvdBsJJQ; _ga_XPR6BMZXSN=GS1.1.1691909625.1.1.1691910169.0.0.0; _ga_T1JC9RNQXV=GS1.1.1691933672.12.0.1691933672.0.0.0; _ga=GA1.2.1937570242.1691308386; cf_clearance=cECnIFmDx1Sk0iXdNUBHlSqQ_Yrjm1yn.LU88pDY.04-1691933675-0-1-4b32a90f.8bfae033.b3562468-0.2.1691933675; __cuid=92de69d8ce3a43a996c84f3abc18d6c0; amp_fef1e8=3ebd2a67-f4bc-4529-9ead-fa408e774325R...1h7nho042.1h7nho04r.1.1.2"
        })
        r2 = float(r.json()['avgPrice'])
        return r2
    except:
        pass
    return 0


# def force_async(fn):
#     # turns a sync function to async function using threads
#     from concurrent.futures import ThreadPoolExecutor
#     import asyncio
#     pool = ThreadPoolExecutor()
#
#     @functools.wraps(fn)
#     def wrapper(*args, **kwargs):
#         future = pool.submit(fn, *args, **kwargs)
#         return asyncio.wrap_future(future)  # make it awaitable
#
#     return wrapper


def force_sync(fn):
    # turn an async function to sync function
    import asyncio

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        res = fn(*args, **kwargs)
        if asyncio.iscoroutine(res):
            return asyncio.run(res)
            # return asyncio.get_event_loop().run_until_complete(res)
        return res

    return wrapper
