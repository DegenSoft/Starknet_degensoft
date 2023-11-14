# -*- coding: utf-8 -*-
from asgiref.sync import async_to_sync

from starknet_degensoft.starknet_swap import BaseSwap


class SithSwap(BaseSwap):
    _contract_address = '0x028c858a586fa12123a1ccb337a0a3b369281f91ea00544d0c086524b759f627'
    swap_name = 'sithswap'

    async def get_min_amount_out(self, amount: int, slippage: float, path: list):
        min_amount_out_data = await self.contract.functions["getAmountOut"].prepare(
            amount,
            path[0],
            path[1]
        ).call()

        min_amount_out = min_amount_out_data.amount
        stable = min_amount_out_data.stable

        return int(min_amount_out - (min_amount_out / 100 * slippage)), stable

    def swap(self, amount, token_a_address, token_b_address, slippage=2.0):
        return async_to_sync(self.swap_async)(amount, token_a_address, token_b_address, slippage)

    async def swap_async(self, amount, token_a_address, token_b_address, slippage=2.0):
        path = [int(token_a_address, 16), int(token_b_address, 16)]
        deadline = (await self.account.client.get_block(block_number='latest')).timestamp + 60 * 60  # 60 minutes
        min_amount_out, stable = await self.get_min_amount_out(amount, slippage, path)
        route = [{'from_address': path[0], 'to_address': path[1], 'stable': stable}]
        approve_call = self.get_prepared_approve_tx(amount, token_a_address)
        swap_call = self.contract.functions['swapExactTokensForTokens'].prepare(
            amount_in=amount,
            amount_out_min=min_amount_out,
            routes=route,
            to=self.account.address,
            deadline=deadline
        )
        invoke = await self.account.sign_invoke_transaction(calls=[approve_call, swap_call], auto_estimate=True)
        return await self.account.client.send_transaction(invoke)
