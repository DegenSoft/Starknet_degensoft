# -*- coding: utf-8 -*-
import math
import time
import random
import logging
from functools import cached_property
from typing import Union
import requests
from web3 import Web3
from starknet_degensoft.api import Node, Account
from starknet_degensoft.utils import random_float
from pprint import pprint


class OrbiterFinanceTrader:
    ORBITER_URL = 'https://www.orbiter.finance/'
    GITHUB_SRC_URL = 'https://raw.githubusercontent.com/Orbiter-Finance/OrbiterFE-V2/main/src/'
    ALLOWED_NETWORKS = (
        "1",  # Ethereum
        "2",  # Arbitrum
        "3",  # zkSync Lite
        "4",  # Starknet TODO
        # "6",  # Polygon TODO
        "7",  # Optimism
        # "8",  # Immutable X
        # "9",  # Loopring
        # "10",  # Metis
        # "11",  # Dydx
        # "12",  # ZKSpace
        # "13",  # Boba
        "14",  # zkSync Era
        # "15",  # BNB Chain
        # "16",  # Arbitrum Nova
        # "17",  # Polygon zkEVM
    )
    IS_DEV = False

    def __init__(self):
        self._maker_data = self._fetch_maker_data()
        self._chains_data = self._fetch_chain_data()
        self.chains = {c['internalId']: c for c in self._chains_data if c['internalId'] in self.ALLOWED_NETWORKS}
        self.logger = logging.getLogger('orbiter')
        self.logger.setLevel(logging.DEBUG)

    # def _fetch_website_data(self) -> list:
    #     html = requests.get(self.ORBITER_URL).text
    #     app_js_href = re.search('\"(static/js/app\..+?)\"', html).group(1)
    #     app_js = requests.get(self.ORBITER_URL + app_js_href).text
    #     json_strings = re.findall('JSON\.parse\(\'(.+?)\'\)', app_js, re.DOTALL)
    #     data = [json.loads(s) for s in json_strings]
    #     return data

    def _fetch_maker_data(self) -> dict:
        return random.choice((
            requests.get(self.GITHUB_SRC_URL + 'config/maker-1.json').json(),
            # requests.get(self.GITHUB_SRC_URL + 'config/maker-2.json').json()
        ))

    def _fetch_chain_data(self) -> list:
        return requests.get(self.GITHUB_SRC_URL + 'config/chain.json').json()

    @cached_property
    def networks(self):
        return {chain_id: self.chains[chain_id]['name'] for chain_id in self.chains}

    def get_transaction_cost(self, from_network_id, to_network_id, amount, symbol='ETH'):
        pass

    def get_maker_data(self, from_network_id, to_network_id, symbol):
        if from_network_id not in self.ALLOWED_NETWORKS:
            raise ValueError(f'from_network_id {from_network_id} is not supported')
        if to_network_id not in self.ALLOWED_NETWORKS:
            raise ValueError(f'to_network_id {to_network_id} is not supported')
        try:
            return self._maker_data[f'{from_network_id}-{to_network_id}'][f'{symbol}-{symbol}']
        except KeyError:
            raise ValueError(f'no such token to move: {symbol}')

    def delay(self, timeout):
        self.logger.debug(f'Delay for {timeout} sec.')
        if not self.IS_DEV:
            time.sleep(timeout)

    def random_delay(self, min_max: tuple):
        self.delay(random.randint(min_max[0], min_max[1]))

    def run(self, private_keys, next_wallet_delay, from_network_id, to_network_id,
            amount, amount_percent, amount_to_keep):
        for i, private_key in enumerate(private_keys, 1):
            random_amount = random_float(*amount, diff=2) if amount else None
            random_amount_percent = random_float(*amount_percent) if amount_percent else None
            random_amount_to_keep = random_float(*amount_to_keep) if amount_to_keep else None
            for j in range(10):
                try:
                    self.move_funds(private_key, from_network_id, to_network_id,
                                    random_amount, random_amount_percent, random_amount_to_keep)
                    break
                except RuntimeError as ex:
                    self.logger.error(ex)
                    self.logger.error('exiting, may be something is wrong')
                    return
                except Exception as ex:
                    if type(ex.args[0]) is dict and 'message' in ex.args[0]:
                        ex_message = ex.args[0]['message']
                        self.logger.error(ex_message)
                        if ex_message.startswith('err: max fee per gas less than block base fee'):
                            self.logger.info('retrying...')
                            self.random_delay(next_wallet_delay)
                            continue
                    else:
                        self.logger.error(ex)
                    break
            if i < len(private_keys):
                self.random_delay(next_wallet_delay)

    def get_explorer_url(self, network_id):
        if network_id == '2':
            return 'https://arbiscan.io/'
        return self.chains[network_id]['infoURL']

    def move_funds(self,
                   private_key: str,
                   from_network_id: str,
                   to_network_id: str,
                   amount: Union[float, int] = None,
                   amount_percent: Union[float,int] = None,
                   amount_to_keep: Union[float, int] = None,
                   symbol: str = 'ETH',
                   wait_for_income_tx: bool = True):

        maker_data = self.get_maker_data(from_network_id, to_network_id, symbol)
        trading_fee = Web3.to_wei(maker_data['tradingFee'], 'ether')
        orbiter_min_amount = Web3.to_wei(maker_data['minPrice'], 'ether')
        orbiter_max_amount = Web3.to_wei(maker_data['maxPrice'], 'ether')
        orbiter_id = 9000 + int(to_network_id)

        node = Node(rpc_url=random.choice(self.chains[from_network_id]['rpc']),
                    explorer_url=self.get_explorer_url(from_network_id))
        to_node = Node(rpc_url=random.choice(self.chains[to_network_id]['rpc']),
                       explorer_url=self.get_explorer_url(to_network_id))

        account = Account(node, private_key)
        balance = account.balance_in_wei
        self.logger.info('%s %s' % (account.address, node.get_explorer_address_url(account.address)))

        # get estimate gas and test tx for the min transfer amount
        tx = account.estimate_transfer_gas(maker_data['makerAddress'], orbiter_min_amount + trading_fee + orbiter_id)
        gas = tx['gas'] * (tx['maxFeePerGas'] + tx['maxPriorityFeePerGas'])
        self.logger.debug(f'balance={Web3.from_wei(balance, "ether")} '
                          f'min_amount={Web3.from_wei(orbiter_min_amount, "ether")}, '
                          f'trading_fee={Web3.from_wei(trading_fee, "ether")}, orbiter_id={orbiter_id}')

        max_amount = balance - trading_fee - gas
        if amount:
            amount = Web3.to_wei(amount, 'ether')
        elif amount_percent:
            if amount_percent <= 0 or amount_percent > 100:
                raise ValueError('amount_percent value must be from 0 to 100')
            amount = int(balance * amount_percent / 100.0) - (trading_fee + gas)
        elif amount_to_keep:
            amount_to_keep = Web3.to_wei(amount_to_keep, 'ether')
            if amount_to_keep > balance:
                raise ValueError('amount_to_keep exceeds available balance')
            amount = max_amount - amount_to_keep
        else:
            raise ValueError('you must set amount')

        amount = math.floor(amount / 10000) * 10000
        if amount + trading_fee + orbiter_id > balance - gas:
            amount -= 10000

        if amount < orbiter_min_amount:
            raise ValueError(f'minimum amount to bridge is {maker_data["minPrice"]} {symbol}')
        if amount > orbiter_max_amount:
            raise ValueError(f'maximum amount to bridge is {maker_data["maxPrice"]} {symbol}')
        total_amount = amount + trading_fee + orbiter_id
        self.logger.debug(f'amount={Web3.from_wei(amount, "ether")}, '
                          f'total_amount={Web3.from_wei(total_amount, "ether")}')

        if not str(total_amount).endswith(str(orbiter_id)):
            raise ValueError(f'wrong end of the amount: {total_amount}')
        if balance < total_amount + gas:
            raise ValueError(f'insufficient funds for transfer, balance = {account.balance} {symbol}')

        tx['value'] = total_amount
        signed_tx = account.sign_transaction(tx)
        to_network_first_block = to_node.block_number
        # tx = account.estimate_transfer_gas(maker_data['makerAddress'], total_amount)
        # return
        tx_hash = node.send_raw_transaction(signed_tx.rawTransaction)
        self.logger.debug(node.get_explorer_transaction_url(tx_hash))
        tx_receipt = node.web3.eth.wait_for_transaction_receipt(tx_hash)
        if wait_for_income_tx:
            self.logger.debug('Waiting for income tx...')
            tx = to_node.wait_in_transaction(maker_data['sender'], account.address, to_network_first_block)
            self.logger.debug(to_node.get_explorer_transaction_url(tx['hash']))
            if not tx:
                raise RuntimeError(f'did not get transfer in the destination network {self.chains[to_network_id]["name"]}')
        return tx_hash
