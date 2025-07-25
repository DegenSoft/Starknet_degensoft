# -*- coding: utf-8 -*-
import asyncio
import json
import logging
import os
import pprint
import random
import time
from collections import namedtuple
import traceback

import requests


from PyQt5.QtCore import QThread, pyqtSignal
from eth_account import Account as EthereumAccount
from starknet_py.net.client_errors import ClientError
from starknet_py.net.models.chains import StarknetChainId
from starknet_py.net.signer.stark_curve_signer import KeyPair
from web3 import Web3
from starknet_degensoft.api import Account, Node
from starknet_degensoft.api_client2 import DegenSoftApiClient, DegenSoftApiError
from starknet_degensoft.argentx_updater import ArgentXUpdater
from starknet_degensoft.config import Config
from starknet_degensoft.layerswap import LayerswapBridge
from starknet_degensoft.starkgate import StarkgateBridge
from starknet_degensoft.starknet import Account as StarknetAccount, FullNodeClient
from starknet_degensoft.starknet_swap import (
    MyswapSwap,
    JediSwap,
    TenKSwap,
    BaseSwap,
    StarknetToken,
)
from starknet_degensoft.starknet_swap import SithSwap, AvnuSwap, FibrousSwap
from starknet_degensoft.starknet_nft import BaseNft
from starknet_degensoft.starknet_dmail import BaseDapp
from starknet_degensoft.utils import random_float, get_explorer_address_url

TraderAccount = namedtuple(
    "TraderAccount", field_names=("private_key", "starknet_address", "starknet_account")
)


def action_decorator(action):
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            while 1:
                if self.paused:
                    self.process_pause()
                if self.stopped:
                    break
                try:
                    resp = self._api.new_action(action, self._api_address)
                    if resp["success"]:
                        if resp["is_whitelisted"]:
                            self.logger.info("Wallet is in the WL")
                        else:
                            self.logger.info("Wallet is NOT in the WL")
                        try:
                            # transaction limit exception handler
                            attempt = 1
                            while True:
                                try:
                                    return func(self, *args, **kwargs)
                                except ClientError as ex:
                                    error_message = (
                                        f"An exception occurred:\n\n{type(ex).__name__}: {str(ex)}"
                                        f"\n\nTraceback:\n{traceback.format_exc()}"
                                    )
                                    print(error_message)
                                    if (
                                        "StarknetErrorCode.TRANSACTION_LIMIT_EXCEEDED"
                                        in ex.message
                                        and attempt <= 5
                                    ):
                                        random_delay = random.randint(50, 90)
                                        self.logger.error(
                                            f"Starknet RPC Error: StarknetErrorCode.TRANSACTION_LIMIT_EXCEEDED. Retry in {random_delay} sec."
                                        )
                                        self.process_pause(random_delay)
                                    else:
                                        raise ex
                                except Exception as ex:
                                    error_message = (
                                        f"An exception occurred:\n\n{type(ex).__name__}: {str(ex)}"
                                        f"\n\nTraceback:\n{traceback.format_exc()}"
                                    )
                                    print(error_message)
                                    raise ex
                                attempt += 1
                        except Exception as ex:
                            error_message = (
                                f"An exception occurred:\n\n{type(ex).__name__}: {str(ex)}"
                                f"\n\nTraceback:\n{traceback.format_exc()}"
                            )
                            print(error_message)
                            self.logger.error(ex)
                            self.logger.info(
                                "Points refunding for an unsuccessful action..."
                            )
                            self._api.cancel_last_action()
                            # raise ex
                    else:
                        raise DegenSoftApiError(resp)
                    break
                except Exception as ex:
                    # raise ex
                    self.logger.error("API error: %s" % ex)
                    self.logger.error("Retry in 60 sec.")
                    self.process_pause(60)

        return wrapper

    return decorator


def get_price(symbol: str):
    json_data = requests.get(
        f"https://www.binance.com/api/v3/ticker/price?symbol={symbol.upper()}USDT"
    ).json()
    return float(json_data["price"])


class TraderThread(QThread):
    task_completed = pyqtSignal()
    # logger_signal = pyqtSignal(str)

    def __init__(
        self,
        api,
        trader,
        config,
        swaps: dict,
        bridges: dict,
        back_bridges: dict,
        dapps: dict,
        configs=None,
    ):
        super().__init__()
        self.api = api
        self.trader = trader
        self.config = config
        self.swaps = swaps
        self.bridges = bridges
        self.back_bridges = back_bridges
        self.dapps = dapps
        self.paused = False
        self.configs = configs if configs else {}
        self.logger = logging.getLogger("starknet")
        # self.handler = QtSignalLogHandler(signal=self.logger_signal)
        # self.handler.setFormatter(log_formatter)
        # self.logger.addHandler(self.handler)

    def run(self):
        use_configs = self.configs["use"]
        if use_configs:
            repeat_count = self.configs["repeat_count"]
            for counter in range(1, repeat_count + 1):
                for config_fn in self.configs["file_names"]:
                    loaded_conf = json.load(open(config_fn, "r", encoding="utf-8"))
                    if loaded_conf.get("config_type", "") != "additional":
                        self.logger.error(
                            f"Invalid config: {os.path.basename(config_fn)}"
                        )
                        continue
                    for key in (
                        "gas_limit_spinner",
                        "gas_limit_checkbox",
                        "shuffle_checkbox",
                        "wallet_delay_min_sec",
                        "wallet_delay_max_sec",
                        "project_delay_min_sec",
                        "project_delay_max_sec",
                    ):
                        try:
                            loaded_conf["gui_config"].pop(key)
                        except KeyError:
                            pass
                    self.config.update(loaded_conf["gui_config"])
                    self.logger.info(
                        f"Started config: {os.path.basename(config_fn)} [{counter}/{repeat_count}]"
                    )
                    self.process_run()
                    if self.trader.stopped:
                        break
                    self.trader.process_pause(
                        random.randint(
                            self.configs["delay_from"], self.configs["delay_to"]
                        )
                    )
                    if self.trader.stopped:
                        break
        else:
            self.process_run()
        self.task_completed.emit()

    def process_run(self):
        wallet_delay = (
            self.config["wallet_delay_min_sec"],
            self.config["wallet_delay_max_sec"],
        )
        swap_delay = (
            self.config["project_delay_min_sec"],
            self.config["project_delay_max_sec"],
        )
        projects = []
        # pprint.pp(self.config)
        for key in self.swaps:
            if self.config[f"swap_{key}_checkbox"]:
                amount = (
                    self.config[f"min_price_selector"],
                    self.config[f"max_price_selector"],
                )
                projects.append(
                    dict(
                        cls=self.swaps[key]["cls"],
                        amount=amount,
                        amount_keep=self.config["rest_spinbox"],
                        is_dollars_price=self.config["amount_dollars"],
                    )
                )
        for key in random.sample(list(self.bridges), len(self.bridges)):
            if self.config[f"bridge_{key}_checkbox"]:
                bridge_network_name = self.bridges[key]["networks"][
                    self.config[f"bridge_{key}_network"]
                ]
                bridge_amount = (
                    self.config[f"min_eth_{key}_selector"],
                    self.config[f"max_eth_{key}_selector"],
                )
                projects.append(
                    dict(
                        cls=self.bridges[key]["cls"],
                        network=bridge_network_name,
                        amount=bridge_amount,
                        is_back=False,
                    )
                )
        for key in random.sample(list(self.back_bridges), len(self.back_bridges)):
            if self.config[f"back_bridge_{key}_checkbox"]:
                back_bridge_network_name = self.back_bridges[key]["networks"][
                    self.config[f"back_bridge_{key}_network"]
                ]
                back_bridge_percent = (
                    self.config[f"min_percent_{key}_selector"],
                    self.config[f"max_percent_{key}_selector"],
                )
                projects.append(
                    dict(
                        cls=self.back_bridges[key]["cls"],
                        network=back_bridge_network_name,
                        amount_percent=back_bridge_percent,
                        is_back=True,
                    )
                )
        for key in self.dapps:
            for key1 in self.dapps[key]:
                if self.config[f"dapp_{key1}_checkbox"]:
                    projects.append(dict(cls=self.dapps[key][key1]["cls"]))
        if self.config["backswaps_checkbox"]:
            projects.append(
                dict(
                    cls=None,
                    count=self.config["backswaps_count_spinbox"],
                    amount_usd=self.config["backswaps_usd_spinbox"],
                )
            )
        self.trader.run(
            projects=projects,
            # wallet_delay=wallet_delay,
            # project_delay=swap_delay,
            shuffle=self.config["shuffle_checkbox"],
            random_swap_project=self.config["random_swap_checkbox"],
            random_dapp_project=self.config["random_dapp_checkbox"],
            api=self.api,
            # gas_limit=self.config['gas_limit_spinner'] if self.config['gas_limit_checkbox'] else None,
            slippage=self.config.get("slippage_spinbox", 1.0),
            keep_amount_usd=self.config.get("rest_spinbox", 0.0),
        )

    def pause(self):
        self.trader.pause()
        self.paused = True

    def stop(self):
        self.trader.stop()
        # self.stopped = True

    def resume(self):
        self.trader.resume()
        self.paused = False


class StarknetTrader:
    def __init__(self, config: Config, testnet=False):
        self.config = config
        self.paused = False
        self._success_counter = 0
        self.stopped = False
        self.testnet = testnet
        self._api = None
        self._api_address = None
        rpc_url = (
            random.choice(self.config.networks.starknet.rpc)
            if not testnet
            else random.choice(self.config.networks.starknet_goerli.rpc)
        )
        self.starknet_client = FullNodeClient(rpc_url)
        self.starknet_contracts = self.config.data["starknet_contracts"][
            "goerli" if testnet else "mainnet"
        ].copy()
        self.starknet_eth_contract = self.starknet_contracts.pop("ETH")
        # self.ethereum_node = Node(rpc_url='https://eth.llamarpc.com', explorer_url='https://etherscan.io/')
        self.ethereum_node = Node(
            rpc_url="https://ethereum.publicnode.com",
            explorer_url="https://etherscan.io/",
        )
        self.logger = logging.getLogger("starknet")
        self.logger.setLevel(logging.DEBUG)
        self.accounts = []

    def load_private_keys(self, wallets):
        accounts = []
        for row in wallets:
            if (
                "ethereum_private_key" not in row
                or "starknet_address" not in row
                or "starknet_private_key" not in row
            ):
                raise ValueError("bad wallets file format")
            ethereum_private_key = (
                row["ethereum_private_key"] if row["ethereum_private_key"] else None
            )
            if ethereum_private_key:
                eth_account = Web3().eth.account.from_key(
                    ethereum_private_key
                )  # checking ethereum private key
                # self.logger.debug(f'Loaded account: {eth_account.address}')
            try:
                starknet_address = row["starknet_address"]
                starknet_account = self.get_account(
                    starknet_address, row["starknet_private_key"]
                )
                # starknet_balance = Web3.from_wei(starknet_account.get_balance_sync(), 'ether')
            except ValueError:
                raise ValueError("bad Starknet address or private key")
            # self.logger.debug(f'Loaded Starknet account: {hex(starknet_account.address)}')
            accounts.append(
                TraderAccount(
                    private_key=ethereum_private_key,
                    starknet_address=starknet_address,
                    starknet_account=starknet_account,
                )
            )
        self.accounts = accounts

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stopped = True
        self.starknet_client.is_stopped = True

    def process_pause(self, sec=None):
        if sec:
            self.logger.debug(f"delay for {sec} sec.")
            for i in range(sec):
                time.sleep(1)
                if self.stopped:
                    break
        else:
            while True:
                if self.stopped or not self.paused:
                    break

    def get_tx_url(self, tx_hash):
        if self.testnet:
            return f"https://testnet.starkscan.co/tx/{tx_hash}"
        else:
            return f"https://starkscan.co/tx/{tx_hash}"

    def get_address_url(self, address):
        if self.testnet:
            return f"https://testnet.starkscan.co/contract/{address}"
        else:
            return f"https://starkscan.co/contract/{address}"

    def wait_for_gas(self):
        while True:
            if not self.config.data["gui_config"]["gas_limit_checkbox"]:
                break
            max_gwei = self.config.data["gui_config"]["gas_limit_spinner"]
            try:
                gwei = Web3.from_wei(self.ethereum_node.gas_price, "gwei")
            except Exception as ex:
                self.logger.error(ex)
                self.process_pause(3)
                continue
            if gwei < max_gwei:
                self.logger.debug(f"Gas is {gwei} gwei")
                break
            else:
                self.logger.debug(
                    f"Gas {gwei} gwei > {max_gwei} gwei, waiting for the cheap gas"
                )
                self.process_pause(60)
            if self.stopped:
                break

    def run(
        self,
        projects: list,
        shuffle: bool = False,
        random_swap_project: bool = False,
        random_dapp_project: bool = False,
        api: DegenSoftApiClient = None,
        slippage: float = 1.0,
        keep_amount_usd: float = 0.0,
    ):
        self.paused = False
        self.stopped = False
        self._api = api
        if shuffle:
            random.shuffle(self.accounts)
        self.logger.info(f'Ethereum price: {get_price("ETH")}$')
        for i, account in enumerate(self.accounts, 1):
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            starknet_address = hex(account.starknet_account.address)
            self._success_counter = 0
            is_deployed = None
            for attempt_ in range(3):
                try:
                    balance = Web3.from_wei(
                        account.starknet_account.get_balance_sync(), "ether"
                    )
                    is_deployed = account.starknet_account.is_deployed_sync()
                    self.logger.info(
                        f"Starknet Account {i}/{len(self.accounts)} {hex(account.starknet_account.address)} ({balance:.4f} ETH)"
                    )
                    break
                except Exception as ex:
                    self.logger.error(ex)
                    self.logger.info("retry")
                    # raise  # todo: remove
            if is_deployed is None:
                self.logger.info(
                    f"Starknet Account {i}/{len(self.accounts)} {hex(account.starknet_account.address)}"
                )
                self.logger.error(
                    "could not get account balance and deploy status, probably RPC error"
                )
                continue
            if is_deployed:
                try:
                    ArgentXUpdater(
                        account.starknet_account, logger=self.logger
                    ).auto_update_sync()
                except Exception as ex:
                    self.logger.error(ex)
                    continue

            # choosing random SWAP project and uniq order
            other_projects = []
            bridge_projects = []
            swap_projects = []
            dapp_projects = []
            for k, project in enumerate(projects, 1):
                if not project["cls"]:
                    other_projects.append(project)
                elif issubclass(project["cls"], BaseSwap):
                    swap_projects.append(project)
                elif issubclass(project["cls"], BaseNft):
                    dapp_projects.append(project)
                elif (
                    project["cls"] == StarkgateBridge
                    or project["cls"] == LayerswapBridge
                ):
                    bridge_projects.append(project)
            random.shuffle(swap_projects)
            if random_swap_project:
                swap_projects = swap_projects[:1]
            random.shuffle(dapp_projects)
            if random_dapp_project:
                dapp_projects = dapp_projects[:1]
            unique_projects = (
                swap_projects + other_projects + dapp_projects + bridge_projects
            )

            for j, project in enumerate(unique_projects, 1):
                self.wait_for_gas()
                if self.paused:
                    self.process_pause()
                if self.stopped:
                    break
                if (
                    project["cls"] is None or issubclass(project["cls"], BaseSwap)
                ) and not is_deployed:
                    self.logger.error("Account not deployed yet")
                    break
                self._api_address = [account.starknet_address, starknet_address]
                wait_for_tx = False if j == len(unique_projects) else True

                if project["cls"] is None:
                    try:
                        self.back_swap(
                            starknet_account=account.starknet_account,
                            count=project["count"],
                            min_amount_usd=project["amount_usd"],
                            slippage=slippage,
                        )
                    except Exception as ex:
                        self.logger.error(ex)
                elif issubclass(project["cls"], BaseNft) or issubclass(
                    project["cls"], BaseDapp
                ):
                    if issubclass(project["cls"], BaseDapp):
                        self.logger.info(f'dApp {project["cls"].project_name}')
                    else:
                        self.logger.info(f'Mint NFT {project["cls"].project_name}')
                    if not self.config.data.get("simulate"):
                        self.nft(
                            nft_cls=project["cls"],
                            account=account.starknet_account,
                            wait_for_tx=wait_for_tx,
                        )
                elif issubclass(project["cls"], BaseSwap):
                    # swap amount calculation
                    eth_price = get_price("ETH")
                    balance_wei = account.starknet_account.get_balance_sync()
                    self.logger.debug(
                        f'current balance {Web3.from_wei(balance_wei, "ether"):.4f} ETH '
                        f'({(float(Web3.from_wei(balance_wei, "ether")) * eth_price):.2f} USD)'
                    )
                    keep_amount_wei = Web3.to_wei(
                        (
                            keep_amount_usd
                            + self.config.data.get("default_transaction_fee", 0)
                        )
                        / eth_price,
                        "ether",
                    )
                    if balance_wei - keep_amount_wei < 0:
                        self.logger.error(
                            f"keep amount + tx fee "
                            f'({Web3.from_wei(keep_amount_wei, "ether"):.4f} ETH)'
                            f' > wallet balance ({Web3.from_wei(balance_wei, "ether"):.4f} ETH)'
                        )
                        continue
                    if project["is_dollars_price"]:
                        min_amount_wei = Web3.to_wei(
                            project["amount"][0] / eth_price, "ether"
                        )
                        max_amount_wei = Web3.to_wei(
                            project["amount"][1] / eth_price, "ether"
                        )
                    else:
                        min_amount_wei = int(
                            (balance_wei - keep_amount_wei)
                            * project["amount"][0]
                            / 100.0
                        )
                        max_amount_wei = int(
                            (balance_wei - keep_amount_wei)
                            * project["amount"][1]
                            / 100.0
                        )
                    if max_amount_wei > balance_wei - keep_amount_wei:
                        max_amount_wei = balance_wei - keep_amount_wei
                    if min_amount_wei > max_amount_wei:
                        self.logger.error(
                            f"not enough balance: try to reduce min amount to swap, or amount to keep"
                        )
                        continue
                    random_amount = random.randint(min_amount_wei, max_amount_wei)
                    token_names = list(self.starknet_contracts.keys())
                    if project["cls"] == MyswapSwap:
                        token_names.remove("WBTC")
                    token_name = random.choice(token_names)
                    token_address = self.starknet_contracts[token_name]
                    self.logger.info(
                        f'Swap {project["cls"].swap_name}: '
                        f'{Web3.from_wei(random_amount, "ether"):.4f} ETH -> {token_name}'
                    )
                    if not self.config.data.get("simulate"):
                        self.swap(
                            swap_cls=project["cls"],
                            account=account.starknet_account,
                            amount=random_amount,
                            token_a_address=self.starknet_eth_contract,
                            token_b_address=token_address,
                            wait_for_tx=wait_for_tx,
                            slippage=slippage,
                        )
                elif (project["cls"] == StarkgateBridge) and account.private_key:
                    random_amount = random_float(*project["amount"])
                    self.logger.info(
                        f'Bridge Stargate from {project["network"]} -> {random_amount} ETH'
                    )
                    if not self.config.data.get("simulate"):
                        self.deposit_starkgate(
                            ethereum_private_key=account.private_key,
                            starknet_account=account.starknet_account,
                            amount=random_amount,
                        )
                elif (project["cls"] == LayerswapBridge) and account.private_key:
                    if not project["is_back"]:
                        random_amount = random_float(*project["amount"])
                        self.logger.info(
                            f'Bridge Layerswap from {project["network"]} -> {random_amount} ETH'
                        )
                        if not self.config.data.get("simulate"):
                            self.deposit_layerswap(
                                source_network=project["network"],
                                ethereum_private_key=account.private_key,
                                starknet_account=account.starknet_account,
                                amount=random_amount,
                            )

                    else:
                        random_percent = random.randint(*project["amount_percent"])
                        self.logger.info(
                            f'Back bridge Layerswap to {project["network"]} -> {random_percent}% of balance'
                        )
                        if not self.config.data.get("simulate"):
                            self.withdraw_layerswap(
                                ethereum_private_key=account.private_key,
                                starknet_account=account.starknet_account,
                                destination_network=project["network"],
                                amount_percent=random_percent,
                                wait_for_tx=wait_for_tx,
                            )

                if j < len(projects) and self._success_counter:
                    self.process_pause(self.get_delay("project_delay"))
            if i < len(self.accounts) and self._success_counter:
                self.process_pause(self.get_delay("wallet_delay"))

    def get_delay(self, delay_name):
        delay_min = self.config.data["gui_config"][f"{delay_name}_min_sec"]
        delay_max = self.config.data["gui_config"][f"{delay_name}_max_sec"]
        if delay_max < delay_min:
            delay_max = delay_min
        return random.randint(delay_min, delay_max)

    def get_account(self, address, private_key) -> StarknetAccount:
        try:
            _key = int(private_key)
        except Exception:
            _key = int(private_key, base=16)
        key_par = KeyPair.from_private_key(key=_key)
        account = StarknetAccount(
            client=self.starknet_client,
            address=address,
            key_pair=key_par,
            chain=StarknetChainId.GOERLI if self.testnet else StarknetChainId.MAINNET,
        )
        account.ESTIMATED_FEE_MULTIPLIER = 1.25
        return account

    def setup_account(self, account: StarknetAccount):
        raise NotImplementedError()

    def back_swap(self, starknet_account, count, min_amount_usd, slippage):
        # self.logger.debug(f'count={count}, amount_usd={min_amount_usd}')
        cnt = 0
        tokens_to_swap = []
        self.logger.info("Looking up for the tokens...")
        for token_symbol in self.starknet_contracts:
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            token = StarknetToken(
                self.starknet_contracts[token_symbol], starknet_account
            )
            balance = token.balance()
            if token_symbol in ("DAI", "USDC", "USDT"):
                balance_usd = token.from_native(balance)
            elif token_symbol == "WBTC":
                balance_usd = token.from_native(balance) * get_price("BTC")
            else:
                raise ValueError(
                    f"bad token {token_symbol}, could not calculate USD token balance"
                )
            # self.logger.debug(f'balance {token.from_native(balance):.4f} {token_symbol} ({balance_usd:.4f} USD)')
            if balance_usd > min_amount_usd:
                all_swap_clss = [
                    MyswapSwap,
                    JediSwap,
                    TenKSwap,
                    SithSwap,
                    AvnuSwap,
                    FibrousSwap,
                ]
                if token_symbol not in ("DAI", "USDC", "USDT"):
                    all_swap_clss = all_swap_clss[1:]  # remove Myswap
                swap_cls = random.choice(all_swap_clss)
                tokens_to_swap.append(
                    dict(
                        cls=swap_cls,
                        token=token,
                        symbol=token_symbol,
                        balance=balance,
                        balance_usd=balance_usd,
                    )
                )
                cnt += 1
            if cnt >= count:
                break
        random.shuffle(tokens_to_swap)
        if not tokens_to_swap:
            self.logger.info("No token balance to swap")
        for i, token_to_swap in enumerate(tokens_to_swap, 1):
            if self.paused:
                self.process_pause()
            if self.stopped:
                break
            # wait_for_tx = False if i == len(tokens_to_swap) else True
            balance_from_native = token_to_swap["token"].from_native(
                token_to_swap["balance"]
            )
            self.logger.info(
                f'Swap {token_to_swap["cls"].swap_name}: {balance_from_native:.4f} '
                f'{token_to_swap["symbol"]} ({token_to_swap["balance_usd"]:.4f} USD) -> ETH'
            )
            # self.logger.debug(f'wait_for_tx={wait_for_tx} i={i}, len()={len(tokens_to_swap)}')
            if self.config.data.get("simulate"):
                continue
            self.swap(
                swap_cls=token_to_swap["cls"],
                account=starknet_account,
                amount=token_to_swap["balance"],
                token_a_address=self.starknet_contracts[token_to_swap["symbol"]],
                token_b_address=self.starknet_eth_contract,
                wait_for_tx=True,
                slippage=slippage,
            )

    @action_decorator("bridge")
    def deposit_layerswap(
        self, source_network, ethereum_private_key, starknet_account, amount
    ):
        if self.testnet:
            network_config = self.config.data["networks"]["ethereum_goerli"]
        else:
            network_config = self.config.data["networks"][
                source_network.lower().replace(" ", "_")
            ]
        node = Node(
            rpc_url=random.choice(network_config["rpc"]),
            explorer_url=network_config["explorer"],
        )
        account = Account(node=node, private_key=ethereum_private_key)
        bridge = LayerswapBridge(api_key=self.config.data["gui_config"]["ls_api_key"])
        tx_hash = bridge.deposit(
            account=account, amount=amount, to_l2_address=hex(starknet_account.address)
        )
        self.logger.info(node.get_explorer_transaction_url(tx_hash))
        self._success_counter += 1
        return tx_hash.hex()

    @action_decorator("bridge")
    def withdraw_layerswap(
        self,
        ethereum_private_key,
        starknet_account,
        destination_network,
        amount_percent,
        wait_for_tx=False,
    ):
        bridge = LayerswapBridge(api_key=self.config.data["gui_config"]["ls_api_key"])
        ethereum_account = EthereumAccount.from_key(ethereum_private_key)
        to_l2_address = ethereum_account.address
        explorer_url = self.config.data["networks"][
            destination_network.lower().replace(" ", "_")
        ]["explorer"]
        balance = starknet_account.get_balance_sync()
        fee = bridge.get_starknet_transfer_fee(starknet_account, to_l2_address)
        transfer_amount = int((balance - fee) * amount_percent / 100)
        if transfer_amount < 1:
            raise ValueError(
                f"Calculated amount less then zero because of the transfer fee, could not withdraw"
            )
        elif transfer_amount < 0.0001 * 10**18:
            raise ValueError(
                f'Calculated amount less then minimum layerswap amount: {Web3.from_wei(transfer_amount, "ether"):.4f} &lt; {Web3.from_wei(min_amount, "ether"):.4f}'
            )
        elif transfer_amount > 2 * 10**18:  # 2 ETH
            raise ValueError(
                f'Calculated amount greater then minimum layerswap amount: {Web3.from_wei(transfer_amount, "ether"):.4f} &gt; {Web3.from_wei(max_amount, "ether"):.4f}'
            )
        self.logger.debug(
            f'Amount is {Web3.from_wei(transfer_amount, "ether"):.4f} ETH'
        )
        # print(type(Web3.from_wei(transfer_amount, 'ether')))
        tx_hash = bridge.deposit(
            account=starknet_account,
            amount=Web3.from_wei(transfer_amount, "ether"),
            to_l2_address=to_l2_address,
            to_network=destination_network,
        )
        self.logger.info(self.get_tx_url(tx_hash))
        self.logger.debug(get_explorer_address_url(to_l2_address, explorer_url))
        if wait_for_tx and not self.stopped:
            self.logger.debug("Waiting for tx confirmation...")
            self.starknet_client.wait_for_tx_sync(
                int(tx_hash, base=16), check_interval=5
            )
        self._success_counter += 1
        return tx_hash

    @action_decorator("bridge")
    def deposit_starkgate(self, ethereum_private_key, starknet_account, amount):
        network_config = self.config.data["networks"][
            "ethereum_goerli" if self.testnet else "ethereum"
        ]
        node = Node(
            rpc_url=random.choice(network_config["rpc"]),
            explorer_url=network_config["explorer"],
        )
        bridge = StarkgateBridge(
            node=node, network="testnet" if self.testnet else "mainnet"
        )
        account = Account(node=node, private_key=ethereum_private_key)
        self.logger.info(node.get_explorer_address_url(account.address))
        tx_hash = bridge.deposit(
            account=account,
            amount=Web3.to_wei(amount, "ether"),
            to_l2_address=hex(starknet_account.address),
        )
        self.logger.info(node.get_explorer_transaction_url(tx_hash))
        self.logger.info(
            self.get_tx_url("").replace("/tx/", f"/eth-tx/{tx_hash.hex()}")
        )
        self._success_counter += 1
        return tx_hash.hex()

    @action_decorator("swap")
    def swap(
        self,
        swap_cls,
        account,
        amount,
        token_a_address,
        token_b_address,
        wait_for_tx=True,
        slippage=1.0,
    ):
        # self.logger.debug(f'slippage={slippage}')
        s = swap_cls(
            account=account,
            testnet=self.testnet,
            eth_contract_address=self.starknet_eth_contract,
        )
        res = s.swap(
            amount=amount,
            token_a_address=token_a_address,
            token_b_address=token_b_address,
            slippage=slippage,
        )
        self.logger.info(self.get_tx_url(hex(res.transaction_hash)))
        if wait_for_tx and not self.stopped:
            self.logger.debug("Waiting for tx confirmation...")
            self.starknet_client.wait_for_tx_sync(
                res.transaction_hash, check_interval=5
            )
        self._success_counter += 1
        return hex(res.transaction_hash)

    @action_decorator("nft")
    def nft(self, nft_cls, account, wait_for_tx=True):
        n = nft_cls(account=account, eth_contract_address=self.starknet_eth_contract)
        res = n.mint()
        self.logger.info(self.get_tx_url(hex(res.transaction_hash)))
        if wait_for_tx and not self.stopped:
            self.logger.debug("Waiting for tx confirmation...")
            self.starknet_client.wait_for_tx_sync(
                res.transaction_hash, check_interval=5
            )
        self._success_counter += 1
        return hex(res.transaction_hash)
