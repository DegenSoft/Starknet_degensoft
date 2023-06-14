import asyncio
from typing import List, Optional, Tuple, Union, cast

from marshmallow import EXCLUDE, ValidationError
from starknet_py.hash.selector import get_selector_from_name
from starknet_py.net.account.account import Account as BaseAccount
from starknet_py.net.client_errors import ClientError
from starknet_py.net.client_models import Call, Hash, TransactionStatus, EstimatedFee, Tag
from starknet_py.net.full_node_client import FullNodeClient as BaseFullNodeClient, \
    get_block_identifier, _create_broadcasted_txn
from starknet_py.net.gateway_client import GatewayClient as BaseGatewayClient
from starknet_py.net.models import parse_address
from starknet_py.net.models.transaction import AccountTransaction
from starknet_py.net.schemas.rpc import EstimatedFeeSchema
from starknet_py.transaction_errors import TransactionFailedError, TransactionNotReceivedError, TransactionRejectedError
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
            if 'StarknetErrorCode.UNINITIALIZED_CONTRACT' in ex.message:
                return False
            elif 'Contract not found' in ex.message:
                return False
            if 'StarknetErrorCode.ENTRY_POINT_NOT_FOUND_IN_CONTRACT' in ex.message:
                return True
            elif 'Invalid message selector' in ex.message:
                return True
            raise ex
        # return False


@add_sync_methods
class ClientMixin:

    is_stopped = False

    async def wait_for_pending_tx(
            self,
            tx_hash: Hash,
            wait_for_accept: Optional[bool] = False,
            check_interval=5,
    ) -> Tuple[int, TransactionStatus]:
        if check_interval <= 0:
            raise ValueError("Argument check_interval has to be greater than 0.")

        first_run = True
        try:
            # ugly code for JSON RPC nodes
            while True:
                if self.is_stopped:
                    return None, TransactionStatus.NOT_RECEIVED
                _attempt = 0
                while True:
                    if self.is_stopped:
                        return None, TransactionStatus.NOT_RECEIVED
                    try:
                        _attempt += 1
                        result = await self.get_transaction_receipt(tx_hash=tx_hash)
                        break
                    except ClientError as ex:
                        if ex.code == 25:# and _attempt <= 100:
                            print(f'attempt {_attempt} failed. try again in {check_interval} sec.')
                            await asyncio.sleep(check_interval)
                            continue
                        else:
                            raise ex
                    except ValidationError as ex:
                        return None, TransactionStatus.PENDING
                        # print(f'ValidationError, try again: {ex}')
                        # await asyncio.sleep(check_interval)
                        # continue
                status = result.status

                if status in (
                        TransactionStatus.ACCEPTED_ON_L1,
                        TransactionStatus.ACCEPTED_ON_L2,
                ):
                    assert result.block_number is not None
                    return result.block_number, status
                if status == TransactionStatus.PENDING:
                    if not wait_for_accept:
                        # if result.block_number is not None:
                        return result.block_number, status
                elif status == TransactionStatus.REJECTED:
                    raise TransactionRejectedError(
                        message=result.rejection_reason,
                    )
                elif status == TransactionStatus.NOT_RECEIVED:
                    if not first_run:
                        raise TransactionNotReceivedError()
                elif status != TransactionStatus.RECEIVED:
                    # This will never get executed with current possible transactions statuses
                    raise TransactionFailedError(
                        message=result.rejection_reason,
                    )

                first_run = False
                await asyncio.sleep(check_interval)
        except asyncio.CancelledError as exc:
            raise TransactionNotReceivedError from exc


@add_sync_methods
class FullNodeClient(ClientMixin, BaseFullNodeClient):
    async def estimate_fee(
            self,
            tx: AccountTransaction,
            block_hash: Optional[Union[Hash, Tag]] = None,
            block_number: Optional[Union[int, Tag]] = None,
    ) -> Union[EstimatedFee, List[EstimatedFee]]:
        block_identifier = get_block_identifier(
            block_hash=block_hash, block_number=block_number
        )

        res = await self._client.call(
            method_name="estimateFee",
            params={
                "request": _create_broadcasted_txn(transaction=tx),
                **block_identifier,
            },
        )

        return cast(
            EstimatedFee,
            EstimatedFeeSchema().load(
                res, unknown=EXCLUDE, many=False
            ),
        )


@add_sync_methods
class GatewayClient(ClientMixin, BaseGatewayClient):
    ...
