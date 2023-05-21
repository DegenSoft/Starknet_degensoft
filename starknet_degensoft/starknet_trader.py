# -*- coding: utf-8 -*-
import logging
from web3 import Web3
from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.gateway_client import GatewayClient
from starknet_py.net.models.chains import StarknetChainId
from starknet_py.net.signer.stark_curve_signer import KeyPair
from starknet_degensoft.api import Account, Node
from starknet_degensoft.starknet_swap import MyswapSwap, JediSwap, TenKSwap
from starknet_degensoft.starkgate import StarkgateBridge
from starknet_degensoft.config import Config
from starknet_degensoft.trader import BaseTrader


class StarknetTrader(BaseTrader):
    def __init__(self, config: Config, network: str = 'testnet'):
        self.config = config
        if network not in ('mainnet', 'testnet'):
            raise ValueError('bad network: %s' % network)
        self.network = network
        self.node = GatewayClient(network)
        self.logger = logging.getLogger('starknet')
        self.logger.setLevel(logging.DEBUG)

    def run(self, private_keys):
        for private_key in private_keys:
            # todo create account
            # todo: get quests and amounts
            # todo delay
            self.random_delay(self.config.delays.walet)

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
        res = s.swap_eth_to_token(amount=Web3.to_wei(amount, 'ether'), token_address=token_address)
        return hex(res.transaction_hash)
