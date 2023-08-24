import json
import logging
import os
import random
import sys
import time

from PyQt5.Qt import QDesktopServices, QUrl, Qt, QTextCursor
from PyQt5.QtCore import QThread, pyqtSignal, QMetaObject
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox, QPushButton, \
    QTextEdit, QLabel, QLineEdit, QAction, QWidget, QDesktopWidget, QFileDialog, \
    QSplitter, QDoubleSpinBox, QSpinBox, QAbstractSpinBox, QMessageBox, QTextBrowser, QDialog, QDialogButtonBox

from degensoft.filereader import UniversalFileReader
from starknet_degensoft.api_client2 import DegenSoftApiClient
from starknet_degensoft.config import Config
from starknet_degensoft.layerswap import LayerswapBridge
from starknet_degensoft.starkgate import StarkgateBridge
from starknet_degensoft.starknet_swap import MyswapSwap, TenKSwap, JediSwap
from starknet_degensoft.starknet_trader import StarknetTrader
from starknet_degensoft.utils import setup_file_logging, log_formatter, convert_urls_to_links, \
    mask_hex_in_string


class QtSignalLogHandler(logging.Handler):
    def __init__(self, signal):
        super().__init__()
        self.signal = signal

    def emit(self, record):
        message = self.format(record)
        self.signal.emit(message)

    def flush(self):
        pass


class GuiLogHandler(logging.Handler):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def emit(self, record):
        message = self.format(record)
        self.callback(message)

    def flush(self):
        pass


def setup_gui_loging(logger, callback, formatter=log_formatter):
    handler = GuiLogHandler(callback=callback)
    # formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
    formatter = log_formatter
    handler.setFormatter(formatter)
    logger.addHandler(handler)


class TraderThread(QThread):
    task_completed = pyqtSignal()
    # logger_signal = pyqtSignal(str)

    def __init__(self, api, trader, config, swaps, bridges, back_bridges, configs={}):
        super().__init__()
        self.api = api
        self.trader = trader
        self.config = config
        self.swaps = swaps
        self.bridges = bridges
        self.back_bridges = back_bridges
        self.paused = False
        self.configs = configs
        self.logger = logging.getLogger('starknet')
        # self.handler = QtSignalLogHandler(signal=self.logger_signal)
        # self.handler.setFormatter(log_formatter)
        # self.logger.addHandler(self.handler)

    def run(self):
        use_configs = self.configs['use']
        if use_configs:
            repeat_count = self.configs['repeat_count']
            for counter in range(1, repeat_count + 1):
                for config_fn in self.configs['file_names']:
                    loaded_conf = json.load(open(config_fn, "r", encoding='utf-8'))
                    if loaded_conf.get("config_type", "") != "additional":
                        self.logger.error(f"Invalid config: {os.path.basename(config_fn)}")
                        continue
                    self.config.update(loaded_conf['gui_config'])
                    self.logger.info(f"Started config: {os.path.basename(config_fn)} [{counter}/{repeat_count}]")
                    self.process_run()
                    if self.trader.stopped:
                        return self.task_completed.emit()
                    self.trader.process_pause(random.randint(self.configs['delay_from'], self.configs['delay_to']))
                    if self.trader.stopped:
                        return self.task_completed.emit()
        else:
            self.process_run()
        self.task_completed.emit()

    def process_run(self):
        wallet_delay = (self.config['wallet_delay_min_sec'], self.config['wallet_delay_max_sec'])
        swap_delay = (self.config['project_delay_min_sec'], self.config['project_delay_max_sec'])
        projects = []
        for key in self.swaps:
            if self.config[f'swap_{key}_checkbox']:
                projects.append(dict(cls=self.swaps[key]['cls'],
                                     amount_usd=(self.config[f'min_price_{key}_selector'],
                                                 self.config[f'max_price_{key}_selector'])))
        for key in random.sample(list(self.bridges), len(self.bridges)):
            if self.config[f'bridge_{key}_checkbox']:
                bridge_network_name = self.bridges[key]['networks'][self.config[f'bridge_{key}_network']]
                bridge_amount = (self.config[f'min_eth_{key}_selector'], self.config[f'max_eth_{key}_selector'])
                projects.append(dict(cls=self.bridges[key]['cls'], network=bridge_network_name,
                                     amount=bridge_amount, is_back=False))
        for key in random.sample(list(self.back_bridges), len(self.back_bridges)):
            if self.config[f'back_bridge_{key}_checkbox']:
                back_bridge_network_name = self.back_bridges[key]['networks'][self.config[f'back_bridge_{key}_network']]
                back_bridge_percent = (self.config[f'min_percent_{key}_selector'],
                                       self.config[f'max_percent_{key}_selector'])
                projects.append(dict(cls=self.back_bridges[key]['cls'], network=back_bridge_network_name,
                                     amount_percent=back_bridge_percent, is_back=True))
        if self.config['backswaps_checkbox']:
            projects.append(dict(cls=None,
                                 count=self.config['backswaps_count_spinbox'],
                                 amount_usd=self.config['backswaps_usd_spinbox']))
        self.trader.run(projects=projects, wallet_delay=wallet_delay,
                        project_delay=swap_delay, shuffle=self.config['shuffle_checkbox'],
                        random_swap_project=self.config['random_swap_checkbox'],
                        api=self.api, config=self.config)

        # self.logger.removeHandler(self.handler)

    def pause(self):
        self.trader.pause()
        self.paused = True

    def stop(self):
        self.trader.stop()
        # self.stopped = True

    def resume(self):
        self.trader.resume()
        self.paused = False


class MyQTextEdit(QTextEdit):

    def mousePressEvent(self, e):
        self.anchor = self.anchorAt(e.pos())
        if self.anchor:
            QApplication.setOverrideCursor(Qt.PointingHandCursor)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self.anchor:
            QDesktopServices.openUrl(QUrl(self.anchor))
            QApplication.setOverrideCursor(Qt.IBeamCursor)
            self.anchor = None
        super().mouseReleaseEvent(e)


class PasswordDialog(QDialog):
    def __init__(self, *args, language, messages, **kwargs):
        super().__init__(*args, **kwargs)
        self.language = language
        self.messages = messages
        self.setupUi(self)

    def setupUi(self, Dialog):
        Dialog.setObjectName("Dialog")
        Dialog.resize(388, 95)
        self.verticalLayout = QVBoxLayout(Dialog)
        self.verticalLayout.setObjectName("verticalLayout")
        self.label = QLabel(Dialog)
        self.label.setObjectName("label")
        self.verticalLayout.addWidget(self.label)
        self.lineEdit = QLineEdit(Dialog)
        self.lineEdit.setEchoMode(QLineEdit.Password)
        self.lineEdit.setObjectName("lineEdit")
        self.verticalLayout.addWidget(self.lineEdit)
        self.buttonBox = QDialogButtonBox(Dialog)
        self.buttonBox.setAutoFillBackground(False)
        # self.buttonBox.setLocale(QtCore.QLocale(QtCore.QLocale.Russian, QtCore.QLocale.RussianFederation))
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.buttonBox.setObjectName("buttonBox")
        self.verticalLayout.addWidget(self.buttonBox)

        self.retranslateUi(Dialog)
        self.buttonBox.accepted.connect(Dialog.accept)
        self.buttonBox.rejected.connect(Dialog.reject)
        QMetaObject.connectSlotsByName(Dialog)

    def retranslateUi(self, Dialog):
        # Dialog.setWindowTitle(_translate("Dialog", "Enter Password"))
        Dialog.setWindowTitle(self.messages[self.language]['password_dialog_title'])
        self.label.setText(self.messages[self.language]['password_dialog_message'])


class MainWindow(QMainWindow):
    CONFIG_FILENAME = os.environ.get('CONFIG_FILENAME', 'config.json')
    SLAVIK_API_SECRET = ''

    file_name = None
    log_line = 0
    worker_thread = None
    logger_signal = pyqtSignal(str)

    bridges = {
        'starkgate': {
            'name': 'Starkgate',
            'cls': StarkgateBridge,
            'networks': ['Ethereum']
        },
        'layerswap': {
            'name': 'Layerswap.io',
            'cls': LayerswapBridge,
            'networks': ['Arbitrum One', 'Arbitrum Nova']
        }
    }

    back_bridges = {
        'layerswap': {
            'name': 'Layerswap.io',
            'cls': LayerswapBridge,
            'networks': ['Arbitrum One',
                         'Arbitrum Nova',
                         'Ethereum']
        }
    }

    swaps = {
        'myswap': {'name': 'myswap.xyz', 'cls': MyswapSwap},
        '10kswap': {'name': '10kswap', 'cls': TenKSwap},
        'jediswap': {'name': 'jediswap', 'cls': JediSwap},
    }

    messages = {
        'en': {
            'window_title': "Starknet [DEGENSOFT]",
            'language_label': "Language",
            'api_key_label': "API Key (you can get it via <a href='http://t.me/degensoftbot'>@DegenSoftBot</a>)",
            'api_key_checkbox': "hide",
            'private_keys_label': "Private keys file",
            'bridges_label': "Select bridge and source network to transfer ETH to Starknet",
            'back_bridges_label': "Select bridge and destination network to withdraw ETH from Starknet",
            'quests_label': "Select quests",
            'backswaps_label': "Back swap tokens to ETH",
            'backswaps_checkbox': "Make swap tokens to ETH",
            'backswaps_usd_label': "Minimum token USD price:",
            'backswaps_count_label': "Amount of swaps (random tokens):",
            'options_label': "Options",
            'wallet_delay_label': "Wallet delay",
            'project_delay_label': "Project delay",
            'wallet_delay_min_sec_label': "min sec:",
            'project_delay_min_sec_label': "min sec:",
            'wallet_delay_max_sec_label': "max sec:",
            'project_delay_max_sec_label': "max sec:",
            'random_swap_checkbox': "Random project",
            'min_eth_label': "min ETH:",
            'max_eth_label': "max ETH:",
            'min_price_label': "min $:",
            'max_price_label': "max $:",
            'min_percent_layerswap_label': "min %:",
            'max_percent_layerswap_label': "max %:",
            'shuffle_checkbox': "Shuffle wallets",
            'select_file_button': "Import wallets",
            'start_button': "Start",
            'stop_button': "Stop",
            'pause_button': "Pause/Continue",
            'apikey_error': 'You must set API key!',
            'api_error': 'Bad API key or API error: ',
            'file_error': 'You must select file with private keys!',
            'csv_error': 'Failed to load wallets file: ',
            'minmax_eth_error': 'Minimum ETH amount must be non-zero and less then Maximum ETH amount',
            'minmax_percent_error': 'Minimum percent must be less then Maximum percent',
            'minmax_usd_error': 'Minimum USD$ amount must be non-zero and less then Maximum USD$ amount',
            'minmax_delay_error': 'Minimum delay must be less or equal maximum delay',
            'decryption_error': 'Decryption error or wrong password',
            'password_dialog_title': 'Enter Password',
            'password_dialog_message': 'Enter password to decrypt wallets file:',
            "decrypt_wallets_label": "Decrypt wallets",
            "gas_limit_label": "Gas limit:",
            "configs_label": "Configuration options",
            "save_config_button": "Save current configuration",
            "select_configs_button": "Load configurations"
        },
        'ru': {
            'window_title': "Starknet [DEGENSOFT]",
            'language_label': "Язык",
            'api_key_label': "API ключ (вы можете получить его через <a href='http://t.me/degensoftbot'>@DegenSoftBot</a>)",
            'api_key_checkbox': "скрыть",
            'private_keys_label': "Файл приватных ключей",
            'bridges_label': "Выберете мост и сеть в которой у вас есть ETH для перевода в Starknet",
            'back_bridges_label': "Выберете мост и сеть в которую переводить ETH из Starknet",
            'quests_label': "Выберете квесты",
            'backswaps_label': "Обмен токенов обратно в ETH",
            'backswaps_checkbox': "Сделать свап токенов в ETH",
            'backswaps_usd_label': "Минимальная цена токена в USD:",
            'backswaps_count_label': "Количество свапов в ETH (рандомный выбор токенов):",
            'options_label': "Настройки",
            'wallet_delay_label': "Задержка между кошельками",
            'project_delay_label': "Задержка между проектами",
            'wallet_delay_min_sec_label': "мин сек:",
            'project_delay_min_sec_label': "мин сек:",
            'wallet_delay_max_sec_label': "макс сек:",
            'project_delay_max_sec_label': "макс сек:",
            'random_swap_checkbox': "Рандомный проект",
            'min_eth_label': "мин ETH:",
            'max_eth_label': "макс ETH:",
            'min_price_label': "мин $:",
            'max_price_label': "макс $:",
            'min_percent_layerswap_label': "мин %:",
            'max_percent_layerswap_label': "макс %:",
            'shuffle_checkbox': "Перемешать кошельки",
            'select_file_button': "Импорт кошельков",
            'start_button': "Старт",
            'stop_button': "Стоп",
            'pause_button': "Пауза/Продолжить",
            'apikey_error': 'Вы должны ввести API ключ!',
            'api_error': 'Неправильный ключ API или ошибка API: ',
            'file_error': 'Вы должны выбрать файл приватных ключей!',
            'csv_error': 'Не удалось загрузить файл кошельков: ',
            'minmax_eth_error': 'Минимальная сумма ETH должна быть больше нуля и меньше Максимальной суммы ETH',
            'minmax_percent_error': 'Минимальный процент должен быть меньше максимального процента',
            'minmax_usd_error': 'Минимальная USD$ сумма должна быть больше нуля и меньше максимальной USD$ суммы',
            'minmax_delay_error': 'Минимальная задержка должна быть меньше или равна максимальной задержке',
            'decryption_error': 'Ошибка расшифровки или неверный пароль',
            'password_dialog_title': 'Введите Пароль',
            'password_dialog_message': 'Введите пароль, что бы расшифровать файл кошельков:',
            "decrypt_wallets_label": "Расшифровать кошельки",
            "gas_limit_label": "Лимит газа:",
            "configs_label": "Настройки конфигураций",
            "save_config_button": "Сохранить текущую конфигурацию",
            "select_configs_button": "Загрузить конфигурации"
        }
    }

    def __init__(self):
        super().__init__()
        self.config = Config()
        # logging
        self.logger = logging.getLogger('gui')
        self.logger.setLevel(level=logging.DEBUG)
        setup_gui_loging(logger=self.logger, callback=self._log)
        startnet_logger = logging.getLogger('starknet')
        startnet_logger.setLevel(level=logging.DEBUG)
        # setup_gui_loging(startnet_logger, callback=self._log)
        for logger in (self.logger, startnet_logger):
            setup_file_logging(logger=logger, log_file='default.log')
        handler = QtSignalLogHandler(signal=self.logger_signal)
        handler.setFormatter(log_formatter)
        startnet_logger.addHandler(handler)
        self.logger_signal.connect(self._log)
        self.worker_thread = None

        for lang in ('ru', 'en'):
            for bridge_name in self.bridges:
                self.messages[lang][f'min_eth_{bridge_name}_label'] = self.messages[lang]['min_eth_label']
                self.messages[lang][f'max_eth_{bridge_name}_label'] = self.messages[lang]['max_eth_label']
            for swap_name in self.swaps:
                self.messages[lang][f'min_price_{swap_name}_label'] = self.messages[lang]['min_price_label']
                self.messages[lang][f'max_price_{swap_name}_label'] = self.messages[lang]['max_price_label']
        self.widgets_tr = {}
        self.widgets_config = {}
        self.language = 'en'
        self.init_ui()
        self.retranslate_ui()
        self.load_config()
        self.trader = StarknetTrader(config=self.config, testnet=self.config.testnet)

    def load_config(self):
        self.config.load(self.CONFIG_FILENAME)
        for key in self.config.data['gui_config']:
            if key == "selected_configs_entry": continue
            value = self.config.data['gui_config'][key]
            if key not in self.widgets_config:
                continue
            widget = self.widgets_config[key]
            if isinstance(widget, QComboBox):
                widget.setCurrentIndex(value)
            elif isinstance(widget, QLineEdit):
                widget.setText(value)
            elif isinstance(widget, QCheckBox):
                widget.setChecked(value)
            else:
                widget.setValue(value)
        self.file_name = self.config.gui_config.file_name
        self.on_bridge_checkbox_clicked()

    def get_config(self, check_enabled_widget=False):
        gui_config = {}
        for key in self.widgets_config:
            widget = self.widgets_config[key]
            if isinstance(widget, QComboBox):
                value = widget.currentIndex()
            elif isinstance(widget, QLineEdit):
                value = widget.text()
            elif isinstance(widget, QCheckBox):
                if check_enabled_widget:
                    value = widget.isChecked() and widget.isEnabled()
                else:
                    value = widget.isChecked()
            else:
                value = widget.value()
            # self._log(f'{key}: {value}')
            gui_config[key] = value
        gui_config['file_name'] = self.file_name
        return gui_config

    def init_ui(self):
        layout = QVBoxLayout()
        bold_font = QFont()
        bold_font.setBold(True)

        language_layout = QHBoxLayout()
        language_label = QLabel()
        language_layout.addWidget(language_label)
        language_selector = QComboBox()
        language_selector.addItem("English")
        language_selector.addItem("Русский")
        language_selector.currentIndexChanged.connect(self.change_language)
        language_layout.addWidget(language_selector)
        layout.addLayout(language_layout)
        language_selector.setCurrentIndex(1)
        self.widgets_tr['language_label'] = language_label
        self.widgets_config['language_selector'] = language_selector

        api_key_layout = QHBoxLayout()
        api_key_label = QLabel()
        api_key_label.setOpenExternalLinks(True)
        # api_key_layout.addWidget(api_key_label)
        layout.addWidget(api_key_label)
        api_key_field = QLineEdit()
        # api_key_field.setText()
        api_key_field.setEchoMode(QLineEdit.Password)
        api_key_checkbox = QCheckBox()
        api_key_checkbox.setChecked(True)
        api_key_layout.addWidget(api_key_field)
        api_key_layout.addWidget(api_key_checkbox)
        layout.addLayout(api_key_layout)
        self.widgets_tr['api_key_label'] = api_key_label
        self.widgets_config['api_key'] = api_key_field
        self.widgets_tr['api_key_checkbox'] = api_key_checkbox
        api_key_checkbox.stateChanged.connect(self.on_hide_checkbox_changed)
        self.widgets_config['api_key_checkbox'] = api_key_checkbox

        private_keys_layout = QHBoxLayout()
        # private_keys_label = QLabel(self.tr("Ethereum private keys file:"))
        # private_keys_layout.addWidget(private_keys_label)
        select_file_button = QPushButton()
        select_file_button.clicked.connect(self.on_open_file_clicked)
        private_keys_layout.addWidget(select_file_button)
        layout.addLayout(private_keys_layout)
        # self.widgets_tr['private_keys_label'] = private_keys_label
        self.widgets_tr['select_file_button'] = select_file_button

        decrypt_layout = QHBoxLayout()
        decrypt_checkbox = QCheckBox("Decrypt wallets")
        decrypt_checkbox.setChecked(True)
        decrypt_layout.addWidget(decrypt_checkbox)
        gas_limit_layout = QHBoxLayout()
        gas_limit_label = QLabel("Gas limit: ")
        gas_limit_entry = QLineEdit("0")
        gas_limit_layout.addWidget(gas_limit_label)
        gas_limit_layout.addWidget(gas_limit_entry)
        layout.addLayout(decrypt_layout)
        layout.addLayout(gas_limit_layout)
        self.widgets_tr[f'decrypt_wallets_label'] = decrypt_checkbox
        self.widgets_tr[f'gas_limit_label'] = gas_limit_label
        self.widgets_config[f'decrypt_wallets_label'] = decrypt_checkbox
        self.widgets_config[f'gas_limit_entry'] = gas_limit_entry

        mh = 22
        configs_label = QLabel()
        configs_label.setFont(bold_font)
        layout.addWidget(configs_label)
        configs_layout = QVBoxLayout()
        save_config_button = QPushButton()
        save_config_button.setMinimumHeight(mh)
        save_config_button.clicked.connect(self.save_config_pressed)
        configs_layout.addWidget(save_config_button)
        select_configs_layout = QHBoxLayout()
        selected_configs_entry = QLineEdit()
        selected_configs_entry.setMinimumWidth(100)
        selected_configs_entry.setReadOnly(True)
        selected_configs_entry.setMinimumHeight(mh)
        select_configs_layout.addWidget(selected_configs_entry)
        select_configs_button = QPushButton()
        select_configs_button.setMinimumHeight(mh)
        select_configs_button.clicked.connect(self.on_select_configs_clicked)
        select_configs_layout.addWidget(select_configs_button)
        configs_layout.addLayout(select_configs_layout)
        use_configs_checkbox = QCheckBox("Use selected configurations")
        configs_layout.addWidget(use_configs_checkbox)
        configs_delay_layout = QHBoxLayout()
        configs_delay_label = QLabel("Delay between configurations from")
        configs_delay_from = QLineEdit("1")
        configs_delay_from.setFixedWidth(50)
        configs_delay_to_label = QLabel("to")
        configs_delay_to = QLineEdit("5")
        configs_delay_to.setFixedWidth(50)
        repeat_count_label = QLabel("repeat count: ")
        repeat_count = QLineEdit("1")
        repeat_count.setFixedWidth(50)
        configs_delay_layout.addWidget(configs_delay_label)
        configs_delay_layout.addWidget(configs_delay_from)
        configs_delay_layout.addWidget(configs_delay_to_label)
        configs_delay_layout.addWidget(configs_delay_to)
        configs_delay_layout.addWidget(repeat_count_label)
        configs_delay_layout.addWidget(repeat_count)
        configs_delay_layout.addStretch()
        configs_layout.addLayout(configs_delay_layout)
        layout.addLayout(configs_layout)
        self.widgets_config['selected_configs_entry'] = selected_configs_entry
        self.widgets_config['use_configs_checkbox'] = use_configs_checkbox
        self.widgets_config['delay_from'] = configs_delay_from
        self.widgets_config['delay_to'] = configs_delay_to
        self.widgets_config['repeat_count'] = repeat_count
        self.widgets_tr['select_configs_button'] = select_configs_button
        self.widgets_tr['use_configs_checkbox'] = use_configs_checkbox
        self.widgets_tr['save_config_button'] = save_config_button
        self.widgets_tr['configs_label'] = configs_label




        # starknet_seed_layout = QHBoxLayout()
        # self.starknet_seed_label = QLabel("Starknet seed file:")
        # starknet_seed_layout.addWidget(self.starknet_seed_label)
        # self.select_starknet_button = QPushButton("Select File")
        # self.select_starknet_button.clicked.connect(self.on_open_file_clicked)
        # starknet_seed_layout.addWidget(self.select_starknet_button)
        # layout.addLayout(starknet_seed_layout)

        layout.addWidget(QSplitter())

        bridges_label = QLabel()
        bridges_label.setFont(bold_font)
        layout.addWidget(bridges_label)
        self.widgets_tr['bridges_label'] = bridges_label

        for key in self.bridges:
            bridge_layout = QHBoxLayout()
            bridge_checkbox = QCheckBox(self.bridges[key]['name'])
            # bridge_checkbox.setChecked(False)
            bridge_checkbox.clicked.connect(self.on_bridge_checkbox_clicked)
            bridge_layout.addWidget(bridge_checkbox)
            bridge_dropdown = QComboBox()
            for network in self.bridges[key]['networks']:
                bridge_dropdown.addItem(network)
            bridge_layout.addWidget(bridge_dropdown)
            min_label = QLabel()
            max_label = QLabel()
            min_eth_selector = QDoubleSpinBox(decimals=4, stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            max_eth_selector = QDoubleSpinBox(decimals=4, stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            bridge_layout.addWidget(min_label)
            bridge_layout.addWidget(min_eth_selector)
            bridge_layout.addWidget(max_label)
            bridge_layout.addWidget(max_eth_selector)
            bridge_layout.setStretch(0, 1)
            bridge_layout.setStretch(1, 1)
            self.widgets_tr[f'min_eth_{key}_label'] = min_label
            self.widgets_tr[f'max_eth_{key}_label'] = max_label
            self.widgets_config[f'bridge_{key}_checkbox'] = bridge_checkbox
            self.widgets_config[f'bridge_{key}_network'] = bridge_dropdown
            self.widgets_config[f'min_eth_{key}_selector'] = min_eth_selector
            self.widgets_config[f'max_eth_{key}_selector'] = max_eth_selector
            self.bridges[key]['checkbox'] = bridge_checkbox
            self.bridges[key]['min_eth'] = min_eth_selector
            self.bridges[key]['max_eth'] = max_eth_selector
            layout.addLayout(bridge_layout)

        layout.addWidget(QSplitter())
        back_bridges_label = QLabel()
        back_bridges_label.setFont(bold_font)
        layout.addWidget(back_bridges_label)
        self.widgets_tr['back_bridges_label'] = back_bridges_label

        for key in self.back_bridges:
            back_bridge_layout = QHBoxLayout()
            back_bridge_checkbox = QCheckBox(self.back_bridges[key]['name'])
            back_bridge_layout.addWidget(back_bridge_checkbox)
            back_bridge_dropdown = QComboBox()
            for network in self.back_bridges[key]['networks']:
                back_bridge_dropdown.addItem(network)
            back_bridge_layout.addWidget(back_bridge_dropdown)
            min_percent_label = QLabel()
            max_percent_label = QLabel()
            min_percent_selector = QSpinBox()
            min_percent_selector.setRange(1, 100)
            max_percent_selector = QSpinBox()
            max_percent_selector.setRange(1, 100)
            back_bridge_layout.addWidget(min_percent_label)
            back_bridge_layout.addWidget(min_percent_selector)
            back_bridge_layout.addWidget(max_percent_label)
            back_bridge_layout.addWidget(max_percent_selector)
            back_bridge_layout.setStretch(0, 1)
            back_bridge_layout.setStretch(1, 1)
            self.widgets_tr[f'min_percent_{key}_label'] = min_percent_label
            self.widgets_tr[f'max_percent_{key}_label'] = max_percent_label
            self.widgets_config[f'back_bridge_{key}_checkbox'] = back_bridge_checkbox
            self.widgets_config[f'back_bridge_{key}_network'] = back_bridge_dropdown
            self.widgets_config[f'min_percent_{key}_selector'] = min_percent_selector
            self.widgets_config[f'max_percent_{key}_selector'] = max_percent_selector
            self.back_bridges[key]['checkbox'] = back_bridge_checkbox
            self.back_bridges[key]['min_percent'] = min_percent_selector
            self.back_bridges[key]['max_percent'] = max_percent_selector
            layout.addLayout(back_bridge_layout)

        layout.addWidget(QSplitter())
        quests_label = QLabel()
        quests_label.setFont(bold_font)
        self.widgets_tr['quests_label'] = quests_label
        layout.addWidget(quests_label)

        for key in self.swaps:
            quest_layout = QHBoxLayout()
            swap_checkbox = QCheckBox(self.swaps[key]['name'])
            swap_checkbox.setChecked(True)
            quest_layout.addWidget(swap_checkbox)
            min_price_label = QLabel(self.tr('min $:'))
            quest_layout.addWidget(min_price_label)
            min_eth_selector = QDoubleSpinBox(stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            min_eth_selector.setRange(0, 10000)
            quest_layout.addWidget(min_eth_selector)
            max_price_label = QLabel(self.tr('max $:'))
            quest_layout.addWidget(max_price_label)
            max_eth_selector = QDoubleSpinBox(stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            max_eth_selector.setRange(0, 10000)
            quest_layout.addWidget(max_eth_selector)
            quest_layout.setStretch(0, 1)
            quest_layout.setStretch(2, 1)
            quest_layout.setStretch(4, 1)
            self.widgets_tr[f'min_price_{key}_label'] = min_price_label
            self.widgets_tr[f'max_price_{key}_label'] = max_price_label
            self.widgets_config[f'min_price_{key}_selector'] = min_eth_selector
            self.widgets_config[f'max_price_{key}_selector'] = max_eth_selector
            self.widgets_config[f'swap_{key}_checkbox'] = swap_checkbox
            self.swaps[key]['checkbox'] = swap_checkbox
            self.swaps[key]['min_price'] = min_eth_selector
            self.swaps[key]['max_price'] = max_eth_selector
            layout.addLayout(quest_layout)

        random_swap_checkbox = QCheckBox()
        self.widgets_tr['random_swap_checkbox'] = random_swap_checkbox
        self.widgets_config['random_swap_checkbox'] = random_swap_checkbox
        layout.addWidget(random_swap_checkbox)

        layout.addWidget(QSplitter())
        backswaps_label = QLabel()
        backswaps_label.setFont(bold_font)
        self.widgets_tr['backswaps_label'] = backswaps_label
        layout.addWidget(backswaps_label)

        backswaps_checkbox = QCheckBox()
        layout.addWidget(backswaps_checkbox)
        self.widgets_tr['backswaps_checkbox'] = backswaps_checkbox
        self.widgets_config['backswaps_checkbox'] = backswaps_checkbox
        backswaps_layout = QHBoxLayout()
        self.widgets_tr['backswaps_count_label'] = QLabel()
        self.widgets_tr['backswaps_usd_label'] = QLabel()
        backswaps_count_spinbox = QSpinBox()
        backswaps_count_spinbox.setRange(0, 1000)
        self.widgets_config['backswaps_count_spinbox'] = backswaps_count_spinbox
        backswaps_usd_spinbox = QDoubleSpinBox(stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        backswaps_usd_spinbox.setRange(0, 10000)
        self.widgets_config['backswaps_usd_spinbox'] = backswaps_usd_spinbox
        backswaps_layout.addWidget(self.widgets_tr['backswaps_count_label'])
        backswaps_layout.addWidget(backswaps_count_spinbox)
        backswaps_layout.addWidget(self.widgets_tr['backswaps_usd_label'])
        backswaps_layout.addWidget(backswaps_usd_spinbox)
        layout.addLayout(backswaps_layout)

        layout.addWidget(QSplitter())
        options_label = QLabel()
        options_label.setFont(bold_font)
        self.widgets_tr['options_label'] = options_label
        layout.addWidget(options_label)

        for option_name in ('wallet_delay', 'project_delay'):
            options_layout = QHBoxLayout()
            options_1_label = QLabel()
            min_option_1_label = QLabel()
            min_option_1_selector = QSpinBox()
            min_option_1_selector.setRange(0, 10000)
            # min_option_1_selector.setValue(60)
            max_option_1_label = QLabel()
            max_option_1_selector = QSpinBox()
            max_option_1_selector.setRange(0, 10000)
            # max_option_1_selector.setValue(120)
            options_layout.addWidget(options_1_label)
            options_layout.addWidget(min_option_1_label)
            options_layout.addWidget(min_option_1_selector)
            options_layout.addWidget(max_option_1_label)
            options_layout.addWidget(max_option_1_selector)
            options_layout.setStretch(0, 1)
            options_layout.setStretch(2, 1)
            options_layout.setStretch(4, 1)
            self.widgets_tr[f'{option_name}_label'] = options_1_label
            self.widgets_tr[f'{option_name}_min_sec_label'] = min_option_1_label
            self.widgets_tr[f'{option_name}_max_sec_label'] = max_option_1_label
            self.widgets_config[f'{option_name}_min_sec'] = min_option_1_selector
            self.widgets_config[f'{option_name}_max_sec'] = max_option_1_selector
            layout.addLayout(options_layout)

        shuffle_checkbox = QCheckBox('Shuffle wallets')
        self.widgets_config['shuffle_checkbox'] = shuffle_checkbox
        self.widgets_tr['shuffle_checkbox'] = shuffle_checkbox
        layout.addWidget(shuffle_checkbox)

        layout.addWidget(QSplitter())

        button_layout = QHBoxLayout()
        self.widgets_tr['start_button'] = QPushButton()
        self.widgets_tr['start_button'].clicked.connect(self.on_start_clicked)
        self.widgets_tr['stop_button'] = QPushButton()
        self.widgets_tr['stop_button'].setDisabled(True)
        self.widgets_tr['stop_button'].clicked.connect(self.on_stop_clicked)
        self.widgets_tr['pause_button'] = QPushButton()
        self.widgets_tr['pause_button'].setDisabled(True)
        self.widgets_tr['pause_button'].clicked.connect(self.on_pause_clicked)
        button_layout.addWidget(self.widgets_tr['start_button'])
        button_layout.addWidget(self.widgets_tr['pause_button'])
        button_layout.addWidget(self.widgets_tr['stop_button'])
        layout.addLayout(button_layout)

        # Add a big text field for logs
        # self.log_text_edit = MyQTextEdit()
        # self.log_text_edit = QTextEdit()
        self.log_text_edit = QTextBrowser()
        self.log_text_edit.setOpenLinks(False)
        self.log_text_edit.anchorClicked.connect(self.handle_links)

        self.log_text_edit.setReadOnly(True)
        layout.addWidget(self.log_text_edit)

        central_widget = QWidget()
        central_widget.setLayout(layout)
        self.setCentralWidget(central_widget)

        # Actions
        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        self.addAction(exit_action)

        open_file_action = QAction('Open File', self)
        open_file_action.setShortcut('Ctrl+O')
        open_file_action.triggered.connect(self.on_open_file_clicked)
        self.addAction(open_file_action)

    def change_language(self, index):
        languages = ["en", "ru"]
        self.language = languages[index]
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.tr(self.messages[self.language].get('window_title')))
        for widget_name in self.widgets_tr:
            if widget_name not in self.messages[self.language]:
                continue
            # if widget_name.endswith('_label') or widget_name.endswith('_button'):
            self.widgets_tr[widget_name].setText(self.tr(self.messages[self.language][widget_name]))

    def _log(self, message):
        self.log_line += 1
        message = convert_urls_to_links(message)
        if self.widgets_config['api_key_checkbox'].isChecked():
            message = mask_hex_in_string(message)
        # self.log_text_edit.append(f'{self.log_line}. {message}')
        # self.log_text_edit.verticalScrollBar().setValue(self.log_text_edit.verticalScrollBar().maximum())
        self.log_text_edit.moveCursor(QTextCursor.End)
        self.log_text_edit.insertHtml(f'{self.log_line}. {message}<br>')
        scroll = self.log_text_edit.verticalScrollBar()
        scroll.setValue(scroll.maximum())
        # time.sleep(0.01)

    def show_error_message(self, message):
        alert = QMessageBox()
        alert.setIcon(QMessageBox.Warning)
        alert.setWindowTitle(self.tr("Error"))
        alert.setText(message)
        alert.exec_()

    def on_start_clicked(self):
        conf = self.get_config(check_enabled_widget=True)
        self.process_start(conf)

    def process_start(self, conf):
        self.logger.info('START button clicked')
        if not conf['api_key']:
            self.show_error_message(self.messages[self.language]['apikey_error'])
            return
        try:
            degensoft_api = DegenSoftApiClient(api_key=conf['api_key'])
            user_info = degensoft_api.get_userinfo()
            self.logger.info(f'API Username: {user_info["user"]}, Points: {user_info["points"]}, '
                             f'Premium points: {user_info["prem_points"]}')
        except Exception as ex:
            self.show_error_message(self.messages[self.language]['api_error'] + str(ex))
            return
        if not conf['file_name']:
            self.show_error_message(self.messages[self.language]['file_error'])
            return
        for key in self.bridges:
            if conf[f'bridge_{key}_checkbox'] and not (
                    0 < conf[f'min_eth_{key}_selector'] <= conf[f'max_eth_{key}_selector']):
                self.show_error_message(self.messages[self.language]['minmax_eth_error'])
                return
        for key in self.back_bridges:
            if conf[f'back_bridge_{key}_checkbox'] and not (
                    0 < conf[f'min_percent_{key}_selector'] <= conf[f'max_percent_{key}_selector']):
                self.show_error_message(self.messages[self.language]['minmax_percent_error'])
                return
        for key in self.swaps:
            if conf[f'swap_{key}_checkbox'] and not (0 < conf[f'min_price_{key}_selector'] <= conf[f'max_price_{key}_selector']):
                self.show_error_message(self.messages[self.language]['minmax_usd_error'])
                return
        for key in ('wallet_delay', 'project_delay'):
            if conf[f'{key}_min_sec'] != 0 and conf[f'{key}_min_sec'] > conf[f'{key}_max_sec']:
                self.show_error_message(self.messages[self.language]['minmax_delay_error'])
                return
        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.logger.error('Worker is already running.. please wait')
            return
        conf['gas_limit'] = float(self.widgets_config['gas_limit_entry'].text())
        try:
            filereader = UniversalFileReader(conf['file_name'])
            filereader.load()
            if filereader.is_encrypted() and self.widgets_config['decrypt_wallets_label'].isChecked():
                dialog = PasswordDialog(language=self.language, messages=self.messages)
                result = dialog.exec_()
                if not (result and dialog.lineEdit.text()):
                    self.logger.error('You must enter password')
                    return
                try:
                    filereader.decrypt(dialog.lineEdit.text())
                except Exception:
                    return self.show_error_message(self.messages[self.language]['decryption_error'])
            self.trader.load_private_keys(filereader.wallets)
        except Exception as ex:
            return self.show_error_message(self.messages[self.language]['csv_error'] + str(ex))
        self.widgets_tr['start_button'].setDisabled(True)
        self.widgets_tr['pause_button'].setDisabled(False)
        self.widgets_tr['stop_button'].setDisabled(False)
        configs = {}
        configs['use'] = self.widgets_config['use_configs_checkbox'].isChecked()
        configs['delay_from'] = float(self.widgets_config['delay_from'].text().strip())
        configs['delay_to'] = float(self.widgets_config['delay_to'].text().strip())
        if configs['use']:
            configs['repeat_count'] = int(self.widgets_config['repeat_count'].text() or 1)
            configs['file_names'] = self.config_file_names

        self.worker_thread = TraderThread(trader=self.trader, api=degensoft_api, config=conf, configs=configs,
                                          swaps=self.swaps, bridges=self.bridges, back_bridges=self.back_bridges)
        self.worker_thread.task_completed.connect(self.on_thread_task_completed)
        # self.worker_thread.logger_signal.connect(self._log)
        self.worker_thread.start()

    def on_thread_task_completed(self):
        self.widgets_tr['start_button'].setDisabled(False)
        self.widgets_tr['pause_button'].setDisabled(True)
        self.widgets_tr['stop_button'].setDisabled(True)
        self.logger.info('Task completed!')

    def on_pause_clicked(self):
        if not self.worker_thread.paused:
            self.logger.info('PAUSE button clicked')
            self.worker_thread.pause()
        else:
            self.logger.info('CONTINUE button clicked')
            self.worker_thread.resume()

    def on_stop_clicked(self):
        self.logger.info('STOP button clicked')
        self.worker_thread.stop()
        self.logger.info('Waiting for worker will be finished...')
        while self.worker_thread.isRunning():
            time.sleep(0.1)
        self.widgets_tr['start_button'].setDisabled(False)
        self.widgets_tr['pause_button'].setDisabled(True)
        self.widgets_tr['stop_button'].setDisabled(True)

    def on_hide_checkbox_changed(self):
        echo_mode = QLineEdit.Password if self.sender().isChecked() else QLineEdit.Normal
        self.widgets_config['api_key'].setEchoMode(echo_mode)

    def on_bridge_checkbox_clicked(self):
        for key in self.bridges:
            if self.bridges[key]['checkbox'].isChecked():
                self._set_swap_checkboxes(disabled=True)
                return
        self._set_swap_checkboxes(disabled=False)

    def _set_swap_checkboxes(self, disabled: bool):
        for key in self.swaps:
            self.swaps[key]['checkbox'].setDisabled(disabled)
        self.widgets_config['random_swap_checkbox'].setDisabled(disabled)

    def on_open_file_clicked(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*);;Text Files (*.txt)",
                                                   options=options)
        if file_name:
            self.file_name = file_name
            self.logger.debug(f'File selected: {file_name}')

    def save_config_pressed(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileName, _ = QFileDialog.getSaveFileName(self, "Save File", "", "All Files(*);;JSON Files(*.json)",
                                                  options=options)
        if fileName:
            cfg = self.get_config()
            cfg.pop("api_key")
            cfg.pop("decrypt_wallets_label")
            cfg.pop("file_name")
            cfg.pop("selected_configs_entry")
            to_save = {"gui_config": cfg, "config_type": "additional"}
            json.dump(to_save, open(fileName, "w", encoding='utf-8'), ensure_ascii=False)
            self.logger.info("Config has been successfully saved")

    def on_select_configs_clicked(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getOpenFileNames(self, "Select configs", "", "All Files (*);;JSON Files (*.json)",
                                                   options=options)
        if file_name:
            self.config_file_names = file_name
            self.logger.debug(f'Config files selected: {" ".join(file_name)}')
            self.widgets_config['selected_configs_entry'].setText(", ".join(list(map(lambda x: os.path.basename(x), file_name))))

    def closeEvent(self, event):
        self.config.gui_config = self.get_config(check_enabled_widget=True)
        self.config.save(self.CONFIG_FILENAME)

    def handle_links(self, url):
        QDesktopServices.openUrl(url)


def main():
    app = QApplication(sys.argv)
    # app.setStyle(QStyleFactory.create('Windows'))
    main_window = MainWindow()
    main_window.setMinimumSize(600, 700)
    frame_geometry = main_window.frameGeometry()
    center_point = QDesktopWidget().availableGeometry().center()
    frame_geometry.moveCenter(center_point)
    main_window.move(frame_geometry.topLeft())
    main_window.show()
    sys.exit(app.exec_())
