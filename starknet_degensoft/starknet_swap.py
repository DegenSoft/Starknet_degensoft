# -*- coding: utf-8 -*-
"""
2 Часть - свапы

1 - Переходим на сайт https://app.jediswap.xyz/#/swap  и делаем свап монеты ETH  в монеты USDT, USDC, DAI, WBTC в сети StarkNet

2 - Переходим на сайт https://www.myswap.xyz/#/ и делаем свап монеты ETH в  USDT, USDC, DAI, WBTC в сети StarkNet

3 -  Переходим на сайт https://10kswap.com  и делаем свап монеты ETH в USDT, USDC, DAI, WBTC в сети StarkNet


"""
from starknet_py.net.account.account import Account
from starknet_py.contract import Contract
from starknet_degensoft.utils import uniswap_v2_calculate_tokens_and_price
from web3 import Web3

class BaseSwap:
    _contract_address = '0x0'
    _proxy_config = False

    def __init__(self, account: Account, config: dict = None):
        self.account = account
        self.config = config
        self.eth_contract_address = self.config['starknet_contracts']['ETH']
        self.contract = Contract.from_address_sync(address=self._contract_address, provider=self.account,
                                                   proxy_config=self._proxy_config)

    def swap_eth_to_token(self, amount, token_address, slippage=2.0):
        raise NotImplementedError()

    def _calculate_token_b_amount(self):
        raise NotImplementedError()


class MyswapSwap(BaseSwap):
    _contract_address = '0x018a439bcbb1b3535a6145c1dc9bc6366267d923f60a84bd0c7618f33c81d334'
    _proxy_config = True
    _token_pool_mapping = {
        '0x005a643907b9a4bc6a55e9069c4fd5fd1f5c79a22470690f75556c4736e34426': 1,  # usdc
        '0x03e85bfbb8e2a42b7bead9e88e9a1b19dbccf661471061807292120462396ec9': 2,  # dai
    }

    def get_prepared_approve_tx(self, amount, token_address, trade_address=_contract_address, ):
        token_contract = Contract.from_address_sync(address=token_address, provider=self.account, proxy_config=True)
        return token_contract.functions['approve'].prepare(spender=int(trade_address, base=16), amount=amount)

    def swap_eth_to_token(self, amount, token_address='0x0', slippage=2.0):
        try:
            pool_id = self._token_pool_mapping[token_address]
        except KeyError:
            raise ValueError(f'no such token for myswap: {token_address}')
        account_balance =self.account.get_balance_sync()
        if account_balance < amount:
            raise ValueError('no such balance to swap')
        pool_data = self.contract.functions['get_pool'].call_sync(pool_id=pool_id, block_number='pending')
        amount_to = uniswap_v2_calculate_tokens_and_price(
            x=pool_data.pool['token_b_reserves'],
            y=pool_data.pool['token_a_reserves'],
            amount_x=amount,
            fee=pool_data.pool['fee_percentage'] / 1000 / 100)
        amount_to_min = int(amount_to * (1 - slippage / 100.0))
        approve_prepared_tx = self.get_prepared_approve_tx(amount=amount, token_address=self.eth_contract_address)
        swap_prepared_tx = self.contract.functions['swap'].prepare(
            pool_id=pool_id,
            token_from_addr=int(self.eth_contract_address, base=16),
            amount_from=amount,
            amount_to_min=amount_to_min
        )
        invoke = self.account.sign_invoke_transaction_sync(calls=[approve_prepared_tx, swap_prepared_tx],
                                                           auto_estimate=True)
        return self.account.client.send_transaction_sync(invoke)
