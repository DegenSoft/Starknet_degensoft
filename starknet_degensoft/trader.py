# -*- coding: utf-8 -*-
import logging
import random
import time
from collections import namedtuple
from starknet_degensoft.api import Node, Account, Erc20Token, UniswapV2Exchange
from starknet_degensoft.utils import random_float

NetworkConfig = namedtuple('NetworkConfig', ('rpc', 'explorer', 'weth_address'))

Config = namedtuple('Config', ('amount', 'swaps_count', 'buy_delay', 'sell_delay', 'next_wallet_delay'))


class Trader:

    IS_DEV = False

    def __init__(self,
                 network_config: NetworkConfig,
                 config: Config,
                 private_keys: list,
                 exchanges: dict,
                 tokens: list):
        self.logger = logging.getLogger('trader')
        self.logger.setLevel(logging.DEBUG)
        self.config = config
        self.node = Node(rpc_url=network_config.rpc, weth_address=network_config.weth_address,
                         explorer_url=network_config.explorer)
        self.accounts = [Account(self.node, private_key) for private_key in private_keys]
        self.exchanges = {key: UniswapV2Exchange(self.node, key, exchanges[key]) for key in exchanges}
        self.arbswap = self.exchanges['arbswap']  # default one, todo
        self.tokens = [Erc20Token(self.node, token) for token in tokens]

    def delay(self, timeout):
        self.logger.debug(f'Delay for {timeout} sec.')
        if not self.IS_DEV:
            time.sleep(timeout)

    def random_delay(self, min_max: tuple):
        self.delay(random.randint(min_max[0], min_max[1]))

    def sell_token(self, account: Account, exchange: UniswapV2Exchange, token: Erc20Token, amount: int, delay=None):
        allowance = token.allowance(account.address, exchange.address)
        if amount > allowance:
            approve_tx_hash = token.approve(account, exchange.address, amount)
            self.logger.debug(f'Allowed {token.native_to_amount(amount)} {token.symbol} to trade on '
                              f'{exchange.address} -> {self.node.get_explorer_transaction_url(approve_tx_hash)}')
            self.logger.debug('Waiting for TX confirmation...')
            self.node.web3.eth.wait_for_transaction_receipt(approve_tx_hash)
            if delay:
                self.random_delay(delay)
            # allowance = token.allowance(account.address, exchange.address)
        tx_hash = exchange.swap_token_to_eth(account, amount, token)
        self.logger.debug(
            f'Sold {token.native_to_amount(amount)} {token.symbol} on {exchange.name.capitalize()} -> '
            f'{self.node.get_explorer_transaction_url(tx_hash)}')
        self.logger.debug('Waiting for TX confirmation...')
        tx_receipt = self.node.web3.eth.wait_for_transaction_receipt(tx_hash)
        # if tx_receipt['status'] != 1:
        #     raise Exception('Error')
        return tx_hash

    def buy_token(self, account: Account, exchange: UniswapV2Exchange, token: Erc20Token, amount: float):
        tx_hash = exchange.swap_eth_to_token(account, amount, token)
        self.logger.debug(
            f'Bought {token.symbol} for {amount} ETH on {exchange.name.capitalize()} -> '
            f'{self.node.get_explorer_transaction_url(tx_hash)}')
        self.logger.debug('Waiting for TX confirmation...')
        tx_receipt = self.node.web3.eth.wait_for_transaction_receipt(tx_hash)
        # if tx_receipt['status'] != 1:
        #     raise Exception('Error')
        return tx_hash

    def run(self):
        for i, account in enumerate(self.accounts, 1):
            self.logger.info('%s %s' % (account.address, self.node.get_explorer_address_url(account.address)))
            for j in range(random.randint(*self.config.swaps_count)):
                token = random.choice(self.tokens)
                self.logger.info(f'Swap #{j + 1}')
                amount = random_float(self.config.amount[0], self.config.amount[1], 2)
                balance = account.balance
                if account.balance < amount:
                    self.logger.error(f'Low balance: {balance} ETH')
                    break
                # buying
                try:
                    self.buy_token(account=account, exchange=self.arbswap, token=token, amount=amount)
                    self.random_delay(self.config.buy_delay)
                except Exception as ex:
                    self.logger.error(f'Error: {ex}')
                    continue
                # selling
                balance = token.balance_of(account.address)
                try:
                    self.sell_token(account=account, exchange=self.arbswap, token=token, amount=balance,
                                    delay=self.config.sell_delay)
                    self.random_delay(self.config.sell_delay)
                except Exception as ex:
                    self.logger.error(f'Error: {ex}')
            # break
            if i < len(self.accounts):
                self.random_delay(self.config.next_wallet_delay)

    def sell_all_tokens(self):
        for i, account in enumerate(self.accounts, 1):
            self.logger.info('%s -> %s' % (account.address, self.node.get_explorer_address_url(account.address)))
            for token in self.tokens:
                balance = token.balance_of(account.address)
                if balance:
                    self.logger.debug(f'Found {token.native_to_amount(balance)} {token.symbol} -> selling')
                    try:
                        self.sell_token(account=account, exchange=self.arbswap, token=token, amount=balance,
                                        delay=self.config.sell_delay)
                        self.random_delay(self.config.sell_delay)
                    except Exception as ex:
                        self.logger.error(f'Error: {ex}')
            if i < len(self.accounts):
                self.random_delay(self.config.next_wallet_delay)
