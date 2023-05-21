# -*- coding: utf-8 -*-
import requests
from starknet_degensoft.api import Account, Node
from starknet_degensoft.utils import load_lines
from starknet_degensoft.config import Config
from web3 import Web3
import random
import requests


class LayerswapBridge:
    CHAIN_ID_TO_SOURCE_NETWORK = {
        5: 'ETHEREUM_GOERLI',
        42170: 'ARBITRUMNOVA_MAINNET',
        42161: 'ARBITRUM_MAINNET',
    }

    def __init__(self, testnet=False):
        if testnet:
            self.IDENTITY_API_URL = 'https://identity-api-dev.layerswap.cloud'
            self.BRIDGE_API_URL = 'https://bridge-api-dev.layerswap.cloud'
        else:
            self.IDENTITY_API_URL = 'https://identity-api.layerswap.io'
            self.BRIDGE_API_URL = 'https://bridge-api.layerswap.cloud'
        self.testnet = testnet

    def _get_authorization_header(self):
        data = {
            'client_id': 'layerswap_bridge_ui',
            'grant_type': 'credentialless',
        }
        r = requests.post(f'{self.IDENTITY_API_URL}/connect/token', headers={}, data=data)
        if r.status_code != 200:
            raise RuntimeError('could not get layerswap access token')
        return {'authorization': 'Bearer ' + r.json()['access_token']}

    def _api_swap(self, amount, from_network, to_network, to_address, auth_header):
        headers = {}
        headers.update(auth_header)

        json_data = {
            'amount': amount,
            'source_exchange': None,
            'source_network': from_network,
            'destination_network': to_network,
            'destination_exchange': None,
            'asset': 'ETH',
            'destination_address': to_address,
            'refuel': False,
        }

        r = requests.post(f'{self.BRIDGE_API_URL}/api/swaps', headers=headers, json=json_data)
        if r.status_code != 200:
            raise RuntimeError(r.json())
        swap_id = r.json()['data']['swap_id']
        return swap_id

    def _get_deposit_address(self, swap_id, auth_header):
        r = requests.get(f'{self.BRIDGE_API_URL}/api/swaps/{swap_id}', headers=auth_header)
        if r.status_code != 200:
            raise RuntimeError(r.json())
        data = r.json()
        from_network = data['data']['source_network']
        rd = requests.get(f'{self.BRIDGE_API_URL}/api/deposit_addresses/{from_network}',
                          params={'source': 0}, headers=auth_header)
        rd_data = rd.json()
        if rd_data['error']:
            raise RuntimeError(rd_data)
        return rd_data['data']['address']

    def deposit(self, account: Account, amount: float, to_l2_address: str):
        chain_id = account.web3.eth.chain_id
        try:
            from_network = self.CHAIN_ID_TO_SOURCE_NETWORK[chain_id]
        except KeyError:
            raise ValueError(f'bad source network with chain_id={chain_id}')
        auth_header = self._get_authorization_header()
        to_network = 'STARKNET_MAINNET' if not self.testnet else 'STARKNET_GOERLI'
        swap_id = self._api_swap(from_network=from_network, to_network=to_network, amount=amount,
                                 to_address=to_l2_address, auth_header=auth_header)
        print(f'https://testnet.layerswap.io/swap/{swap_id}')
        deposit_address = self._get_deposit_address(swap_id, auth_header=auth_header)
        tx_hash = account.transfer(to_address=deposit_address, amount=Web3.to_wei(amount, 'ether'))
        tx_receipt = account.web3.eth.wait_for_transaction_receipt(tx_hash)
        print(account.node.get_explorer_transaction_url(tx_hash))
        return tx_hash


def layerswap_test():
    config = Config()
    config.load('../config.json')
    private_key = load_lines('../private_keys.txt').pop()
    network = 'ethereum_goerli'
    n = Node(rpc_url=random.choice(config.data['networks'][network]['rpc']),
             explorer_url=config.data['networks'][network]['explorer'])
    a = Account(node=n, private_key=private_key)
    print(n.get_explorer_address_url(a.address))
    ls = LayerswapBridge(testnet=True)
    # print(ls._get_access_token())
    ls.deposit(account=a, amount=0.01,
               to_l2_address='0x01ebcf3b2baa73d0d1946ca25728cb7601462f42589bad517141ce29fbba784c')


if __name__ == '__main__':
    layerswap_test()
