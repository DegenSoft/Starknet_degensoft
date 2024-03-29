# -*- coding: utf-8 -*-
import logging
import time
from decimal import Decimal
from typing import Union

import requests
from starknet_py.contract import Contract
from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.models import StarknetChainId
from web3 import Web3

from starknet_degensoft.api import Account
from starknet_degensoft.starknet_swap import StarknetToken


class LayerswapBridge:
    CHAIN_ID_TO_SOURCE_NETWORK = {
        5: 'ETHEREUM_GOERLI',
        42170: 'ARBITRUMNOVA_MAINNET',
        42161: 'ARBITRUM_MAINNET',
        StarknetChainId.MAINNET: 'STARKNET_MAINNET',
        StarknetChainId.TESTNET: 'STARKNET_GOERLI',
    }

    NETWORK_TO_LS_NAME = {
        'Arbitrum One': 'ARBITRUM_MAINNET',
        'Arbitrum Nova': 'ARBITRUMNOVA_MAINNET',
        'Ethereum': 'ETHEREUM_MAINNET',
        # 'Zksync Era': 'ZKSYNCERA_MAINNET',
    }

    def __init__(self, testnet=False):
        if testnet:
            self.IDENTITY_API_URL = 'https://identity-api-dev.layerswap.cloud'
            self.BRIDGE_API_URL = 'https://bridge-api-dev.layerswap.cloud'
            self.STARKNET_WATCH_CONTRACT = '0x056b277d1044208632456902079f19370e0be63b1a4745f04f96c8c652237dbc'
        else:
            self.IDENTITY_API_URL = 'https://identity-api.layerswap.io'
            self.BRIDGE_API_URL = 'https://bridge-api.layerswap.io'
            self.STARKNET_WATCH_CONTRACT = '0x05f5b269a57ec59a5fedf10f0f81cbbb7fbe005d3c9f0e0273601a122338f08a'
        self.testnet = testnet
        self.logger = logging.getLogger('starknet')

    def _get_authorization_header(self):
        data = {
            'client_id': 'layerswap_bridge_ui',
            'grant_type': 'credentialless',
        }
        r = requests.post(f'{self.IDENTITY_API_URL}/connect/token', headers={}, data=data)
        if r.status_code != 200:
            raise RuntimeError('could not get layerswap access token')
        return {'authorization': 'Bearer ' + r.json()['access_token']}

    def _get_swap_response(self, amount, from_network, to_network, from_address, to_address, auth_header):
        headers = {}
        headers.update(auth_header)

        json_data = {
            'amount': str(amount),
            'asset': 'ETH',
            # 'source_exchange': None,
            # 'source_network': from_network,
            'source': from_network,
            'source_address': from_address,
            # 'destination_network': to_network,
            'refuel': False,
            'destination': to_network,
            # 'destination_exchange': None,
            'destination_address': to_address,
            "source_asset": "ETH",
            'destination_asset': "ETH"
        }
        r = requests.post(f'{self.BRIDGE_API_URL}/api/swaps', headers=headers, json=json_data)
        return r

    def _api_swap(self, amount, from_network, to_network, from_address, to_address, auth_header):
        r = self._get_swap_response(amount, from_network, to_network, from_address, to_address, auth_header)
        if r.status_code != 200:
            raise RuntimeError(r.json())
        # print("api_swap", r.text)
        swap_id = r.json()['data']['swap_id']
        return swap_id

    def _get_swap_status(self, swap_id, auth_header):
        r = requests.get(f'{self.BRIDGE_API_URL}/api/swaps/{swap_id}', headers=auth_header)
        # print("get_swap_status", r.text)
        if r.status_code != 200:
            raise RuntimeError(r.json())
        return r.json()

    def _get_deposit_address(self, swap_id, auth_header, is_starknet):  # todo
        swap_data = self._get_swap_status(swap_id, auth_header)
        from_network = swap_data['data']['source_network']
        if not is_starknet:
            rd = requests.post(f'{self.BRIDGE_API_URL}/api/deposit_addresses/{from_network}', headers=auth_header)
        else:
            # hardcoded starknet deposit contract address (only for mainnet)
            return '0x19252b1deef483477c4d30cfcc3e5ed9c82fafea44669c182a45a01b4fdb97a'
            # rd = requests.get(f'{self.BRIDGE_API_URL}/api/deposit_addresses/{from_network}',
            #                   params={'source': 1},
            #                   headers=auth_header)
        # print("get_depo_address", rd.text)
        rd_data = rd.json()
        if rd_data['error']:
            raise RuntimeError(rd_data)
        return rd_data['data']['address']

    def get_deposit_amount_limits(self, from_network, to_network, auth_header=None):
        if not auth_header:
            auth_header = self._get_authorization_header()
        json_data = {
            'asset': 'ETH',
            'source': from_network,
            'destination': to_network,
            'refuel': False,
            "source_asset": "ETH",
            'destination_asset': "ETH"
        }
        r = requests.post(f'{self.BRIDGE_API_URL}/api/swaps/quote', headers=auth_header, json=json_data)
        # print("get_depo_amount_limits", r.text)
        response_data = r.json()
        if response_data['error']:
            raise RuntimeError(response_data)
        return response_data['data'][0]

    def deposit(
            self, account: Union[Account, StarknetAccount],
            amount: Union[float, Decimal],
            to_l2_address: str,
            to_network=None,
            wait_for_tx=False,
            wait_for_income_tx=False
    ):
        if type(account) == Account:
            chain_id = account.web3.eth.chain_id
            balance = account.balance
            is_starknet = False
            from_address = account.address
        else:
            chain_id = account._chain_id
            balance = account.get_balance_sync()
            is_starknet = True
            from_address = hex(account.address)
        try:
            from_network = self.CHAIN_ID_TO_SOURCE_NETWORK[chain_id]
        except KeyError:
            raise ValueError(f'bad source network with chain_id={chain_id}')

        if not to_network:
            to_network = 'STARKNET_MAINNET' if not self.testnet else 'STARKNET_GOERLI'
        else:
            to_network = self.NETWORK_TO_LS_NAME.get(to_network, to_network)
        auth_header = self._get_authorization_header()
        deposit_data = self.get_deposit_amount_limits(from_network, to_network, auth_header)
        if amount < deposit_data['min_amount']:
            raise ValueError(f'amount must be greater then {deposit_data["MinAmount"]} ETH')
        elif amount > deposit_data['max_amount']:
            raise ValueError(f'amount must be less then {deposit_data["MaxAmount"]} ETH')
        if balance < amount:
            raise ValueError(f'insufficient funds for transfer, balance={balance} ETH, amount={amount} ETH')
        swap_id = self._api_swap(from_network=from_network, to_network=to_network, amount=amount,
                                 from_address=from_address, to_address=to_l2_address, auth_header=auth_header)
        self.logger.debug(f'https://{"testnet." if self.testnet else ""}layerswap.io/swap/{swap_id}')
        # swap_status = self._get_swap_status(swap_id=swap_id, auth_header=auth_header)
        deposit_address = self._get_deposit_address(swap_id, auth_header=auth_header, is_starknet=is_starknet)
        if type(account) == Account:
            tx_hash = account.transfer(to_address=deposit_address, amount=Web3.to_wei(amount, 'ether'))
            if wait_for_tx:
                tx_receipt = account.web3.eth.wait_for_transaction_receipt(tx_hash)
        else:
            sequence_number = self._get_swap_status(swap_id, auth_header)['data']['sequence_number']
            tx = self._transfer_starknet(account=account, to_address=deposit_address,
                                         amount=amount, sequence_number=sequence_number)
            tx_hash = hex(tx.transaction_hash)
            if wait_for_tx:
                account.client.wait_for_tx_sync(tx.transaction_hash, check_interval=5, wait_for_accept=False)
        if wait_for_income_tx:
            while True:
                swap_data = self._get_swap_status(swap_id, auth_header)
                print(swap_data)
                if swap_data['data']['status'] == 'completed':
                    break
                time.sleep(5)
        return tx_hash

    def _get_transfer_starknet_invoke(self, account: StarknetAccount, to_address, amount, sequence_number):
        amount = Web3.to_wei(amount, 'ether')
        watch_contract = Contract.from_address_sync(address=self.STARKNET_WATCH_CONTRACT, provider=account.client)
        watch_call = watch_contract.functions['watch'].prepare(_Id=sequence_number)
        eth_token = StarknetToken(token_address=account._default_token_address_for_chain(), account=account)
        transfer_call = eth_token.prepare_transfer_tx(amount=amount, to_address=to_address)
        calls = [transfer_call, watch_call]
        return account.sign_invoke_transaction_sync(calls=calls, auto_estimate=True)

    def _transfer_starknet(self, account: StarknetAccount, to_address, amount, sequence_number):
        invoke = self._get_transfer_starknet_invoke(account, to_address, amount, sequence_number)
        tx = account.client.send_transaction_sync(invoke)
        return tx

    def get_starknet_transfer_fee(self, account, address):
        # hack to get transfer fee
        invoke = self._get_transfer_starknet_invoke(account, address,
                                                    amount=0.00001, sequence_number=100)
        return invoke.max_fee
