import aiohttp
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.client_models import Call

from starknet_degensoft.starknet_swap import AsyncBaseSwap


class FibrousSwap(AsyncBaseSwap):
    _contract_address = '0x00f6f4CF62E3C010E0aC2451cC7807b5eEc19a40b0FaaCd00CCA3914280FDf5a'
    swap_name = 'fibrous.finance'
    _API_URL = "https://api.fibrous.finance"

    async def _get_route(self, amount: int, from_token: str, to_token: str):
        async with aiohttp.ClientSession() as session:
            params = {
                "amount": hex(amount),
                "tokenInAddress": from_token,
                "tokenOutAddress": to_token,
            }
            response = await session.get(url=self._API_URL + '/route', params=params)
            return await response.json()

    async def _get_execute_calldata(self, amount: int, from_token: str, to_token: str, slippage: float):
        async with aiohttp.ClientSession() as session:
            params = {
                "amount": hex(amount),
                "tokenInAddress": from_token,
                "tokenOutAddress": to_token,
                "slippage": slippage / 100.0,
                "destination": hex(self.account.address),
            }
            response = await session.get(url=self._API_URL + '/execute', params=params)
            data = await response.json()
            calldata = [int(i, 16) if str(i).startswith('0x') else int(i) for i in data]
            return calldata

    async def swap_async(self, amount, token_a_address, token_b_address, slippage=2.0):
        route_data = await self._get_route(amount, token_a_address, token_b_address)
        if not route_data.get('success'):
            raise RuntimeError(route_data['message'])
        approve_call = self.get_prepared_approve_tx(amount, token_a_address)
        calldata = await self._get_execute_calldata(amount, token_a_address, token_b_address, slippage)
        swap_call = Call(
            to_addr=self.contract.address,
            selector=get_selector_from_name('swap'),
            calldata=calldata,
        )
        invoke = await self.account.sign_invoke_transaction(calls=[approve_call, swap_call], auto_estimate=True)
        return await self.account.client.send_transaction(invoke)
