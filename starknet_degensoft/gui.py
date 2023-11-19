import json
import logging
import os
import sys
import time

from PyQt5.Qt import QDesktopServices, QUrl, Qt, QTextCursor
from PyQt5.QtCore import pyqtSignal, QMetaObject
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox, QPushButton, \
    QTextEdit, QLabel, QLineEdit, QAction, QWidget, QDesktopWidget, QFileDialog, \
    QDoubleSpinBox, QSpinBox, QAbstractSpinBox, QMessageBox, QTextBrowser, QDialog, QDialogButtonBox, \
    QTabWidget, QSpacerItem, QSizePolicy, QGridLayout, QRadioButton

from degensoft.filereader import UniversalFileReader
from starknet_degensoft.api_client2 import DegenSoftApiClient
from starknet_degensoft.config import Config
from starknet_degensoft.layerswap import LayerswapBridge
from starknet_degensoft.starkgate import StarkgateBridge
from starknet_degensoft.starknet_swap import MyswapSwap, TenKSwap, JediSwap, SithSwap, AvnuSwap, FibrousSwap
from starknet_degensoft.starknet_trader import StarknetTrader, TraderThread
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
        'myswap': {'name': 'MySwap.xyz', 'cls': MyswapSwap},
        '10kswap': {'name': '10kSwap', 'cls': TenKSwap},
        'jediswap': {'name': 'JediSwap', 'cls': JediSwap},
        'sithswap': {'name': 'SithSwap', 'cls': SithSwap},
        'avnuswap': {'name': 'Avnu', 'cls': AvnuSwap},
        'fibrous': {'name': 'Fibrous', 'cls': FibrousSwap},
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
            'quests_label': "Select projects",
            'backswaps_label': "Back swap tokens to ETH",
            'backswaps_checkbox': "Make swap tokens to ETH",
            'backswaps_usd_label': "Minimum token USD price:",
            'backswaps_count_label': "Amount of swaps (random tokens):",
            'project_settings_label': "Swap settings",
            'slippage_label': "Maximum slippage, %:",
            'rest_label': "Keep amount on the balance, $",
            'options_label': "Options",
            'wallet_delay_label': "Wallet delay",
            'project_delay_label': "Project delay",
            'wallet_delay_min_sec_label': "min sec:",
            'project_delay_min_sec_label': "min sec:",
            'wallet_delay_max_sec_label': "max sec:",
            'project_delay_max_sec_label': "max sec:",
            'random_swap_checkbox': "Random project (from selected above)",
            'min_eth_label': "min ETH:",
            'max_eth_label': "max ETH:",
            'amount_type_label': "Select amount in:",
            'amount_percent': "percent, %",
            'amount_dollars': "USD, $",
            'min_price_label': "Minimum amount, $:",
            'max_price_label': "Maximum amount, $:",
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
            'configs_error': 'You must select config files',
            'password_dialog_title': 'Enter Password',
            'password_dialog_message': 'Enter password to decrypt wallets file:',
            "decrypt_wallets_label": "Decrypt wallets",
            "gas_limit_label": "Gas limit:",
            "configs_label": "Configuration options",
            "save_config_button": "Save current configuration",
            "select_configs_button": "Load configurations",
            "delay_from": "Delay between configurations from",
            "delay_to": "to",
            "repeat_count": "repeat count: ",
            "use_configs_checkbox": "Use selected configurations",
            "gas_limit_checkbox": "Ethereum Gas limit",
            "settings_tab": "Settings",
            "projects_tab": "Swaps",
            "bridges_tab": "Bridges",
            "logs_tab": "Logs",
        },
        'ru': {
            'window_title': "Starknet [DEGENSOFT]",
            'language_label': "Язык",
            'api_key_label': "API ключ (вы можете получить его через <a href='http://t.me/degensoftbot'>@DegenSoftBot</a>)",
            'api_key_checkbox': "скрыть",
            'private_keys_label': "Файл приватных ключей",
            'bridges_label': "Выберите мост и сеть в которой у вас есть ETH для перевода в Starknet",
            'back_bridges_label': "Выберите мост и сеть в которую переводить ETH из Starknet",
            'quests_label': "Выберите проекты",
            'backswaps_label': "Обмен токенов обратно в ETH",
            'backswaps_checkbox': "Сделать свап токенов в ETH",
            'backswaps_usd_label': "Минимальная цена токена в USD:",
            'backswaps_count_label': "Количество свапов в ETH (рандомный выбор токенов):",
            'project_settings_label': "Настройки свапов",
            'slippage_label': "Максимальное проскальзывание (slippage), %:",
            'rest_label': "Оставить сумму на балансе, $",
            'options_label': "Настройки",
            'wallet_delay_label': "Задержка между кошельками",
            'project_delay_label': "Задержка между проектами",
            'wallet_delay_min_sec_label': "мин сек:",
            'project_delay_min_sec_label': "мин сек:",
            'wallet_delay_max_sec_label': "макс сек:",
            'project_delay_max_sec_label': "макс сек:",
            'random_swap_checkbox': "Рандомный проект (из отмеченных выше)",
            'min_eth_label': "мин ETH:",
            'max_eth_label': "макс ETH:",
            'min_price_label': "Минимальная сумма, $:",
            'max_price_label': "Максимальная сумма, $:",
            'amount_type_label': "Выберите сумму в:",
            'amount_percent': "процентах, %",
            'amount_dollars': "долларах, $",
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
            'configs_error': 'Вы должны выбрать файлы конфигураций',
            'password_dialog_title': 'Введите Пароль',
            'password_dialog_message': 'Введите пароль, что бы расшифровать файл кошельков:',
            "decrypt_wallets_label": "Расшифровать кошельки",
            "gas_limit_label": "Лимит газа:",
            "configs_label": "Настройки конфигураций",
            "save_config_button": "Сохранить текущую конфигурацию",
            "select_configs_button": "Загрузить конфигурации",
            "delay_from": "Задержка между конфигурациями от",
            "delay_to": "до",
            "repeat_count": "количество повторений: ",
            "use_configs_checkbox": "Использовать выбранные конфигурации",
            "gas_limit_checkbox": "Ethereum лимит газа",
            "settings_tab": "Настройки",
            "projects_tab": "Свапы",
            "bridges_tab": "Мосты",
            "logs_tab": "Логи",
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
            # for swap_name in self.swaps:
            #     self.messages[lang][f'min_price_{swap_name}_label'] = self.messages[lang]['min_price_label']
            #     self.messages[lang][f'max_price_{swap_name}_label'] = self.messages[lang]['max_price_label']
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
            elif isinstance(widget, QCheckBox) or isinstance(widget, QRadioButton):
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
            elif isinstance(widget, QCheckBox) or isinstance(widget, QRadioButton):
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
        main_layout = QVBoxLayout()
        self.tab_widget = QTabWidget()

        settings_tab = QWidget()
        logs_tab = QWidget()
        projects_tab = QWidget()
        bridges_tab = QWidget()
        self.projects_tab = projects_tab
        self.bridges_tab = bridges_tab

        projects_layout = QVBoxLayout()
        projects_tab.setLayout(projects_layout)
        bridges_tab_layout = QVBoxLayout()
        bridges_tab.setLayout(bridges_tab_layout)
        settings_layout = QVBoxLayout()
        settings_tab.setLayout(settings_layout)
        log_layout = QVBoxLayout()
        logs_tab.setLayout(log_layout)

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
        settings_layout.addLayout(language_layout)
        language_selector.setCurrentIndex(1)
        self.widgets_tr['language_label'] = language_label
        self.widgets_config['language_selector'] = language_selector

        api_key_layout = QHBoxLayout()
        api_key_label = QLabel()
        api_key_label.setOpenExternalLinks(True)
        settings_layout.addWidget(api_key_label)
        api_key_field = QLineEdit()
        api_key_field.setEchoMode(QLineEdit.Password)
        api_key_checkbox = QCheckBox()
        api_key_checkbox.setChecked(True)
        api_key_layout.addWidget(api_key_field)
        api_key_layout.addWidget(api_key_checkbox)
        settings_layout.addLayout(api_key_layout)
        self.widgets_tr['api_key_label'] = api_key_label
        self.widgets_config['api_key'] = api_key_field
        self.widgets_tr['api_key_checkbox'] = api_key_checkbox
        api_key_checkbox.stateChanged.connect(self.on_hide_checkbox_changed)
        self.widgets_config['api_key_checkbox'] = api_key_checkbox

        private_keys_layout = QHBoxLayout()
        select_file_button = QPushButton()
        select_file_button.clicked.connect(self.on_open_file_clicked)
        private_keys_layout.addWidget(select_file_button)
        settings_layout.addLayout(private_keys_layout)
        self.widgets_tr['select_file_button'] = select_file_button

        decrypt_layout = QHBoxLayout()
        decrypt_checkbox = QCheckBox("Decrypt wallets")
        decrypt_checkbox.setChecked(True)
        decrypt_layout.addWidget(decrypt_checkbox)
        settings_layout.addLayout(decrypt_layout)
        self.widgets_tr['decrypt_wallets_label'] = decrypt_checkbox
        self.widgets_config['decrypt_wallets_label'] = decrypt_checkbox

        gas_limit_layout = QHBoxLayout()
        gas_limit_checkbox = QCheckBox("Ethereum gas limit")
        # gas_limit_checkbox.setChecked(False)
        gas_limit_spinner = QSpinBox()
        gas_limit_spinner.setRange(1, 1000)
        gas_limit_gwei_label = QLabel('gwei')
        gas_limit_layout.addWidget(gas_limit_checkbox)
        gas_limit_layout.addWidget(gas_limit_spinner)
        gas_limit_layout.addWidget(gas_limit_gwei_label, 1)
        self.widgets_config['gas_limit_spinner'] = gas_limit_spinner
        self.widgets_config['gas_limit_checkbox'] = gas_limit_checkbox
        self.widgets_tr['gas_limit_checkbox'] = gas_limit_checkbox
        settings_layout.addLayout(gas_limit_layout)

        mh = 22
        configs_label = QLabel()
        configs_label.setFont(bold_font)
        settings_layout.addWidget(configs_label)
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
        settings_layout.addLayout(configs_layout)
        self.widgets_config['selected_configs_entry'] = selected_configs_entry
        self.widgets_config['use_configs_checkbox'] = use_configs_checkbox
        self.widgets_config['delay_from'] = configs_delay_from
        self.widgets_config['delay_to'] = configs_delay_to
        self.widgets_config['repeat_count'] = repeat_count
        self.widgets_tr['select_configs_button'] = select_configs_button
        self.widgets_tr['use_configs_checkbox'] = use_configs_checkbox
        self.widgets_tr['save_config_button'] = save_config_button
        self.widgets_tr['configs_label'] = configs_label
        self.widgets_tr['delay_from'] = configs_delay_label
        self.widgets_tr['delay_to'] = configs_delay_to_label
        self.widgets_tr['repeat_count'] = repeat_count_label
        use_configs_checkbox.stateChanged.connect(self.on_use_configs_changed)

        bridges_label = QLabel()
        bridges_label.setFont(bold_font)
        bridges_tab_layout.addWidget(bridges_label)
        self.widgets_tr['bridges_label'] = bridges_label

        for key in self.bridges:
            bridges_layout = QHBoxLayout()
            bridge_checkbox = QCheckBox(self.bridges[key]['name'])
            # bridge_checkbox.setChecked(False)
            bridge_checkbox.clicked.connect(self.on_bridge_checkbox_clicked)
            bridges_layout.addWidget(bridge_checkbox)
            bridge_dropdown = QComboBox()
            for network in self.bridges[key]['networks']:
                bridge_dropdown.addItem(network)
            bridges_layout.addWidget(bridge_dropdown)
            min_label = QLabel()
            max_label = QLabel()
            min_price_selector = QDoubleSpinBox(decimals=4, stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            max_price_selector = QDoubleSpinBox(decimals=4, stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            bridges_layout.addWidget(min_label)
            bridges_layout.addWidget(min_price_selector)
            bridges_layout.addWidget(max_label)
            bridges_layout.addWidget(max_price_selector)
            bridges_layout.setStretch(0, 1)
            bridges_layout.setStretch(1, 1)
            self.widgets_tr[f'min_eth_{key}_label'] = min_label
            self.widgets_tr[f'max_eth_{key}_label'] = max_label
            self.widgets_config[f'bridge_{key}_checkbox'] = bridge_checkbox
            self.widgets_config[f'bridge_{key}_network'] = bridge_dropdown
            self.widgets_config[f'min_eth_{key}_selector'] = min_price_selector
            self.widgets_config[f'max_eth_{key}_selector'] = max_price_selector
            self.bridges[key]['checkbox'] = bridge_checkbox
            self.bridges[key]['min_eth'] = min_price_selector
            self.bridges[key]['max_eth'] = max_price_selector
            bridges_tab_layout.addLayout(bridges_layout)

        # projects_layout.addWidget(QSplitter())
        back_bridges_label = QLabel()
        back_bridges_label.setFont(bold_font)
        bridges_tab_layout.addWidget(back_bridges_label)
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
            bridges_tab_layout.addLayout(back_bridge_layout)

        quests_label = QLabel()
        quests_label.setFont(bold_font)
        self.widgets_tr['quests_label'] = quests_label
        projects_layout.addWidget(quests_label)

        for key in self.swaps:
            quest_layout = QHBoxLayout()
            swap_checkbox = QCheckBox(self.swaps[key]['name'])
            swap_checkbox.setChecked(True)
            quest_layout.addWidget(swap_checkbox)
            self.widgets_config[f'swap_{key}_checkbox'] = swap_checkbox
            self.swaps[key]['checkbox'] = swap_checkbox
            projects_layout.addLayout(quest_layout)

        random_swap_checkbox = QCheckBox()
        self.widgets_tr['random_swap_checkbox'] = random_swap_checkbox
        self.widgets_config['random_swap_checkbox'] = random_swap_checkbox
        projects_layout.addWidget(random_swap_checkbox)

        backswaps_label = QLabel()
        backswaps_label.setFont(bold_font)
        self.widgets_tr['backswaps_label'] = backswaps_label
        projects_layout.addWidget(backswaps_label)

        backswaps_checkbox = QCheckBox()
        projects_layout.addWidget(backswaps_checkbox)
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
        projects_layout.addLayout(backswaps_layout)

        # swap settings
        amount_type_layout = QHBoxLayout()
        amount_type_label = QLabel()
        amount_type_layout.addWidget(amount_type_label)
        amount_percent_button = QRadioButton()
        amount_type_layout.addWidget(amount_percent_button)
        amount_dollars_button = QRadioButton()
        amount_dollars_button.setChecked(True)
        amount_type_layout.addWidget(amount_dollars_button)
        spacer3 = QSpacerItem(100, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        amount_type_layout.addItem(spacer3)
        self.widgets_tr['amount_type_label'] = amount_type_label
        self.widgets_tr['amount_dollars'] = self.widgets_config['amount_dollars'] = amount_dollars_button
        self.widgets_tr['amount_percent'] = self.widgets_config['amount_percent'] = amount_percent_button
        amount_dollars_button.toggled.connect(self.change_price_type)

        project_settings_label = QLabel()
        project_settings_label.setFont(bold_font)
        self.widgets_tr['project_settings_label'] = project_settings_label
        projects_layout.addWidget(project_settings_label)
        projects_layout.addLayout(amount_type_layout)

        # swap range settings
        swap_settings_layout = QGridLayout()
        spacer_ = QSpacerItem(300, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        projects_layout.addLayout(swap_settings_layout)

        min_price_label = QLabel()
        min_price_selector = QDoubleSpinBox(stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        min_price_selector.setRange(0, 10000)
        max_price_label = QLabel()
        max_price_selector = QDoubleSpinBox(stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        max_price_selector.setRange(0, 10000)
        swap_settings_layout.addWidget(min_price_label, 0, 0, 1, 1)
        swap_settings_layout.addWidget(min_price_selector, 0, 1, 1, 1)
        swap_settings_layout.addWidget(max_price_label, 1, 0, 1, 1)
        swap_settings_layout.addWidget(max_price_selector, 1, 1, 1, 1)
        self.widgets_tr['min_price_label'] = min_price_label
        self.widgets_tr['max_price_label'] = max_price_label
        self.widgets_config['min_price_selector'] = min_price_selector
        self.widgets_config['max_price_selector'] = max_price_selector
        swap_settings_layout.addItem(spacer_, 0, 2, 1, 1)

        # slippage setting
        slippage_label = QLabel()
        self.widgets_tr['slippage_label'] = slippage_label
        slippage_spinbox = QDoubleSpinBox(stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        slippage_spinbox.setRange(0.1, 50.0)
        self.widgets_config['slippage_spinbox'] = slippage_spinbox
        swap_settings_layout.addWidget(slippage_label, 2, 0, 1, 1)
        swap_settings_layout.addWidget(slippage_spinbox, 2, 1, 1, 1)

        rest_label = QLabel()
        self.widgets_tr['rest_label'] = rest_label
        rest_spinbox = QDoubleSpinBox(stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
        rest_spinbox.setRange(0, 99999)
        self.widgets_config['rest_spinbox'] = rest_spinbox
        swap_settings_layout.addWidget(rest_label, 3, 0, 1, 1)
        swap_settings_layout.addWidget(rest_spinbox, 3, 1, 1, 1)

        options_label = QLabel()
        options_label.setFont(bold_font)
        self.widgets_tr['options_label'] = options_label
        settings_layout.addWidget(options_label)

        for option_name in ('wallet_delay', 'project_delay'):
            options_layout = QHBoxLayout()
            options_1_label = QLabel()
            min_option_1_label = QLabel()
            min_option_1_selector = QSpinBox()
            min_option_1_selector.setRange(0, 100000)
            # min_option_1_selector.setValue(60)
            max_option_1_label = QLabel()
            max_option_1_selector = QSpinBox()
            max_option_1_selector.setRange(0, 100000)
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
            settings_layout.addLayout(options_layout)

        shuffle_checkbox = QCheckBox('Shuffle wallets')
        self.widgets_config['shuffle_checkbox'] = shuffle_checkbox
        self.widgets_tr['shuffle_checkbox'] = shuffle_checkbox
        settings_layout.addWidget(shuffle_checkbox)
        # projects_layout.addWidget(QSplitter())

        main_layout.addWidget(self.tab_widget)

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
        main_layout.addLayout(button_layout)

        # Add a big text field for logs
        self.log_text_edit = QTextBrowser()
        self.log_text_edit.setOpenLinks(False)
        self.log_text_edit.anchorClicked.connect(self.handle_links)
        self.log_text_edit.setReadOnly(True)
        log_layout.addWidget(self.log_text_edit)

        settings_layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        projects_layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))
        bridges_tab_layout.addItem(QSpacerItem(20, 20, QSizePolicy.Minimum, QSizePolicy.Expanding))

        self.tab_widget.addTab(settings_tab, "Settings")
        self.tab_widget.addTab(bridges_tab, "Bridges")
        self.tab_widget.addTab(projects_tab, "Projects")
        self.tab_widget.addTab(logs_tab, "Logs")

        central_widget = QWidget()
        central_widget.setLayout(main_layout)
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
        self.tab_widget.setTabText(0, self.tr(self.messages[self.language].get('settings_tab')))
        self.tab_widget.setTabText(1, self.tr(self.messages[self.language].get('bridges_tab')))
        self.tab_widget.setTabText(2, self.tr(self.messages[self.language].get('projects_tab')))
        self.tab_widget.setTabText(3, self.tr(self.messages[self.language].get('logs_tab')))
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

    @property
    def is_dollars_price(self) -> bool:
        return self.widgets_config['amount_dollars'].isChecked()

    def change_price_type(self, is_dollars):
        for lang in self.messages.keys():
            self.messages[lang]['min_price_label'] = self.messages[lang]['min_price_label'].replace(
                '%' if is_dollars else '$', '$' if is_dollars else '%')
            self.messages[lang]['max_price_label'] = self.messages[lang]['max_price_label'].replace(
                '%' if is_dollars else '$', '$' if is_dollars else '%')
        self.widgets_tr['min_price_label'].setText(self.messages[self.language]['min_price_label'])
        self.widgets_tr['max_price_label'].setText(self.messages[self.language]['max_price_label'])
        self.widgets_config['min_price_selector'].setRange(0, 10000 if is_dollars else 100)
        self.widgets_config['max_price_selector'].setRange(0, 10000 if is_dollars else 100)

    def process_start(self, conf):
        self.logger.info('START button clicked')
        # pprint.pp(conf)
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
        if conf['use_configs_checkbox'] and not conf['selected_configs_entry']:
            self.show_error_message(self.messages[self.language]['configs_error'])
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
        if not (0 < conf[f'min_price_selector'] <= conf[f'max_price_selector']):
            self.show_error_message(self.messages[self.language]['minmax_usd_error'])
            return
        for key in ('wallet_delay', 'project_delay'):
            if conf[f'{key}_min_sec'] != 0 and conf[f'{key}_min_sec'] > conf[f'{key}_max_sec']:
                self.show_error_message(self.messages[self.language]['minmax_delay_error'])
                return
        if self.worker_thread is not None and self.worker_thread.isRunning():
            self.logger.error('Worker is already running.. please wait')
            return
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

    def on_use_configs_changed(self):
        # self.hide_widget.setHidden(self.widgets_config['use_configs_checkbox'].isChecked())
        self.bridges_tab.setDisabled(self.widgets_config['use_configs_checkbox'].isChecked())
        self.projects_tab.setDisabled(self.widgets_config['use_configs_checkbox'].isChecked())

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
            for key in ('api_key', 'decrypt_wallets_label', 'file_name', 'selected_configs_entry',
                        'gas_limit_spinner', 'gas_limit_checkbox', 'shuffle_checkbox',
                        'wallet_delay_min_sec', 'wallet_delay_max_sec',
                        'project_delay_min_sec', 'project_delay_max_sec'):
                cfg.pop(key)
            to_save = {'gui_config': cfg, 'config_type': 'additional'}
            json.dump(to_save, open(fileName, 'w', encoding='utf-8'), ensure_ascii=False)
            self.logger.info('Config has been successfully saved')

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
    main_window.setMinimumSize(650, 600)
    frame_geometry = main_window.frameGeometry()
    center_point = QDesktopWidget().availableGeometry().center()
    frame_geometry.moveCenter(center_point)
    main_window.move(frame_geometry.topLeft())
    main_window.show()
    sys.exit(app.exec_())
