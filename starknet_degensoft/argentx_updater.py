import logging

from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.account.account import Account
from starknet_py.net.client_errors import ClientError
from starknet_py.net.client_models import Call
from starknet_py.utils.sync import add_sync_methods


def decode_hex_string(data):
    return bytes.fromhex(hex(data)[2:]).decode('utf-8')


@add_sync_methods
class ArgentXUpdater:
    ARGENT_CLASS_HASH = 0x33434ad846cdd5f23eb73ff09fe6fddd568284a0fb7d1be20ee482f044dabe2
    ARGENT_PROXY_CLASS_HASH = 0x25ec026985a3bf9d0cc1fe17326b245dfdc3ff89b8fde106542a3ea56c5a918
    NEW_ARGENT_CLASS_HASH = 0x1a736d6ed154502257f02b1ccdf4d9d1089f80811cd6acad48e6b6a9d1f2003

    def __init__(self, account: Account, logger=None):
        self.account = account
        self.client = self.account.client
        self.logger = logger if logger else logging.getLogger('argent_x_updater')

    async def is_argent_x_account(self):
        try:
            name = await self.client.call_contract(Call(
                to_addr=self.account.address,
                selector=get_selector_from_name('getName'),
                calldata=[]
            ))
            if decode_hex_string(name[0]) == 'ArgentAccount':
                return True
            return False
        except ClientError as ex:
            if 'StarknetErrorCode.UNINITIALIZED_CONTRACT' in ex.message:
                return False
            if 'StarknetErrorCode.ENTRY_POINT_NOT_FOUND_IN_CONTRACT' in ex.message:
                return False
            if 'Invalid message selector' in ex.message:
                return False
            if 'Contract not found' in ex.message:
                return False
            raise ex

    async def need_update(self):
        version = await self.client.call_contract(Call(
            to_addr=self.account.address,
            selector=get_selector_from_name('getVersion'),
            calldata=[]
        ))
        version = bytes.fromhex(hex(version[0])[2:]).decode('utf-8')
        # self.logger.debug(f'Account {hex(self.account.address)} version: {version}')
        if version == '0.2.3':
            self.logger.debug(f'Account {hex(self.account.address)} need update')
            return True
        else:
            self.logger.debug(f'Account {hex(self.account.address)} already updated')
            return False

    async def update(self):
        upgrade_call = Call(
            to_addr=self.account.address,
            selector=get_selector_from_name('upgrade'),
            calldata=[self.NEW_ARGENT_CLASS_HASH, 1, 0]
        )
        tx = await self.account.execute(calls=upgrade_call, auto_estimate=True)
        status = await self.client.wait_for_tx(tx.transaction_hash)
        if status.status.name in ['SUCCEEDED', 'ACCEPTED_ON_L1', 'ACCEPTED_ON_L2']:
            self.logger.info(f'Account {hex(self.account.address)} update successfull')
        else:
            self.logger.info(f'Account {hex(self.account.address)} update failed')

    async def auto_update(self):
        if await self.is_argent_x_account() and await self.need_update():
            return await self.update()
