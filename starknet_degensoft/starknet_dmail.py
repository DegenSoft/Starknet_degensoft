# -*- coding: utf-8 -*-
import os
import random
from starknet_degensoft.starknet_nft import BaseNft
from starknet_degensoft.utils import resource_path


class StarknetDmail(BaseNft):
    project_name = 'DMail'
    _contract_address = '0x0454f0bd015e730e5adbb4f080b075fdbf55654ff41ee336203aa2e1ac4d4309'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        with open(resource_path(os.path.join('..', 'starknet_degensoft', 'files', 'words.txt'))) as f:
            self.words = [line.strip() for line in f]

    async def mint_async(self):
        email, subject = self.generate_random_email()
        print(email, subject)

    def generate_random_email(self):
        email = random.choice(self.words) + random.choice(['@gmail.com', '@yandex.com', '@dmail.ai'])
        subject_length = random.randint(1, 25)
        subject = ' '.join(random.sample(self.words, subject_length))
        return email, subject
