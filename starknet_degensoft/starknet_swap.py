# -*- coding: utf-8 -*-
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

    def get_prepared_approve_tx(self, amount, token_address, trade_address=None):
        if not trade_address:
            trade_address = self._contract_address
        token_contract = Contract.from_address_sync(address=token_address, provider=self.account, proxy_config=True)
        return token_contract.functions['approve'].prepare(spender=int(trade_address, base=16), amount=amount)

    def check_balance(self, amount):
        account_balance = self.account.get_balance_sync()
        if account_balance < amount:
            raise ValueError('no such balance to swap')

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
        # todo
    }

    def swap_eth_to_token(self, amount, token_address='0x0', slippage=2.0):
        try:
            pool_id = self._token_pool_mapping[token_address]
        except KeyError:
            raise ValueError(f'no such token for myswap: {token_address}')
        self.check_balance(amount)
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


class UniswapForkBaseSwap(BaseSwap):
    _proxy_config = True
    _swap_function_name = 'swap_exact_tokens_for_tokens'
    _amounts_function_name = 'get_amounts_out'

    def swap_eth_to_token(self, amount, token_address, slippage=2.0):
        self.check_balance(amount)
        deadline = self.account.client.get_block_sync(block_number='latest').timestamp + 60 * 60  # 60 minutes
        path = [int(self.eth_contract_address, base=16), int(token_address, base=16)]
        res = self.contract.functions[self._amounts_function_name].call_sync(amountIn=amount, path=path)
        amount_out_min = int(res.amounts[1] * (1 - slippage / 100.0))
        approve_prepared_tx = self.get_prepared_approve_tx(amount=amount, token_address=self.eth_contract_address)
        swap_prepared_tx = self.contract.functions[self._swap_function_name].prepare(
            amountIn=amount,
            amountOutMin=amount_out_min,
            path=path,
            to=self.account.address,
            deadline=deadline
        )
        invoke = self.account.sign_invoke_transaction_sync(calls=[approve_prepared_tx, swap_prepared_tx],
                                                           auto_estimate=True)
        return self.account.client.send_transaction_sync(invoke)


class JediSwap(UniswapForkBaseSwap):
    _contract_address = '0x02bcc885342ebbcbcd170ae6cafa8a4bed22bb993479f49806e72d96af94c965'
    _swap_function_name = 'swap_exact_tokens_for_tokens'
    _amounts_function_name = 'get_amounts_out'


class TenKSwap(UniswapForkBaseSwap):
    _contract_address = '0x00975910cd99bc56bd289eaaa5cee6cd557f0ddafdb2ce6ebea15b158eb2c664'
    _swap_function_name = 'swapExactTokensForTokens'
    _amounts_function_name = 'getAmountsOut'
    _proxy_config = False
