from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.account.account import Account as BaseAccount
from starknet_py.net.client_errors import ClientError
from starknet_py.net.client_models import Call
from starknet_py.net.full_node_client import FullNodeClient as BaseFullNodeClient
from starknet_py.net.gateway_client import GatewayClient as BaseGatewayClient
from starknet_py.net.models import parse_address
from starknet_py.utils.sync import add_sync_methods

is_stopped = False


@add_sync_methods
class Account(BaseAccount):
    async def is_deployed(self):
        try:
            await self._client.call_contract(Call(
                to_addr=parse_address(self.address),
                # selector=get_selector_from_name('test_call_to_something'),
                selector=get_selector_from_name('get_impl_version'),
                calldata=[]
            ))
            return True
        except ClientError as ex:
            if 'StarknetErrorCode.UNINITIALIZED_CONTRACT' in ex.message or \
                    'Contract not found' in ex.message:
                return False
            return True
        # return False


@add_sync_methods
class FullNodeClient(BaseFullNodeClient):
    ...


@add_sync_methods
class GatewayClient(BaseGatewayClient):
    ...
