# -*- coding: utf-8 -*-
import aiohttp
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.client_models import Call

from starknet_degensoft.starknet_swap import AsyncBaseSwap


async def get_quotes(from_token: int, to_token: int, amount: int, taker_address: int):
    async with aiohttp.ClientSession() as session:
        url = "https://starknet.api.avnu.fi/swap/v1/quotes"

        params = {
            "sellTokenAddress": hex(from_token),
            "buyTokenAddress": hex(to_token),
            "sellAmount": hex(amount),
            "takerAddress": hex(taker_address),
            "size": 3,
            "integratorName": "AVNU Portal"
        }

        response = await session.get(url=url, params=params)
        response_data = await response.json()

        quote_id = response_data[0]["quoteId"]

        return quote_id


async def build_transaction(quote_id: str, recipient: int, slippage: float):
    async with aiohttp.ClientSession() as session:
        url = "https://starknet.api.avnu.fi/swap/v1/build"

        data = {
            "quoteId": quote_id,
            "takerAddress": hex(recipient),
            "slippage": float(slippage / 100),
        }

        response = await session.post(url=url, json=data)
        response_data = await response.json()

        return response_data


class AvnuSwap(AsyncBaseSwap):
    _contract_address = '0x04270219d365d6b017231b52e92b3fb5d7c8378b05e9abc97724537a80e93b0f'
    swap_name = 'avnuswap'

    async def swap_async(self, amount, token_a_address, token_b_address, slippage=2.0):
        quote_id = await get_quotes(int(token_a_address, 16), int(token_b_address, 16), amount, self.account.address)
        transaction_data = await build_transaction(quote_id, self.account.address, slippage)
        approve_call = self.get_prepared_approve_tx(amount, token_a_address)
        calldata = [int(i, 16) for i in transaction_data["calldata"]]
        swap_call = Call(
            to_addr=self.contract.address,
            selector=get_selector_from_name(transaction_data["entrypoint"]),
            calldata=calldata,
        )
        invoke = await self.account.sign_invoke_transaction(calls=[approve_call, swap_call], auto_estimate=True)
        return await self.account.client.send_transaction(invoke)
