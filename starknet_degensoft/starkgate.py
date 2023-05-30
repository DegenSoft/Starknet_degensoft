# -*- coding: utf-8 -*-
import requests
import time
from starknet_degensoft.api import Node, Contract, Account
from pprint import pprint


class StarkgateBridge(Contract):
    def __init__(self, node: Node, network: str):
        if network == 'mainnet':
            address = '0xae0Ee0A63A2cE6BaeEFFE56e7714FB4EFE48D419'
        elif network == 'testnet':
            address = '0xc3511006C04EF1d78af4C8E0e74Ec18A6E64Ff9e'
        else:
            raise ValueError('bad network: %s' % network)
        self._network = network
        super().__init__(node, 'starkgate', address)

    def deposit(self, account: Account, amount: int, to_l2_address: str):
        message_fee = self.estimate_message_fee(amount_wei=amount, to_l2_address=to_l2_address)
        total_amount = amount + message_fee['overall_fee']
        tx = self.functions.deposit(amount, int(to_l2_address, 16))
        gas_multipler = 1.0
        for attempt in range(10):
            try:
                tx = account.build_transaction(tx, total_amount)
                tx['maxFeePerGas'] = int(tx['maxFeePerGas'] * gas_multipler)
                tx['maxPriorityFeePerGas'] = int(tx['maxPriorityFeePerGas'] * gas_multipler)
                signed_tx = account.sign_transaction(tx)
                return self._node.send_raw_transaction(signed_tx.rawTransaction)
            except Exception as ex:
                if 'message' in ex.args[0]:
                    msg = ex.args[0]['message']
                    if msg.startswith('err: max fee per gas less than block base fee') or \
                            msg.startswith('replacement transaction underpriced'):
                        # print('extend gas price')
                        gas_multipler += 0.25
                        # time.sleep(1)
                        continue
                raise ex

    def estimate_message_fee(self, amount_wei: int, to_l2_address: str):
        url_prefix = 'alpha-mainnet' if self._network == 'mainnet' else 'alpha4'
        json_data = {
                "from_address": int(self.address, base=16),  # l1 contract address
                "to_address": '0x073314940630fd6dcda0d772d4c972c4e0a9946bef9dabf4ef84eda8ef542b82',  # l2 bridge address for ETH
                "entry_point_selector": '0x2d757788a8d8d6f21d1cd40bce38a8222d70654214e96ff95d8086e684fbee5',  # hz chto eto
                "payload": [to_l2_address, hex(amount_wei), "0x0"],  # starknet to address, amount, payload 0x0
            }
        r = requests.post(
            f'https://{url_prefix}.starknet.io/feeder_gateway/estimate_message_fee?blockNumber=pending',
            json=json_data)
        return r.json()
