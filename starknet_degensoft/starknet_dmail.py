# -*- coding: utf-8 -*-
import random
from hashlib import sha256

from starknet_degensoft.starknet_nft import BaseNft


class BaseDapp(BaseNft):
    ...


class StarknetDmail(BaseDapp):
    project_name = 'DMail'
    _contract_address = '0x0454f0bd015e730e5adbb4f080b075fdbf55654ff41ee336203aa2e1ac4d4309'

    async def mint_async(self):
        email_address = sha256(str(1e10 * random.random()).encode()).hexdigest()
        theme = sha256(str(1e10 * random.random()).encode()).hexdigest()
        dmail_call = self.contract.functions['transaction'].prepare(email_address[0:31], theme[0:31])
        invoke = await self.account.sign_invoke_transaction([dmail_call], auto_estimate=True)
        return await self.account.client.send_transaction(invoke)
