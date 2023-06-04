# -*- coding: utf-8 -*-
import csv
import logging
import random
import time
from collections import namedtuple

import requests
from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.models.chains import StarknetChainId
from starknet_py.net.signer.stark_curve_signer import KeyPair
from web3 import Web3

from starknet_degensoft.api import Account, Node
from starknet_degensoft.api_client2 import DegenSoftApiClient
from starknet_degensoft.config import Config
from starknet_degensoft.layerswap import LayerswapBridge
from starknet_degensoft.starkgate import StarkgateBridge
from starknet_degensoft.starknet_swap import MyswapSwap, JediSwap, TenKSwap, BaseSwap, StarknetToken
from starknet_degensoft.trader import BaseTrader
from starknet_degensoft.utils import random_float

TraderAccount = namedtuple('TraderAccount', field_names=('private_key', 'starknet_address', 'starknet_account'))


def action_decorator(action):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            while 1:
                if self.paused:
                    self.process_pause()
                if self.stopped:
                    break
                try:
                    resp = self._api.new_action(action, self._api_address)
                    if resp['success']:
                        if resp['is_whitelisted']:
                            self.logger.info('Wallet is in the WL')
                        else:
                            self.logger.info('Wallet is NOT in the WL')
                        try:
                            return func(self, *args, **kwargs)
                        except Exception as ex:
                            self.logger.error(ex)
                            self.logger.info('Points refunding for an unsuccessful action...')
                            self._api.cancel_last_action()
                    else:
                        raise RuntimeError(resp)
                    break
                except Exception as ex:
                    self.logger.error('API error: %s' % ex)
                    self.logger.error('Retry in 60 sec.')
                    self.process_pause(60)

        return wrapper

    return decorator


def get_price(symbol: str):
    json_data = requests.get(f'https://www.binance.com/api/v3/ticker/price?symbol={symbol.upper()}USDT').json()
    return float(json_data['price'])


class StarknetTrader(BaseTrader):
    def __init__(self, config: Config, testnet=False):
        self.config = config
        self.paused = False
        self.stopped = False
        self.testnet = testnet
        self._api = None
        self._api_address = None
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
            dialect = csv.Sniffer().sniff(f.read(1024), delimiters=";,")
            f.seek(0)
            for row in csv.DictReader(f, dialect=dialect):
                if 'ethereum_private_key' not in row or 'starknet_address' not in row or \
                        'starknet_private_key' not in row:
                    raise ValueError('bad CSV file format')
                ethereum_private_key = row['ethereum_private_key'] if row['ethereum_private_key'] else None
                if ethereum_private_key:
                    eth_account = Web3().eth.account.from_key(ethereum_private_key)  # checking ethereum private key
                    self.logger.debug(f'Loaded account: {eth_account.address}')
                try:
                    starknet_address = row['starknet_address']
                    starknet_account = self.get_account(starknet_address, row['starknet_private_key'])
                    # starknet_balance = Web3.from_wei(starknet_account.get_balance_sync(), 'ether')
                except ValueError:
                    raise ValueError('bad Starknet address or private key')
                # self.logger.debug(f'Loaded Starknet account: {hex(starknet_account.address)} -> {starknet_balance} ETH')
                self.logger.debug(f'Loaded Starknet account: {hex(starknet_account.address)}')
                accounts.append(TraderAccount(private_key=ethereum_private_key, starknet_address=starknet_address,
                                              starknet_account=starknet_account))
        self.accounts = accounts

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stopped = True

    def process_pause(self, sec=None):
        for i in range(sec) if sec else 1:
            time.sleep(1)
            if not self.paused:
                break
            if self.stopped:
                break

    # @staticmethod
    # def get_eth_price():
    #     # json_data = requests.get('https://api.binance.com/api/v3/avgPrice?symbol=ETHUSDT').json()
    #     json_data = requests.get('https://www.binance.com/api/v3/ticker/price?symbol=ETHUSDT').json()
    #     return float(json_data['price'])
    #
    # @staticmethod
    # def get_btc_price():
    #     json_data = requests.get(f'https://www.binance.com/api/v3/ticker/price?symbol=BTCUSDT').json()
    #     return float(json_data['price'])

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

    # def _run_project(self, project, account, is_last_project=False):
    #     eth_price = get_price('ETH')
    #     # print(project)
    #     if project['cls'] is None:
    #         self.back_swap(starknet_account=account.starknet_account,
    #                        count=project['count'], min_amount_usd=project['amount_usd'])
    #     elif issubclass(project['cls'], BaseSwap):
    #         random_amount = random_float(project['amount_usd'][0] / eth_price,
    #                                      project['amount_usd'][1] / eth_price)
    #         token_name, token_address = random.choice(list(self.starknet_contracts.items()))
    #         if project['cls'] == MyswapSwap and not self.testnet:
    #             token_name = 'DAI'  # only DAI for myswap.xyz for now
    #             token_address = self.starknet_contracts[token_name]
    #         self.logger.info(f'Swap {project["cls"].swap_name}: {random_amount:.4f} ETH -> {token_name}')
    #         self.swap(swap_cls=project['cls'], account=account.starknet_account,
    #                   amount=random_amount, token_address=token_address,
    #                   wait_for_tx=True if not is_last_project else False)
    #     elif (project['cls'] == StarkgateBridge) and account.private_key:
    #         random_amount = random_float(*project['amount'])
    #         self.logger.info(f'Bridge Stargate from {project["network"]} -> {random_amount} ETH')
    #         self.deposit_starkgate(ethereum_private_key=account.private_key,
    #                                starknet_account=account.starknet_account,
    #                                amount=random_amount)
    #     elif (project['cls'] == LayerswapBridge) and account.private_key:
    #         random_amount = random_float(*project['amount'])
    #         self.logger.info(f'Bridge Layerswap from {project["network"]} -> {random_amount} ETH')
    #         self.deposit_layerswap(source_network=project['network'],
    #                                ethereum_private_key=account.private_key,
    #                                starknet_account=account.starknet_account,
    #                                amount=random_amount)

    def run(self, projects, wallet_delay=(0, 0), project_delay=(0, 0), shuffle=False, api: DegenSoftApiClient = None):
        self.paused = False
        self.stopped = False
        self._api = api
        if shuffle:
            random.shuffle(self.accounts)
        self.logger.info(f'Ethereum price: {get_price("ETH")}$')
        for i, account in enumerate(self.accounts, 1):
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            balance = Web3.from_wei(account.starknet_account.get_balance_sync(), 'ether')
            starknet_address = hex(account.starknet_account.address)
            self.logger.info(f'Starknet Account {hex(account.starknet_account.address)} ({balance:.4f} ETH)')
            # self.logger.info(self.get_address_url(starknet_address))
            is_account_deployed = True if account.starknet_account.get_nonce_sync() else False
            for j, project in enumerate(projects, 1):
                if self.paused:
                    self.process_pause()
                if self.stopped:
                    break
                if (project['cls'] is None or issubclass(project['cls'], BaseSwap)) and not is_account_deployed:
                    self.logger.error('account not deployed yet')
                    break
                self._api_address = [starknet_address, account.starknet_address]

                if project['cls'] is None:
                    self.back_swap(starknet_account=account.starknet_account,
                                   count=project['count'], min_amount_usd=project['amount_usd'])
                elif issubclass(project['cls'], BaseSwap):
                    eth_price = get_price('ETH')
                    random_amount = random_float(project['amount_usd'][0] / eth_price,
                                                 project['amount_usd'][1] / eth_price)
                    if project['cls'] == MyswapSwap:
                        token_names = ('DAI', 'USDC', 'USDT')
                    else:
                        token_names = tuple(self.starknet_contracts.keys())
                    token_name = random.choice(token_names)
                    token_address = self.starknet_contracts[token_name]
                    wait_for_tx = False if j == len(projects) else True
                    self.logger.info(f'Swap {project["cls"].swap_name}: {random_amount:.4f} ETH -> {token_name}')
                    # self.swap_eth(swap_cls=project['cls'], account=account.starknet_account,
                    #               amount=random_amount, token_address=token_address,
                    #               wait_for_tx=True if not is_last_project else False)
                    self.swap(swap_cls=project['cls'], account=account.starknet_account,
                              amount=Web3.to_wei(random_amount, 'ether'),
                              token_a_address=self.starknet_eth_contract,
                              token_b_address=token_address,
                              wait_for_tx=wait_for_tx)
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
                # self._run_project(project, account, is_last_project)
                # action = 'swap' if project['cls'] is None or issubclass(project['cls'], BaseSwap) else 'bridge'
                # while 1:
                #     if self.paused:
                #         self.process_pause()
                #     if self.stopped:
                #         break
                #     try:
                #         self.logger.debug(f'{starknet_address} {account.starknet_address}')
                #         resp = api.new_action(action, [starknet_address, account.starknet_address])
                #         # print(resp)
                #         if resp['success']:
                #             if resp['is_whitelisted']:
                #                 self.logger.info('Wallet is in the WL')
                #             else:
                #                 self.logger.info('Wallet is NOT in the WL')
                #             try:
                #                 is_last_project = True if j == len(projects) else False
                #                 self._run_project(project, account, is_last_project=is_last_project)
                #             except Exception as ex:
                #                 self.logger.error(ex)
                #                 self.logger.info('Points refunding for an unsuccessful action...')
                #                 api.cancel_last_action()
                #                 # raise
                #         else:
                #             self.logger.error('API error: %s' % resp)
                #         # break
                #     except Exception as ex:
                #         raise
                #         self.logger.error('API error: %s' % ex)
                #         self.logger.error('Retry in 60 sec.')
                #         self.process_pause(60)
                if j < len(projects):
                    self.random_delay(project_delay)
            if i < len(self.accounts):
                self.random_delay(wallet_delay)

    def get_account(self, address, private_key) -> StarknetAccount:
        try:
            _key = int(private_key)
        except Exception:
            _key = int(private_key, base=16)
        key_par = KeyPair.from_private_key(key=_key)
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

    def back_swap(self, starknet_account, count, min_amount_usd):
        # self.logger.debug(f'count={count}, amount_usd={min_amount_usd}')
        cnt = 0
        tokens_to_swap = []
        self.logger.info('Looking up for the tokens...')
        for token_symbol in self.starknet_contracts:
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            token = StarknetToken(self.starknet_contracts[token_symbol], starknet_account)
            balance = token.balance()
            if token_symbol in ('DAI', 'USDC', 'USDT'):
                balance_usd = token.from_native(balance)
            elif token_symbol == 'WBTC':
                balance_usd = token.from_native(balance) * get_price('BTC')
            else:
                raise ValueError(f'bad token {token_symbol}, could not calculate USD token balance')
            # self.logger.debug(f'balance {token.from_native(balance):.4f} {token_symbol} ({balance_usd:.4f} USD)')
            if balance_usd > min_amount_usd:
                if token_symbol in ('DAI', 'USDC', 'USDT'):
                    swap_cls = random.choice((MyswapSwap, JediSwap, TenKSwap))
                else:
                    swap_cls = random.choice((JediSwap, TenKSwap))
                tokens_to_swap.append(dict(cls=swap_cls, token=token, symbol=token_symbol,
                                           balance=balance, balance_usd=balance_usd))
                cnt += 1
            if cnt >= count:
                break
        random.shuffle(tokens_to_swap)
        for i, token_to_swap in enumerate(tokens_to_swap, 1):
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            wait_for_tx = False if i == len(token_to_swap) else True
            balance_from_native = token_to_swap["token"].from_native(token_to_swap["balance"])
            self.logger.info(f'Swap {token_to_swap["cls"].swap_name}: {balance_from_native:.4f} '
                             f'{token_to_swap["symbol"]} ({token_to_swap["balance_usd"]:.4f} USD) -> ETH')
            self.swap(swap_cls=token_to_swap["cls"],
                      account=starknet_account,
                      amount=token_to_swap["balance"],
                      token_a_address=self.starknet_contracts[token_to_swap["symbol"]],
                      token_b_address=self.starknet_eth_contract,
                      wait_for_tx=wait_for_tx)

    @action_decorator('bridge')
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

    @action_decorator('bridge')
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

    # @action_decorator('swap')
    # def swap_eth(self, swap_cls, account, amount, token_address, wait_for_tx=True):
    #     s = swap_cls(account=account, testnet=self.testnet, eth_contract_address=self.starknet_eth_contract)
    #     res = s.swap_eth_to_token(amount=Web3.to_wei(amount, 'ether'),
    #                               token_address=token_address,
    #                               slippage=self.config.slippage)
    #     self.logger.info(self.get_tx_url(hex(res.transaction_hash)))
    #     if wait_for_tx:
    #         self.logger.debug('Waiting for tx confirmation...')
    #         self.starknet_client.wait_for_tx_sync(res.transaction_hash, check_interval=3, wait_for_accept=False)
    #     return hex(res.transaction_hash)

    @action_decorator('swap')
    def swap(self, swap_cls, account, amount, token_a_address, token_b_address, wait_for_tx=True):
        s = swap_cls(account=account, testnet=self.testnet, eth_contract_address=self.starknet_eth_contract)
        res = s.swap(amount=amount, token_a_address=token_a_address, token_b_address=token_b_address,
                     slippage=self.config.slippage)
        self.logger.info(self.get_tx_url(hex(res.transaction_hash)))
        if wait_for_tx:
            self.logger.debug('Waiting for tx confirmation...')
            self.starknet_client.wait_for_tx_sync(res.transaction_hash, check_interval=5, wait_for_accept=False)
        return hex(res.transaction_hash)
