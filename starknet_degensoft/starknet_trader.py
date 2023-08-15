# -*- coding: utf-8 -*-
import csv
import logging
import random
import time
from collections import namedtuple

import requests
from eth_account import Account as EthereumAccount
from starknet_py.net.client_errors import ClientError
from starknet_py.net.models.chains import StarknetChainId
from starknet_py.net.signer.stark_curve_signer import KeyPair
from web3 import Web3

from starknet_degensoft.api import Account, Node
from starknet_degensoft.api_client2 import DegenSoftApiClient, DegenSoftApiError
from starknet_degensoft.config import Config
from starknet_degensoft.layerswap import LayerswapBridge
from starknet_degensoft.starkgate import StarkgateBridge
from starknet_degensoft.starknet import Account as StarknetAccount, GatewayClient, FullNodeClient
from starknet_degensoft.starknet_swap import MyswapSwap, JediSwap, TenKSwap, BaseSwap, StarknetToken
from starknet_degensoft.utils import random_float, get_explorer_address_url, get_ethereum_gas

from degensoft.filereader import UniversalFileReader
from degensoft.decryption import is_base64

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
                            # transaction limit exception handler
                            attempt = 1
                            while True:
                                try:
                                    return func(self, *args, **kwargs)
                                except ClientError as ex:
                                    if 'StarknetErrorCode.TRANSACTION_LIMIT_EXCEEDED' in ex.message and attempt <= 5:
                                        random_delay = random.randint(50, 90)
                                        self.logger.error(f'Starknet RPC Error: StarknetErrorCode.TRANSACTION_LIMIT_EXCEEDED. Retry in {random_delay} sec.')
                                        self.process_pause(random_delay)
                                    else:
                                        raise ex
                                except Exception as ex:
                                    raise ex
                                attempt += 1
                        except Exception as ex:
                            self.logger.error(ex)
                            self.logger.info('Points refunding for an unsuccessful action...')
                            self._api.cancel_last_action()
                            # raise ex
                    else:
                        raise DegenSoftApiError(resp)
                    break
                except Exception as ex:
                    # raise ex
                    self.logger.error('API error: %s' % ex)
                    self.logger.error('Retry in 60 sec.')
                    self.process_pause(60)

        return wrapper

    return decorator


def get_price(symbol: str):
    json_data = requests.get(f'https://www.binance.com/api/v3/ticker/price?symbol={symbol.upper()}USDT').json()
    return float(json_data['price'])


class StarknetTrader:
    def __init__(self, config: Config, testnet=False):
        self.config = config
        self.paused = False
        self.stopped = False
        self.testnet = testnet
        self._api = None
        self._api_address = None
        rpc_url = random.choice(self.config.networks.starknet.rpc) if not testnet else \
            random.choice(self.config.networks.starknet_goerli.rpc)
        self.starknet_client = GatewayClient(rpc_url) if '.starknet.io' in rpc_url else FullNodeClient(rpc_url)
        self.starknet_contracts = self.config.data['starknet_contracts']['goerli' if testnet else 'mainnet'].copy()
        self.starknet_eth_contract = self.starknet_contracts.pop('ETH')
        self.logger = logging.getLogger('starknet')
        self.logger.setLevel(logging.DEBUG)
        self.accounts = []

    def load_private_keys(self, wallets):
        accounts = []
        # with open(filename) as f:
        #     dialect = csv.Sniffer().sniff(f.readline(), delimiters=";,")
        #     f.seek(0)
        for row in wallets:
            if 'ethereum_private_key' not in row or 'starknet_address' not in row or \
                    'starknet_private_key' not in row:
                raise ValueError('bad wallets file format')
            ethereum_private_key = row['ethereum_private_key'] if row['ethereum_private_key'] else None
            if ethereum_private_key:
                eth_account = Web3().eth.account.from_key(ethereum_private_key)  # checking ethereum private key
                # self.logger.debug(f'Loaded account: {eth_account.address}')
            try:
                starknet_address = row['starknet_address']
                starknet_account = self.get_account(starknet_address, row['starknet_private_key'])
                # starknet_balance = Web3.from_wei(starknet_account.get_balance_sync(), 'ether')
            except ValueError:
                raise ValueError('bad Starknet address or private key')
            # self.logger.debug(f'Loaded Starknet account: {hex(starknet_account.address)}')
            accounts.append(TraderAccount(private_key=ethereum_private_key, starknet_address=starknet_address,
                                          starknet_account=starknet_account))
        self.accounts = accounts

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stopped = True
        self.starknet_client.is_stopped = True

    def process_pause(self, sec=None):
        if sec:
            self.logger.debug(f'delay for {sec} sec.')
            for i in range(sec):
                time.sleep(1)
                if self.stopped:
                    break
        else:
            while True:
                if self.stopped or not self.paused:
                    break

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

    def run(self,
            projects: list,
            wallet_delay: tuple = (0, 0),
            project_delay: tuple = (0, 0),
            shuffle: bool = False,
            random_swap_project: bool = False,
            api: DegenSoftApiClient = None,
            config: dict = {}):
        self.paused = False
        self.stopped = False
        self._api = api
        if shuffle:
            random.shuffle(self.accounts)
        self.logger.info(f'Ethereum price: {get_price("ETH")}$')
        current_gas = get_ethereum_gas()
        gas_limit = config.get("gas_limit", 0)
        if gas_limit > 0 and current_gas > gas_limit:
            self.logger.info(f"Current Ethereum network gas ({current_gas} GWEI) is larger than selected ({gas_limit} GWEI). Retrying in 1 minute...")
            self.process_pause(60)
            if not self.stopped: return self.run(projects, wallet_delay, project_delay, shuffle, random_swap_project, api, config)
            else: return
        for i, account in enumerate(self.accounts, 1):
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            starknet_address = hex(account.starknet_account.address)
            for attempt_ in range(3):
                try:
                    balance = Web3.from_wei(account.starknet_account.get_balance_sync(), 'ether')
                    is_deployed = account.starknet_account.is_deployed_sync()
                    self.logger.info(f'Starknet Account {hex(account.starknet_account.address)} ({balance:.4f} ETH)')
                    break
                except Exception as ex:
                    is_deployed = None
                    self.logger.error(ex)
                    self.logger.info('retry')
            if is_deployed is None:
                self.logger.info(f'Starknet Account {hex(account.starknet_account.address)}')
                self.logger.error('could not get account balance and deploy status, probably RPC error')
                continue
            # choosing random SWAP project and uniq order
            uniq_projects = []
            swap_projects = []
            for k, project in enumerate(projects, 1):
                is_swap_project = project['cls'] and issubclass(project['cls'], BaseSwap)
                if is_swap_project:
                    swap_projects.append(project)
                if swap_projects and (not is_swap_project or k == len(projects)):
                    random.shuffle(swap_projects)
                    if random_swap_project:
                        swap_projects = swap_projects[:1]
                    uniq_projects += swap_projects
                    swap_projects = []
                if not is_swap_project:
                    uniq_projects.append(project)
            for j, project in enumerate(uniq_projects, 1):
                if self.paused:
                    self.process_pause()
                if self.stopped:
                    break
                if (project['cls'] is None or issubclass(project['cls'], BaseSwap)) and not is_deployed:
                    self.logger.error('Account not deployed yet')
                    break
                self._api_address = [account.starknet_address, starknet_address]
                wait_for_tx = False if j == len(uniq_projects) else True

                if project['cls'] is None:
                    if not self.config.data.get('simulate'):
                        self.back_swap(starknet_account=account.starknet_account,
                                       count=project['count'], min_amount_usd=project['amount_usd'])
                elif issubclass(project['cls'], BaseSwap):
                    eth_price = get_price('ETH')
                    random_amount = random_float(project['amount_usd'][0] / eth_price,
                                                 project['amount_usd'][1] / eth_price)
                    if project['cls'] == MyswapSwap:
                        token_names = list(self.starknet_contracts.keys())
                        token_names.remove('WBTC')
                    else:
                        token_names = tuple(self.starknet_contracts.keys())
                    token_name = random.choice(token_names)
                    token_address = self.starknet_contracts[token_name]
                    self.logger.info(f'Swap {project["cls"].swap_name}: {random_amount:.4f} ETH -> {token_name}')
                    if not self.config.data.get('simulate'):
                        self.swap(swap_cls=project['cls'], account=account.starknet_account,
                                  amount=Web3.to_wei(random_amount, 'ether'),
                                  token_a_address=self.starknet_eth_contract,
                                  token_b_address=token_address,
                                  wait_for_tx=wait_for_tx)
                elif (project['cls'] == StarkgateBridge) and account.private_key:
                    random_amount = random_float(*project['amount'])
                    self.logger.info(f'Bridge Stargate from {project["network"]} -> {random_amount} ETH')
                    if not self.config.data.get('simulate'):
                        self.deposit_starkgate(ethereum_private_key=account.private_key,
                                               starknet_account=account.starknet_account,
                                               amount=random_amount)
                elif (project['cls'] == LayerswapBridge) and account.private_key:
                    if not project['is_back']:
                        random_amount = random_float(*project['amount'])
                        self.logger.info(f'Bridge Layerswap from {project["network"]} -> {random_amount} ETH')
                        if not self.config.data.get('simulate'):
                            self.deposit_layerswap(source_network=project['network'],
                                                   ethereum_private_key=account.private_key,
                                                   starknet_account=account.starknet_account,
                                                   amount=random_amount)
                    else:
                        random_percent = random.randint(*project['amount_percent'])
                        self.logger.info(
                            f'Back bridge Layerswap to {project["network"]} -> {random_percent}% of balance')
                        if not self.config.data.get('simulate'):
                            self.withdraw_layerswap(ethereum_private_key=account.private_key,
                                                    starknet_account=account.starknet_account,
                                                    destination_network=project['network'],
                                                    amount_percent=random_percent,
                                                    wait_for_tx=wait_for_tx)
                if j < len(projects):
                    self.process_pause(random.randint(*project_delay))
                    # self.random_delay(project_delay)
            if i < len(self.accounts):
                # self.random_delay(wallet_delay)
                self.process_pause(random.randint(*wallet_delay))

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
        account.ESTIMATED_FEE_MULTIPLIER = 1.25
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
        if not tokens_to_swap:
            self.logger.info('No token balance to swap')
        for i, token_to_swap in enumerate(tokens_to_swap, 1):
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            wait_for_tx = False if i == len(tokens_to_swap) else True
            balance_from_native = token_to_swap["token"].from_native(token_to_swap["balance"])
            self.logger.info(f'Swap {token_to_swap["cls"].swap_name}: {balance_from_native:.4f} '
                             f'{token_to_swap["symbol"]} ({token_to_swap["balance_usd"]:.4f} USD) -> ETH')
            # self.logger.debug(f'wait_for_tx={wait_for_tx} i={i}, len()={len(tokens_to_swap)}')
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
    def withdraw_layerswap(self, ethereum_private_key, starknet_account, destination_network, amount_percent,
                           wait_for_tx=False):
        bridge = LayerswapBridge(testnet=self.testnet)
        ethereum_account = EthereumAccount.from_key(ethereum_private_key)
        to_l2_address = ethereum_account.address
        explorer_url = self.config.data['networks'][destination_network.lower().replace(' ', '_')]['explorer']
        from_netwrok = 'STARKNET_MAINNET' if not self.config.testnet else 'STARKNET_GOERLI'
        to_network = LayerswapBridge.NETWORK_TO_LS_NAME.get(destination_network, destination_network)
        deposit_data = bridge.get_deposit_amount_limits(from_network=from_netwrok, to_network=to_network)
        # if not deposit_data:
        #     raise ValueError('some error in Layerswap bridge call')
        min_amount = Web3.to_wei(deposit_data['min_amount'], 'ether')
        max_amount = Web3.to_wei(deposit_data['max_amount'], 'ether')
        # fee_amount = Web3.to_wei(deposit_data['FeeAmount'], 'ether')
        balance = starknet_account.get_balance_sync()
        fee = bridge.get_starknet_transfer_fee(starknet_account, to_l2_address)
        transfer_amount = int((balance - fee) * amount_percent / 100)
        if transfer_amount < 1:
            raise ValueError(f'Calculated amount less then zero because of the transfer fee, could not withdraw')
        elif transfer_amount < min_amount:
            raise ValueError(
                f'Calculated amount less then minimum layerswap amount: {Web3.from_wei(transfer_amount, "ether"):.4f} &lt; {Web3.from_wei(min_amount, "ether"):.4f}')
        elif transfer_amount > max_amount:
            raise ValueError(
                f'Calculated amount greater then minimum layerswap amount: {Web3.from_wei(transfer_amount, "ether"):.4f} &gt; {Web3.from_wei(max_amount, "ether"):.4f}')
        self.logger.debug(f'Amount is {Web3.from_wei(transfer_amount, "ether"):.4f} ETH')
        # print(type(Web3.from_wei(transfer_amount, 'ether')))
        tx_hash = bridge.deposit(account=starknet_account, amount=Web3.from_wei(transfer_amount, 'ether'),
                                 to_l2_address=to_l2_address, to_network=destination_network)
        self.logger.info(self.get_tx_url(tx_hash))
        self.logger.debug(get_explorer_address_url(to_l2_address, explorer_url))
        if wait_for_tx and not self.stopped:
            self.logger.debug('Waiting for tx confirmation...')
            self.starknet_client.wait_for_pending_tx_sync(int(tx_hash, base=16), check_interval=5)
        return tx_hash

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

    @action_decorator('swap')
    def swap(self, swap_cls, account, amount, token_a_address, token_b_address, wait_for_tx=True):
        s = swap_cls(account=account, testnet=self.testnet, eth_contract_address=self.starknet_eth_contract)
        res = s.swap(amount=amount, token_a_address=token_a_address, token_b_address=token_b_address,
                     slippage=self.config.slippage)
        self.logger.info(self.get_tx_url(hex(res.transaction_hash)))
        if wait_for_tx and not self.stopped:
            self.logger.debug('Waiting for tx confirmation...')
            self.starknet_client.wait_for_pending_tx_sync(res.transaction_hash, check_interval=5)
        return hex(res.transaction_hash)
