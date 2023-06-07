import random
import requests
import hashlib
from web3 import Web3


class DegenSoftApiError(Exception):
    pass


class DegenSoftApiClient:
    CLIENT_NAME = "starknet"
    CLIENT_PASSWORD = "JidRL83cGgpr"
    API_PASSWORD = "E2ahEczlrsAo"
    SERVER_PASSWORD = "5ALKVQc71hEG"
    BASE_URL = "https://degensoftapi.com/api/"

    def __init__(self, api_key):
        self.api_key = api_key
        self.client_secret = self.make_hash(self.CLIENT_NAME, self.CLIENT_PASSWORD)
        self.server_secret = self.make_hash(self.CLIENT_NAME, self.SERVER_PASSWORD)
        self._last_cancel_id = None

    @staticmethod
    def make_hash(*args):
        return hashlib.sha256(",".join(args).encode("utf-8")).hexdigest()

    @staticmethod
    def create_address_hashes(address):
        if type(address) == str:
            no_checksum = address.lower()
            checksum = Web3.to_checksum_address(no_checksum)
            checksum = hashlib.sha256(checksum.encode('utf-8')).hexdigest()
            no_checksum = hashlib.sha256(no_checksum.encode("utf-8")).hexdigest()
            return [checksum, no_checksum]
        elif type(address) == list:
            return [
                hashlib.sha256(address[0].encode('utf-8')).hexdigest(),
                hashlib.sha256(address[1].lower().encode('utf-8')).hexdigest()
            ]
        else:
            raise ValueError('bad address in create_address_hashes()')

    def make_client_hash(self, method, api_salt):
        return self.make_hash(self.api_key, method, api_salt, self.client_secret)

    def make_server_hash(self, method, response, client_seed):
        salt_generators = {
            "get_userinfo": lambda x: x.get('user', "") + self.API_PASSWORD,
            "new_action": lambda x: str(int(x['success']) + x.get("new_balance", 0)) + self.API_PASSWORD,
            "cancel_action": lambda x: str(self._last_cancel_id) + self.API_PASSWORD
        }
        api_salt = salt_generators[method](response)
        return self.make_hash(self.api_key, method, api_salt, self.server_secret, str(client_seed))

    def make_request(self, method, endpoint, payload=None):
        if payload is None:
            payload = {}
        client_seed = random.randint(100_000, 999_999)
        if payload:
            payload['client_seed'] = client_seed
        url = self.BASE_URL + self.api_key + "/" + endpoint
        res = None
        if method == "GET":
            res = requests.get(url)
        elif method == "POST":
            # print("request payload", endpoint, payload)
            res = requests.post(url, data=payload)

        if not res.ok:
            raise DegenSoftApiError(f'HTTP error: {res.status_code} code')
        try:
            response = res.json()
        except Exception as ex:
            raise ex
        server_hash = self.make_server_hash(endpoint, response, payload.get("client_seed", 0))
        if server_hash != response.get("hash", ""):
            raise DegenSoftApiError("DegenSoft API hashes doesn't match")
        return response

    def get_userinfo(self):
        res = self.make_request("POST", "get_userinfo", {
            "hash": self.make_client_hash("get_userinfo", self.API_PASSWORD),
            "soft": self.CLIENT_NAME
        })
        return res
        # return "user" in res and res['user']

    def new_action(self, action, address):
        hashes = self.create_address_hashes(address)
        result = self.make_request("POST", "new_action", {
            "soft": self.CLIENT_NAME,
            "action": action,
            "hash": self.make_client_hash("new_action", action + self.API_PASSWORD),
            "whitelist_hashes": hashes
        })
        if result['success']:
            self._last_cancel_id = result['cancel_id']
        return result

    def cancel_last_action(self):
        if self._last_cancel_id:
            result = self.make_request("POST", "cancel_action", {
                "id": self._last_cancel_id,
                "hash": self.make_client_hash("cancel_action", str(self._last_cancel_id) + self.API_PASSWORD),
                "soft": self.CLIENT_NAME
            })
            self._last_cancel_id = None
            return result
            # print("Cancel result", result)
