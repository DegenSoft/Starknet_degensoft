# -*- coding: utf-8 -*-
import logging
import time
from decimal import Decimal
from typing import Union
import asyncio
import requests
from starknet_py.contract import Contract
from starknet_py.net.account.account import Account as StarknetAccount
from starknet_py.net.models import StarknetChainId
from web3 import Web3

from starknet_degensoft.api import Account
from starknet_degensoft.starknet_swap import StarknetToken


class LayerswapBridge:
    CHAIN_ID_TO_SOURCE_NETWORK = {
        5: "ETHEREUM_GOERLI",
        42170: "ARBITRUMNOVA_MAINNET",
        42161: "ARBITRUM_MAINNET",
        StarknetChainId.MAINNET: "STARKNET_MAINNET",
        StarknetChainId.GOERLI: "STARKNET_GOERLI",
    }

    NETWORK_TO_LS_NAME = {
        "Arbitrum One": "ARBITRUM_MAINNET",
        "Arbitrum Nova": "ARBITRUMNOVA_MAINNET",
        "Ethereum": "ETHEREUM_MAINNET",
        # 'Zksync Era': 'ZKSYNCERA_MAINNET',
    }

    STARKNET_WATCH_CONTRACT = (
        "0x022993789c33e54e0d296fc266a9c9a2e9dcabe2e48941f5fa1bd5692ac4a8c4"
    )

    def __init__(self, api_key, testnet=False):
        self.LS_API_URL = "https://api.layerswap.io/api/v2/swaps"
        self.testnet = testnet
        self.api_key = api_key
        if not self.api_key:
            raise ValueError("API key is required for Layerswap Bridge")
        self.logger = logging.getLogger("starknet")

    def _get_authorization_header(self):
        data = {
            "accept": "application/json",
            "content-type": "application/json",
            "X-LS-APIKEY": self.api_key,
        }

        return data

    def _get_swap_response(
        self, amount, from_network, to_network, from_address, to_address, auth_header
    ):
        headers = {}
        headers.update(auth_header)

        json_data = {
            "destination_address": to_address,
            "source_network": from_network,
            "source_token": "ETH",
            "destination_network": to_network,
            "destination_token": "ETH",
            "refuel": False,
            "use_deposit_address": False,
            "amount": str(amount),
        }
        r = requests.post(self.LS_API_URL, headers=headers, json=json_data)
        return r

    def _api_swap(
        self, amount, from_network, to_network, from_address, to_address, auth_header
    ):
        r = self._get_swap_response(
            amount, from_network, to_network, from_address, to_address, auth_header
        )
        if r.status_code != 200:
            print(r)
            raise RuntimeError(r.json())
        # print("api_swap", r.text)
        swap_id: str = r.json()["data"]["swap"]["id"]
        deposit_address: str = r.json()["data"]["deposit_actions"][0]["to_address"]
        return swap_id, deposit_address

    def _get_swap_status(self, swap_id, auth_header):
        r = requests.get(f"{self.LS_API_URL}/{swap_id}", headers=auth_header)
        # print("get_swap_status", r.text)
        if r.status_code != 200:
            raise RuntimeError(r.json())
        return r.json()

    def get_deposit_amount_limits(self, from_network, to_network, auth_header=None):
        if not auth_header:
            auth_header = self._get_authorization_header()
        r = requests.get(
            f"https://api.layerswap.io/api/v2/quote?source_network={from_network}&source_token=ETH&destination_network={to_network}&destination_token=ETH&amount={0.001}",
            headers=auth_header,
        )
        # print("get_depo_amount_limits", r.text)

        response_data = r.json()
        print(response_data)
        if response_data["error"]:
            print(response_data)
            raise RuntimeError(response_data)
        return response_data["data"][0]

    def deposit(
        self,
        account: Union[Account, StarknetAccount],
        amount: Union[float, Decimal],
        to_l2_address: str,
        to_network=None,
        wait_for_tx=False,
        wait_for_income_tx=False,
    ):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            self.deposit_async(
                account=account,
                amount=amount,
                to_l2_address=to_l2_address,
                to_network=to_network,
                wait_for_tx=wait_for_tx,
                wait_for_income_tx=wait_for_income_tx,
            )
        )
        return result

    async def deposit_async(
        self,
        account: Union[Account, StarknetAccount],
        amount: Union[float, Decimal],
        to_l2_address: str,
        to_network=None,
        wait_for_tx=False,
        wait_for_income_tx=False,
    ):
        if type(account) == Account:
            chain_id = account.web3.eth.chain_id
            balance = account.balance
            is_starknet = False
            from_address = account.address
        else:
            chain_id = account._chain_id
            balance = await account.get_balance()
            is_starknet = True
            from_address = hex(account.address)
        try:
            from_network = self.CHAIN_ID_TO_SOURCE_NETWORK[chain_id]
        except KeyError:
            raise ValueError(f"bad source network with chain_id={chain_id}")

        if not to_network:
            to_network = "STARKNET_MAINNET" if not self.testnet else "STARKNET_GOERLI"
        else:
            to_network = self.NETWORK_TO_LS_NAME.get(to_network, to_network)
        auth_header = self._get_authorization_header()
        if balance < amount:
            raise ValueError(
                f"insufficient funds for transfer, balance={balance} ETH, amount={amount} ETH"
            )
        swap_id, deposit_address = self._api_swap(
            from_network=from_network,
            to_network=to_network,
            amount=amount,
            from_address=from_address,
            to_address=to_l2_address,
            auth_header=auth_header,
        )
        self.logger.debug(
            f'https://{"testnet." if self.testnet else ""}layerswap.io/swap/{swap_id}'
        )
        # swap_status = self._get_swap_status(swap_id=swap_id, auth_header=auth_header)
        if type(account) == Account:
            tx_hash = account.transfer(
                to_address=deposit_address, amount=Web3.to_wei(amount, "ether")
            )
            if wait_for_tx:
                tx_receipt = account.web3.eth.wait_for_transaction_receipt(tx_hash)
        else:
            sequence_number = self._get_swap_status(swap_id, auth_header)["data"]["swap"]["metadata"][
                "sequence_number"
            ]
            tx = await self._transfer_starknet(
                account=account,
                to_address=deposit_address,
                amount=amount,
                sequence_number=sequence_number,
            )
            tx_hash = hex(tx.transaction_hash)
            if wait_for_tx:
                await account.client.wait_for_tx(
                    tx.transaction_hash, check_interval=5, wait_for_accept=False
                )
        if wait_for_income_tx:
            while True:
                swap_data = self._get_swap_status(swap_id, auth_header)
                print(swap_data)
                if swap_data["data"]["status"] == "completed":
                    break
                time.sleep(5)
        return tx_hash

    async def _get_transfer_starknet_invoke(
        self, account: StarknetAccount, to_address, amount, sequence_number
    ):
        amount = Web3.to_wei(amount, "ether")
        watch_contract = await Contract.from_address(
            address=self.STARKNET_WATCH_CONTRACT, provider=account.client
        )
        watch_call = watch_contract.functions["watch"].prepare_call(_Id=sequence_number)
        eth_token = StarknetToken(
            token_address=account._default_token_address_for_chain(), account=account
        )
        transfer_call = eth_token.prepare_transfer_tx(
            amount=amount, to_address=to_address
        )
        calls = [transfer_call, watch_call]
        return await account.sign_invoke_v1(calls=calls, auto_estimate=True)

    async def _transfer_starknet(
        self, account: StarknetAccount, to_address, amount, sequence_number
    ):
        invoke = await self._get_transfer_starknet_invoke(
            account, to_address, amount, sequence_number
        )
        tx = await account.client.send_transaction(invoke)
        return tx

    def get_starknet_transfer_fee(self, account, address):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        task = loop.create_task(
            self._get_starknet_transfer_fee_async(account=account, address=address)
        )
        return loop.run_until_complete(task)

    async def _get_starknet_transfer_fee_async(self, account, address):
        # hack to get transfer fee
        invoke = await self._get_transfer_starknet_invoke(
            account, address, amount=0.00001, sequence_number=100
        )
        return invoke.max_fee
