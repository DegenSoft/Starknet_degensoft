# -*- coding: utf-8 -*-
from functools import cached_property

from starknet_py.contract import Contract
from starknet_py.net.account.account import Account as StarknetAccount

from starknet_degensoft.utils import uniswap_v2_calculate_tokens_and_price

ERC20_ABI = [{'members': [{'name': 'low', 'offset': 0, 'type': 'felt'}, {'name': 'high', 'offset': 1, 'type': 'felt'}],
              'name': 'Uint256', 'size': 2, 'type': 'struct'},
             {'inputs': [], 'name': 'name', 'outputs': [{'name': 'name', 'type': 'felt'}], 'stateMutability': 'view',
              'type': 'function'}, {'inputs': [], 'name': 'symbol', 'outputs': [{'name': 'symbol', 'type': 'felt'}],
                                    'stateMutability': 'view', 'type': 'function'},
             {'inputs': [], 'name': 'totalSupply', 'outputs': [{'name': 'totalSupply', 'type': 'Uint256'}],
              'stateMutability': 'view', 'type': 'function'},
             {'inputs': [], 'name': 'decimals', 'outputs': [{'name': 'decimals', 'type': 'felt'}],
              'stateMutability': 'view', 'type': 'function'},
             {'inputs': [{'name': 'account', 'type': 'felt'}], 'name': 'balanceOf',
              'outputs': [{'name': 'balance', 'type': 'Uint256'}], 'stateMutability': 'view', 'type': 'function'},
             {'inputs': [{'name': 'owner', 'type': 'felt'}, {'name': 'spender', 'type': 'felt'}], 'name': 'allowance',
              'outputs': [{'name': 'remaining', 'type': 'Uint256'}], 'stateMutability': 'view', 'type': 'function'},
             {'inputs': [], 'name': 'permittedMinter', 'outputs': [{'name': 'minter', 'type': 'felt'}],
              'stateMutability': 'view', 'type': 'function'}, {
                 'inputs': [{'name': 'name', 'type': 'felt'}, {'name': 'symbol', 'type': 'felt'},
                            {'name': 'decimals', 'type': 'felt'}, {'name': 'minter_address', 'type': 'felt'}],
                 'name': 'constructor', 'outputs': [], 'type': 'constructor'},
             {'inputs': [{'name': 'recipient', 'type': 'felt'}, {'name': 'amount', 'type': 'Uint256'}],
              'name': 'transfer', 'outputs': [{'name': 'success', 'type': 'felt'}], 'type': 'function'}, {
                 'inputs': [{'name': 'sender', 'type': 'felt'}, {'name': 'recipient', 'type': 'felt'},
                            {'name': 'amount', 'type': 'Uint256'}], 'name': 'transferFrom',
                 'outputs': [{'name': 'success', 'type': 'felt'}], 'type': 'function'},
             {'inputs': [{'name': 'spender', 'type': 'felt'}, {'name': 'amount', 'type': 'Uint256'}], 'name': 'approve',
              'outputs': [{'name': 'success', 'type': 'felt'}], 'type': 'function'},
             {'inputs': [{'name': 'spender', 'type': 'felt'}, {'name': 'added_value', 'type': 'Uint256'}],
              'name': 'increaseAllowance', 'outputs': [{'name': 'success', 'type': 'felt'}], 'type': 'function'},
             {'inputs': [{'name': 'spender', 'type': 'felt'}, {'name': 'subtracted_value', 'type': 'Uint256'}],
              'name': 'decreaseAllowance', 'outputs': [{'name': 'success', 'type': 'felt'}], 'type': 'function'},
             {'inputs': [{'name': 'recipient', 'type': 'felt'}, {'name': 'amount', 'type': 'Uint256'}],
              'name': 'permissionedMint', 'outputs': [], 'type': 'function'},
             {'inputs': [{'name': 'account', 'type': 'felt'}, {'name': 'amount', 'type': 'Uint256'}],
              'name': 'permissionedBurn', 'outputs': [], 'type': 'function'}]


class StarknetToken:
    def __init__(self, token_address, account):
        # try:
        #     self.contract = Contract.from_address_sync(address=token_address, provider=account, proxy_config=True)
        # except ProxyResolutionError:
        #     self.contract = Contract.from_address_sync(address=token_address, provider=account, proxy_config=False)
        self.contract = Contract(address=token_address, abi=ERC20_ABI, provider=account)

    def prepare_approve_tx(self, amount, trade_address):
        return self.contract.functions['approve'].prepare(spender=int(trade_address, base=16), amount=amount)

    @property
    def address(self):
        return self.contract.address

    @cached_property
    def symbol(self):
        int_repr = self.contract.functions['symbol'].call_sync()[0]
        return bytes.fromhex(hex(int_repr).replace('0x', '')).decode('utf8')

    @cached_property
    def decimals(self):
        return self.contract.functions['decimals'].call_sync()[0]

    def to_native(self, amount):
        return int(amount * 10 ** self.decimals)

    def from_native(self, native_amount):
        return native_amount / 10 ** self.decimals

    def balance(self):
        return self.contract.functions['balanceOf'].call_sync(self.contract.account.address)[0]


class BaseSwap:
    _contract_address = '0x0'
    _proxy_config = False

    def __init__(self, account: StarknetAccount, eth_contract_address: str, testnet: bool = False):
        self.account = account
        self.testnet = testnet
        self.eth_contract_address = eth_contract_address
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
    _proxy_config = True
    swap_name = 'myswap'

    @property
    def _contract_address(self):
        if self.testnet:
            return '0x018a439bcbb1b3535a6145c1dc9bc6366267d923f60a84bd0c7618f33c81d334'
        else:
            return '0x010884171baf1914edc28d7afb619b40a4051cfae78a094a55d230f19e944a28'  # mainnet

    @property
    def _token_pool_mapping(self):
        if self.testnet:
            return {
                '0x005a643907b9a4bc6a55e9069c4fd5fd1f5c79a22470690f75556c4736e34426': 1,  # usdc
                '0x03e85bfbb8e2a42b7bead9e88e9a1b19dbccf661471061807292120462396ec9': 2,  # dai
            }
        else:
            return {
                '0x068f5c6a61780768455de69077e07e89787839bf8166decfbf92b645209c0fb8': 4,  # usdt
                '0x053c91253bc9682c04929ca02ed00b3e423f6710d2ee7e0d5ebb06f3ecf368a8': 1,  # usdc
                '0x00da114221cb83fa859dbdb4c44beeaa0bb37c7537ad5ae66fe5e0efd20e6eb3': 2,  # dai
                # '0x03fe2b97c1fd336e750087d68b9b867997fd64a2661ff3ca5a7c771641e8e7ac': None,  # wbtc not a valid pool
            }

    def swap(self, amount, token_a_address, token_b_address, slippage=2.0):
        if token_a_address in self._token_pool_mapping:
            pool_id = self._token_pool_mapping[token_a_address]
        elif token_b_address in self._token_pool_mapping:
            pool_id = self._token_pool_mapping[token_b_address]
        else:
            raise ValueError(f'no such token for myswap')
        token = StarknetToken(token_address=token_a_address, account=self.account)
        token_balance = token.balance()
        if token_balance < amount:
            raise ValueError('no such balance for swap')
        pool_data = self.contract.functions['get_pool'].call_sync(pool_id=pool_id, block_number='pending')
        if pool_data.pool['token_a_address'] == token.address:
            token_a_reserves = pool_data.pool['token_a_reserves']
            token_b_reserves = pool_data.pool['token_b_reserves']
        else:
            token_a_reserves = pool_data.pool['token_b_reserves']
            token_b_reserves = pool_data.pool['token_a_reserves']
        amount_to = uniswap_v2_calculate_tokens_and_price(
            x=token_a_reserves,
            y=token_b_reserves,
            amount_x=amount,
            fee=pool_data.pool['fee_percentage'] / 1000 / 100)
        amount_to_min = int(amount_to * (1 - slippage / 100.0))
        approve_prepared_tx = token.prepare_approve_tx(amount=amount, trade_address=self._contract_address)
        swap_prepared_tx = self.contract.functions['swap'].prepare(
            pool_id=pool_id,
            token_from_addr=token.address,
            amount_from=amount,
            amount_to_min=amount_to_min
        )
        calls = [approve_prepared_tx, swap_prepared_tx]
        invoke = self.account.sign_invoke_transaction_sync(calls=calls, auto_estimate=True)
        return self.account.client.send_transaction_sync(invoke)

    # def swap_eth_to_token(self, amount, token_address='0x0', slippage=2.0):
    #     try:
    #         pool_id = self._token_pool_mapping[token_address]
    #     except KeyError:
    #         raise ValueError(f'no such token for myswap: {token_address}')
    #     self.check_balance(amount)
    #     pool_data = self.contract.functions['get_pool'].call_sync(pool_id=pool_id, block_number='pending')
    #     # print(pool_data)
    #     amount_to = uniswap_v2_calculate_tokens_and_price(
    #         x=pool_data.pool['token_b_reserves'],
    #         y=pool_data.pool['token_a_reserves'],
    #         amount_x=amount,
    #         fee=pool_data.pool['fee_percentage'] / 1000 / 100)
    #     amount_to_min = int(amount_to * (1 - slippage / 100.0))
    #     # print(amount_to, amount_to_min)
    #     approve_prepared_tx = self.get_prepared_approve_tx(amount=amount, token_address=self.eth_contract_address)
    #     swap_prepared_tx = self.contract.functions['swap'].prepare(
    #         pool_id=pool_id,
    #         token_from_addr=int(self.eth_contract_address, base=16),
    #         amount_from=amount,
    #         amount_to_min=amount_to_min
    #     )
    #     calls = [approve_prepared_tx, swap_prepared_tx]
    #     invoke = self.account.sign_invoke_transaction_sync(calls=calls, auto_estimate=True)
    #     return self.account.client.send_transaction_sync(invoke)

    def swap_eth_to_token(self, amount, token_address='0x0', slippage=2.0):
        return self.swap(amount=amount,
                         token_a_address=self.eth_contract_address,
                         token_b_address=token_address,
                         slippage=slippage)

    def swap_token_to_eth(self, amount, token_address, slippage=2.0):
        return self.swap(amount=amount,
                         token_a_address=token_address,
                         token_b_address=self.eth_contract_address,
                         slippage=slippage)


class UniswapForkBaseSwap(BaseSwap):
    _proxy_config = True
    _swap_function_name = 'swap_exact_tokens_for_tokens'
    _amounts_function_name = 'get_amounts_out'

    def swap_eth_to_token(self, amount, token_address, slippage=2.0):
        return self.swap(amount=amount, token_a_address=self.eth_contract_address,
                         token_b_address=token_address, slippage=slippage)
        # self.check_balance(amount)
        # deadline = self.account.client.get_block_sync(block_number='latest').timestamp + 60 * 60  # 60 minutes
        # path = [int(self.eth_contract_address, base=16), int(token_address, base=16)]
        # res = self.contract.functions[self._amounts_function_name].call_sync(amountIn=amount, path=path)
        # amount_out_min = int(res.amounts[1] * (1 - slippage / 100.0))
        # approve_prepared_tx = self.get_prepared_approve_tx(amount=amount, token_address=self.eth_contract_address)
        # swap_prepared_tx = self.contract.functions[self._swap_function_name].prepare(
        #     amountIn=amount,
        #     amountOutMin=amount_out_min,
        #     path=path,
        #     to=self.account.address,
        #     deadline=deadline
        # )
        # calls = [approve_prepared_tx, swap_prepared_tx]
        # invoke = self.account.sign_invoke_transaction_sync(calls=calls, auto_estimate=True)
        # return self.account.client.send_transaction_sync(invoke)

    def swap(self, amount, token_a_address, token_b_address, slippage=2.0):
        deadline = self.account.client.get_block_sync(block_number='latest').timestamp + 60 * 60  # 60 minutes
        token = StarknetToken(token_address=token_a_address, account=self.account)
        token_balance = token.balance()
        if token_balance < amount:
            raise ValueError('no such balance for swap')
        path = [int(token_a_address, base=16), int(token_b_address, base=16)]
        res = self.contract.functions[self._amounts_function_name].call_sync(amountIn=amount, path=path)
        amount_out_min = int(res.amounts[1] * (1 - slippage / 100.0))
        approve_prepared_tx = token.prepare_approve_tx(amount=amount, trade_address=self._contract_address)
        swap_prepared_tx = self.contract.functions[self._swap_function_name].prepare(
            amountIn=amount,
            amountOutMin=amount_out_min,
            path=path,
            to=self.account.address,
            deadline=deadline
        )
        calls = [approve_prepared_tx, swap_prepared_tx]
        invoke = self.account.sign_invoke_transaction_sync(calls=calls, auto_estimate=True)
        return self.account.client.send_transaction_sync(invoke)

    def swap_token_to_eth(self, amount, token_address, slippage=2.0):
        return self.swap(amount=amount, token_a_address=token_address,
                         token_b_address=self.eth_contract_address, slippage=slippage)


class JediSwap(UniswapForkBaseSwap):

    _swap_function_name = 'swap_exact_tokens_for_tokens'
    _amounts_function_name = 'get_amounts_out'
    swap_name = 'jediswap'

    @property
    def _contract_address(self):
        return '0x02bcc885342ebbcbcd170ae6cafa8a4bed22bb993479f49806e72d96af94c965' if self.testnet else \
            '0x041fd22b238fa21cfcf5dd45a8548974d8263b3a531a60388411c5e230f97023'


class TenKSwap(UniswapForkBaseSwap):
    # _contract_address = '0x00975910cd99bc56bd289eaaa5cee6cd557f0ddafdb2ce6ebea15b158eb2c664'
    _swap_function_name = 'swapExactTokensForTokens'
    _amounts_function_name = 'getAmountsOut'
    _proxy_config = False
    swap_name = '10kswap'

    @property
    def _contract_address(self):
        return '0x00975910cd99bc56bd289eaaa5cee6cd557f0ddafdb2ce6ebea15b158eb2c664' if self.testnet else \
            '0x7a6f98c03379b9513ca84cca1373ff452a7462a3b61598f0af5bb27ad7f76d1'
