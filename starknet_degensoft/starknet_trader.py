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
from starknet_degensoft.api_client2 import DegenSoftApiClient


TraderAccount = namedtuple('TraderAccount', field_names=('private_key', 'starknet_account',
                                                         'account'))


class StarknetTrader(BaseTrader):
    def __init__(self, config: Config, testnet=False):
        self.config = config
        self.paused = False
        self.stopped = False
        self.testnet = testnet
        self.starknet_client = GatewayClient('testnet' if testnet else
                                             random.choice(self.config.networks.starknet.rpc))
        self.starknet_contracts = self.config.data['starknet_contracts']['goerli' if testnet else 'mainnet'].copy()
        self.starknet_eth_contract = self.starknet_contracts.pop('ETH')
        self.logger = logging.getLogger('starknet')
        self.logger.setLevel(logging.DEBUG)
        self.accounts = []

    def load_private_keys_csv(self, filename):
        accounts = []
        with open(filename) as f:
            for row in csv.DictReader(f):
                if 'ethereum_private_key' not in row or 'starknet_address' not in row or \
                        'starknet_private_key' not in row:
                    raise ValueError('bad CSV file format')
                ethereum_private_key = row['ethereum_private_key'] if row['ethereum_private_key'] else None
                if ethereum_private_key:
                    eth_account = Web3().eth.account.from_key(ethereum_private_key)  # checking ethereum private key
                    self.logger.debug(f'Loaded account: {eth_account.address}')
                try:
                    starknet_account = self.get_account(row['starknet_address'], row['starknet_private_key'])
                    # starknet_balance = Web3.from_wei(starknet_account.get_balance_sync(), 'ether')
                except ValueError:
                    raise ValueError('bad Starknet address or private key')
                # self.logger.debug(f'Loaded Starknet account: {hex(starknet_account.address)} -> {starknet_balance} ETH')
                self.logger.debug(f'Loaded Starknet account: {hex(starknet_account.address)}')
                accounts.append(TraderAccount(private_key=ethereum_private_key, starknet_account=starknet_account, account=None))
        self.accounts = accounts

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stopped = True

    def process_pause(self, sec=None):
        while range(sec) if sec else 1:
            time.sleep(1)
            if not self.paused:
                break
            if self.stopped:
                break

    @staticmethod
    def get_eth_price():
        # json_data = requests.get('https://api.binance.com/api/v3/avgPrice?symbol=ETHUSDT').json()
        json_data = requests.get('https://www.binance.com/api/v3/ticker/price?symbol=ETHUSDT').json()
        return float(json_data['price'])

    def get_tx_url(self, tx_hash):
        if self.testnet:
            return f'https://testnet.starkscan.co/tx/{tx_hash}'
        else:
            return f'https://starkscan.co/tx/{tx_hash}'

    def get_address_url(self, address):
        if self.testnet:
            return f'https://testnet.starkscan.co/contract/{address}'
        else:
            return f'https://starkscan.co/contract/{address}'

    def _run_project(self, project, account):
        eth_price = self.get_eth_price()
        if issubclass(project['cls'], BaseSwap):
            random_amount = random_float(project['amount_usd'][0] / eth_price,
                                         project['amount_usd'][1] / eth_price)
            token_name, token_address = random.choice(list(self.starknet_contracts.items()))
            if project['cls'] == MyswapSwap and not self.testnet:
                token_name = 'DAI'  # only DAI for myswap.xyz for now
                token_address = self.starknet_contracts[token_name]
            self.logger.info(f'Swap {project["cls"].swap_name}: {random_amount} ETH -> {token_name}')
            self.swap(swap_cls=project['cls'], account=account.starknet_account,
                      amount=random_amount, token_address=token_address)
        elif (project['cls'] == StarkgateBridge) and account.private_key:
            random_amount = random_float(*project['amount'])
            self.logger.info(f'Bridge Stargate from {project["network"]} -> {random_amount} ETH')
            self.deposit_starkgate(ethereum_private_key=account.private_key,
                                   starknet_account=account.starknet_account,
                                   amount=random_amount)
        elif (project['cls'] == LayerswapBridge) and account.private_key:
            random_amount = random_float(*project['amount'])
            self.logger.info(f'Bridge Layerswap from {project["network"]} -> {random_amount} ETH')
            self.deposit_layerswap(source_network=project['network'],
                                   ethereum_private_key=account.private_key,
                                   starknet_account=account.starknet_account,
                                   amount=random_amount)

    def run(self, projects, wallet_delay=(0, 0), project_delay=(0, 0), shuffle=False, api: DegenSoftApiClient = None):
        self.paused = False
        self.stopped = False
        if shuffle:
            random.shuffle(self.accounts)
        self.logger.info(f'Ethereum price: {self.get_eth_price()}$')
        for i, account in enumerate(self.accounts, 1):
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            balance = Web3.from_wei(account.starknet_account.get_balance_sync(), 'ether')
            starknet_address = hex(account.starknet_account.address)
            self.logger.info(f'Starknet Account {hex(account.starknet_account.address)} -> {balance} ETH')
            self.logger.info(self.get_address_url(starknet_address))
            is_account_deployed = True if account.starknet_account.get_nonce_sync() else False
            for j, project in enumerate(projects, 1):
                if self.paused:
                    self.process_pause()
                if self.stopped:
                    break
                if issubclass(project['cls'], BaseSwap) and not is_account_deployed:
                    self.logger.error('account not deployed yet')
                    break
                action = 'swap' if issubclass(project['cls'], BaseSwap) else 'bridge'
                while 1:
                    if self.paused:
                        self.process_pause()
                    if self.stopped:
                        break
                    try:
                        resp = api.new_action(action, starknet_address)
                        if resp['success']:
                            try:
                                self._run_project(project, account)
                            except Exception as ex:
                                self.logger.error(ex)
                                api.cancel_last_action()
                        else:
                            self.logger.error('API error: %s' % resp)
                        break
                    except Exception as ex:
                        self.logger.error('API error: %s' % ex)
                        self.logger.error('Retry in 60 sec.')
                        self.process_pause(60)
                if j < len(projects):
                    self.random_delay(project_delay)
            if i < len(self.accounts):
                self.random_delay(wallet_delay)

    def get_account(self, address, private_key) -> StarknetAccount:
        key_par = KeyPair.from_private_key(key=int(private_key, base=16))
        account = StarknetAccount(
            client=self.starknet_client,
            address=address,
            key_pair=key_par,
            chain=StarknetChainId.TESTNET if self.testnet else StarknetChainId.MAINNET
        )
        account.ESTIMATED_FEE_MULTIPLIER = 1.0
        return account

    def setup_account(self, account: StarknetAccount):
        raise NotImplementedError()

    def deposit_layerswap(self, source_network, ethereum_private_key, starknet_account, amount):
        if self.testnet:
            network_config = self.config.data['networks']['ethereum_goerli']
        else:
            network_config = self.config.data['networks'][source_network.lower().replace(' ', '_')]
        node = Node(rpc_url=random.choice(network_config['rpc']), explorer_url=network_config['explorer'])
        account = Account(node=node, private_key=ethereum_private_key)
        bridge = LayerswapBridge(testnet=self.testnet)
        tx_hash = bridge.deposit(account=account, amount=amount, to_l2_address=hex(starknet_account.address))
        self.logger.info(node.get_explorer_transaction_url(tx_hash))
        return tx_hash.hex()

    def deposit_starkgate(self, ethereum_private_key, starknet_account, amount):
        network_config = self.config.data['networks']['ethereum_goerli' if self.testnet else 'ethereum']
        node = Node(rpc_url=random.choice(network_config['rpc']), explorer_url=network_config['explorer'])
        bridge = StarkgateBridge(node=node, network='testnet' if self.testnet else 'mainnet')
        account = Account(node=node, private_key=ethereum_private_key)
        self.logger.info(node.get_explorer_address_url(account.address))
        tx_hash = bridge.deposit(account=account,
                                 amount=Web3.to_wei(amount, 'ether'),
                                 to_l2_address=hex(starknet_account.address))
        self.logger.info(node.get_explorer_transaction_url(tx_hash))
        self.logger.info(self.get_tx_url('').replace('/tx/', f'/eth-tx/{tx_hash.hex()}'))
        return tx_hash.hex()

    def swap(self, swap_cls, account, amount, token_address, wait_for_tx=True):
        s = swap_cls(account=account, testnet=self.testnet, eth_contract_address=self.starknet_eth_contract)
        res = s.swap_eth_to_token(amount=Web3.to_wei(amount, 'ether'),
                                  token_address=token_address,
                                  slippage=self.config.slippage)
        self.logger.info(self.get_tx_url(hex(res.transaction_hash)))
        if wait_for_tx:
            self.logger.debug('waiting for tx confirmation...')
            self.starknet_client.wait_for_tx_sync(res.transaction_hash, check_interval=3, wait_for_accept=False)
        return hex(res.transaction_hash)
