# -*- coding: utf-8 -*-
from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.models.chains import StarknetChainId
from starknet_py.net.signer.stark_curve_signer import KeyPair
from web3 import Web3

ADDRESS = '0x01ebcf3b2baa73d0d1946ca25728cb7601462f42589bad517141ce29fbba784c'
PRIVATE_KEY = '0x0382183af99c507c16d9662c1ae18cf584574c73cdf76468b0c761520188d06c'


def test_starknet_py():
    node = GatewayClient('testnet')
    key_par = KeyPair.from_private_key(key=int(PRIVATE_KEY, base=16))
    account = StarknetAccount(
        client=node,
        address=ADDRESS,
        key_pair=key_par,
        chain=StarknetChainId.TESTNET
    )
    nonce = account.get_nonce_sync()
    balance = account.get_balance_sync()
    print(ADDRESS)
    print(f'balance={Web3.from_wei(balance, "ether")}ETH, nonce={nonce}')


if __name__ == '__main__':
    test_starknet_py()
