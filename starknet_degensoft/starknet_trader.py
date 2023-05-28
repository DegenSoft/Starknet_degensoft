# -*- coding: utf-8 -*-
import csv
import requests
import time
import logging
import random
from web3 import Web3
from collections import namedtuple
from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.models.chains import StarknetChainId
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_degensoft.api import Account, Node
from starknet_degensoft.starknet_swap import MyswapSwap, JediSwap, TenKSwap, BaseSwap
from starknet_degensoft.starkgate import StarkgateBridge
from starknet_degensoft.layerswap import LayerswapBridge
from starknet_degensoft.config import Config
from starknet_degensoft.trader import BaseTrader
from starknet_degensoft.utils import random_float


TraderAccount = namedtuple('TraderAccount', field_names=('private_key', 'starknet_account',
                                                         'account'))


class StarknetTrader(BaseTrader):
    def __init__(self, config: Config, testnet=False):
        self.config = config
        self.paused = False
        self.stopped = False
        self.testnet = testnet
        self.node = GatewayClient('testnet' if testnet else 'mainnet')
        self.logger = logging.getLogger('starknet')
        self.logger.setLevel(logging.DEBUG)
        self.accounts = []

    def load_private_keys_csv(self, filename):
        accounts = []
        with open(filename) as f:
            reader = csv.DictReader(f)
            for line in reader:
                if 'ethereum_private_key' not in line or 'starknet_address' not in line or \
                        'starknet_private_key' not in line:
                    raise ValueError('bad CSV file format')
                ethereum_private_key = line['ethereum_private_key'] if line['ethereum_private_key'] else None
                if ethereum_private_key:
                    eth_account = Web3().eth.account.from_key(ethereum_private_key)  # checking ethereum private key
                    self.logger.debug(f'Loaded account: {eth_account.address}')
                try:
                    starknet_account = self.get_account(line['starknet_address'], line['starknet_private_key'])
                except ValueError:
                    raise ValueError('bad Starknet address or private key')
                self.logger.debug(f'Loaded Starknet account: {hex(starknet_account.address)}')
                accounts.append(TraderAccount(private_key=ethereum_private_key, starknet_account=starknet_account, account=None))
        self.accounts = accounts

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stopped = True

    def process_pause(self):
        while 1:
            time.sleep(1)
            if not self.paused:
                break

    @staticmethod
    def get_eth_price():
        return float(requests.get('https://api.binance.com/api/v3/avgPrice?symbol=ETHUSDT').json()['price'])

    def run(self, projects, wallet_delay=(0, 0), project_delay=(0, 0), shuffle=False):
        self.paused = False
        self.stopped = False
        accounts = random.shuffle(self.accounts) if shuffle else self.accounts
        eth_price = self.get_eth_price()
        self.logger.info(f'Ethereum price: {eth_price}$')
        for i, account in enumerate(accounts, 1):
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            self.logger.info(hex(account.starknet_account.address))
            for j, project in enumerate(projects, 1):
                if issubclass(project['cls'], BaseSwap):
                    self.logger.debug(project['cls'].__name__)
                    random_amount = random_float(project['amount_usd'][0] / eth_price,
                                                 project['amount_usd'][1] / eth_price)
                    # self.logger.debug(f'{project["amount_usd"]}, {amount_min}, {amount_max}, {random_amount}')
                elif isinstance(project['cls'], StarkgateBridge):
                    pass  # todo
                elif isinstance(project['cls'], LayerswapBridge):
                    pass  # todo
                if j < len(projects):
                    self.random_delay(project_delay)
            if i < len(accounts):
                self.random_delay(wallet_delay)

    def get_account(self, address, private_key):
        key_par = KeyPair.from_private_key(key=int(private_key, base=16))
        account = StarknetAccount(
            client=self.node,
            address=address,
            key_pair=key_par,
            chain=StarknetChainId.TESTNET
        )
        account.ESTIMATED_FEE_MULTIPLIER = 1.0
        return account

    def setup_account(self, account: StarknetAccount):
        pass

    def bridge(self, bridge_cls, source_network, ethereum_private_key, starknet_account, amount):
        pass

    def starkgate(self, ethereum_private_key, starknet_account, amount):
        # todo: get RPC from config
        node = Node(rpc_url='https://goerli.infura.io/v3/c10b375472774c31abe0d4b295f3f2e9',
                    explorer_url='https://goerli.etherscan.io/')
        # node = Node(rpc_url='https://mainnet.infura.io/v3/c10b375472774c31abe0d4b295f3f2e9', explorer_url='https://etherscan.io/')
        bridge = StarkgateBridge(node=node, network='goerli')
        account = Account(node=node, private_key=ethereum_private_key)
        tx_hash = bridge.deposit(account=account,
                                 amount=amount,
                                 to_l2_address=starknet_account.address)
        return tx_hash.hex()

    def swap(self, swap_cls, account, amount, token_address):
        s = swap_cls(account=account, eth_contract_address=self.config.starknet_contracts['ETH'])
        res = s.swap_eth_to_token(amount=Web3.to_wei(amount, 'ether'),
                                  token_address=token_address,
                                  slippage=self.config.slippage)
        return hex(res.transaction_hash)
