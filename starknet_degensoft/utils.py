# -*- coding: utf-8 -*-
import os
import sys
import logging
import random
import colorlog
from web3 import Web3
from decimal import Decimal


def load_lines(filename):
    with open(filename) as f:
        return [row.strip() for row in f if row and not row.startswith('#')]


log_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')  # log message formatting

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
