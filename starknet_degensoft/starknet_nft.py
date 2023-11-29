# -*- coding: utf-8 -*-
import random

from asgiref.sync import async_to_sync
from starknet_py.contract import Contract
from starknet_py.net.account.account import Account as StarknetAccount


class BaseNft:
    _contract_address = '0x0'
    _proxy_config = False

    def __init__(self, account: StarknetAccount,
                 eth_contract_address: str = '0x049d36570d4e46f48e99674bd3fcc84644ddd6b96f7c741b1562b82f9e004dc7'):
        self.account = account
        self.eth_contract_address = eth_contract_address
        self.contract = Contract.from_address_sync(address=self._contract_address, provider=self.account,
                                                   proxy_config=self._proxy_config)

    def mint(self):
        return async_to_sync(self.mint_async)()

    async def mint_async(self):
        raise NotImplementedError()


class StarknetIdNft(BaseNft):
    _contract_address = '0x05dbdedc203e92749e2e746e2d40a768d966bd243df04a6b712e222bc040a9af'
    _proxy_config = True
    project_name = 'starknet.id'

    async def mint_async(self):
        mint_call = self.contract.functions["mint"].prepare(int(random.random() * 1e12))
        invoke = await self.account.sign_invoke_transaction([mint_call], auto_estimate=True)
        return await self.account.client.send_transaction(invoke)


class StarkVerseNft(BaseNft):
    _contract_address = '0x060582df2cd4ad2c988b11fdede5c43f56a432e895df255ccd1af129160044b8'
    project_name = 'starkverse.art'

    async def mint_async(self):
        mint_call = self.contract.functions["publicMint"].prepare(self.account.address)
        invoke = await self.account.sign_invoke_transaction([mint_call], auto_estimate=True)
        return await self.account.client.send_transaction(invoke)
