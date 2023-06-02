import os
import random
import sys
import time
import logging
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox, QPushButton, \
    QTextEdit, QStyleFactory, QLabel, QLineEdit, QMenuBar, QMenu, QAction, QWidget, QDesktopWidget, QFileDialog, \
    QSplitter, QDoubleSpinBox, QSpinBox, QAbstractSpinBox, QMessageBox, QTextBrowser
from PyQt5.QtCore import QTranslator, QLocale, QThread, pyqtSignal
from PyQt5.Qt import QDesktopServices, QUrl, Qt
from starknet_degensoft.starknet_trader import StarknetTrader
from starknet_degensoft.config import Config
from starknet_degensoft.utils import setup_file_logging, log_formatter, resource_path, convert_urls_to_links
from starknet_degensoft.starknet_swap import MyswapSwap, TenKSwap, JediSwap
from starknet_degensoft.starkgate import StarkgateBridge
from starknet_degensoft.layerswap import LayerswapBridge
from starknet_degensoft.api_client2 import DegenSoftApiClient, DegenSoftApiError


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
    logger_signal = pyqtSignal(str)

    def __init__(self, api, trader, config, swaps, bridges):
        super().__init__()
        self.api = api
        self.trader = trader
        self.config = config
        self.swaps = swaps
        self.bridges = bridges
        self.paused = False
        self.logger = logging.getLogger('starknet')
        self.handler = QtSignalLogHandler(signal=self.logger_signal)
        # self.handler.setLevel(logging.DEBUG)
        self.handler.setFormatter(log_formatter)
        self.logger.addHandler(self.handler)

    def run(self):
        wallet_delay = (self.config['wallet_delay_min_sec'], self.config['wallet_delay_max_sec'])
        swap_delay = (self.config['project_delay_min_sec'], self.config['project_delay_max_sec'])
        projects = []
        # print(self.config)
        for key in self.swaps:
            if self.config[f'swap_{key}_checkbox']:
                projects.append(dict(cls=self.swaps[key]['cls'],
                                     amount_usd=(self.config[f'min_price_{key}_selector'],
                                                 self.config[f'max_price_{key}_selector'])))
        if self.config['random_swap_checkbox']:
            random.shuffle(projects)
            projects = projects[:1]
        for key in self.bridges:
            if self.config[f'bridge_{key}_checkbox']:
                bridge_network_name = self.bridges[key]['networks'][self.config[f'bridge_{key}_network']]
                bridge_amount = (self.config[f'min_eth_{key}_selector'], self.config[f'max_eth_{key}_selector'])
                projects.append(dict(cls=self.bridges[key]['cls'], network=bridge_network_name, amount=bridge_amount))
        self.trader.run(projects=projects, wallet_delay=wallet_delay,
                        project_delay=swap_delay, shuffle=self.config['shuffle_checkbox'],
                        api=self.api)
        self.task_completed.emit()
        self.logger.removeHandler(self.handler)

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


class MainWindow(QMainWindow):
    CONFIG_NAME = 'config.json'
    SLAVIK_API_SECRET = ''

    file_name = None
    log_line = 0
    worker_thread = None

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

    swaps = {
        'myswap': {'name': 'myswap.xyz', 'cls': MyswapSwap},
        '10kswap': {'name': '10kswap', 'cls': TenKSwap},
        'jediswap': {'name': 'jediswap', 'cls': JediSwap},
    }

    messages = {
        'window_title': "StarkNet DegenSoft",
        'language_label': "Language",
        'api_key_label': "API Key (you can get it via <a href='http://t.me/degensoftbot'>@DegenSoftBot</a>)",
        'api_key_checkbox': "hide",
        'private_keys_label': "Private keys file",
        'bridges_label': "Select bridge and source network to transfer ETH to Starknet",
        'quests_label': "Select quests",
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
        'shuffle_checkbox': "Shuffle wallets",
        'select_file_button': "Select File",
        'start_button': "Start",
        'stop_button': "Stop",
        'pause_button': "Pause/Continue"
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
        for logger in (self.logger, startnet_logger):
            setup_file_logging(logger=logger, log_file='default.log')
        for bridge_name in self.bridges:
            self.messages[f'min_eth_{bridge_name}_label'] = self.messages['min_eth_label']
            self.messages[f'max_eth_{bridge_name}_label'] = self.messages['max_eth_label']
        for swap_name in self.swaps:
            self.messages[f'min_price_{swap_name}_label'] = self.messages['min_price_label']
            self.messages[f'max_price_{swap_name}_label'] = self.messages['max_price_label']
        self.widgets_tr = {}
        self.widgets_config = {}
        self.translator = QTranslator()
        self.init_ui()
        self.retranslate_ui()
        self.load_config()
        self.trader = StarknetTrader(config=self.config, testnet=self.config.testnet)

    def load_config(self):
        self.config.load(self.CONFIG_NAME)
        for key in self.config.data['gui_config']:
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
        api_key_layout.addWidget(api_key_label)
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
        private_keys_label = QLabel(self.tr("Ethereum private keys file:"))
        private_keys_layout.addWidget(private_keys_label)
        select_file_button = QPushButton(self.tr("Select File"))
        select_file_button.clicked.connect(self.on_open_file_clicked)
        private_keys_layout.addWidget(select_file_button)
        layout.addLayout(private_keys_layout)
        self.widgets_tr['private_keys_label'] = private_keys_label
        self.widgets_tr['select_file_button'] = select_file_button

        # starknet_seed_layout = QHBoxLayout()
        # self.starknet_seed_label = QLabel("Starknet seed file:")
        # starknet_seed_layout.addWidget(self.starknet_seed_label)
        # self.select_starknet_button = QPushButton("Select File")
        # self.select_starknet_button.clicked.connect(self.on_open_file_clicked)
        # starknet_seed_layout.addWidget(self.select_starknet_button)
        # layout.addLayout(starknet_seed_layout)

        layout.addWidget(QSplitter())

        bridges_label = QLabel()
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
        self.widgets_tr['quests_label'] = QLabel()
        layout.addWidget(self.widgets_tr['quests_label'])

        for key in self.swaps:
            quest_layout = QHBoxLayout()
            swap_checkbox = QCheckBox(self.swaps[key]['name'])
            swap_checkbox.setChecked(True)
            quest_layout.addWidget(swap_checkbox)
            min_price_label = QLabel(self.tr('min $:'))
            quest_layout.addWidget(min_price_label)
            min_eth_selector = QDoubleSpinBox()
            min_eth_selector.setRange(0, 10000)
            quest_layout.addWidget(min_eth_selector)
            max_price_label = QLabel(self.tr('max $:'))
            quest_layout.addWidget(max_price_label)
            max_eth_selector = QDoubleSpinBox()
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
        self.widgets_tr['options_label'] = QLabel()
        layout.addWidget(self.widgets_tr['options_label'])

        for option_name in ('wallet_delay', 'project_delay'):
            options_layout = QHBoxLayout()
            options_1_label = QLabel()
            min_option_1_label = QLabel()
            min_option_1_selector = QSpinBox()
            min_option_1_selector.setRange(0, 10000)
            min_option_1_selector.setValue(60)
            max_option_1_label = QLabel()
            max_option_1_selector = QSpinBox()
            max_option_1_selector.setRange(0, 10000)
            max_option_1_selector.setValue(120)
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
        self.log_text_edit = MyQTextEdit()
        # self.log_text_edit = QTextEdit()
        # self.log_text_edit = QTextBrowser()
        # self.log_text_edit.setOpenLinks(False)
        # self.log_text_edit.anchorClicked.connect(self.handle_links)

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
        lang = languages[index]
        load_status = self.translator.load(resource_path(os.path.join('starknet_degensoft', 'locale', f'{lang}.qm')))
        if load_status:
            QApplication.instance().installTranslator(self.translator)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.tr(self.messages.get('window_title')))
        for widget_name in self.widgets_tr:
            if widget_name not in self.messages:
                continue
            # if widget_name.endswith('_label') or widget_name.endswith('_button'):
            self.widgets_tr[widget_name].setText(self.tr(self.messages[widget_name]))

    def _log(self, message):
        self.log_line += 1
        message = convert_urls_to_links(message)
        self.log_text_edit.append(f'{self.log_line}. {message}')
        self.log_text_edit.verticalScrollBar().setValue(self.log_text_edit.verticalScrollBar().maximum())

    def show_error_message(self, message):
        alert = QMessageBox()
        alert.setIcon(QMessageBox.Warning)
        alert.setWindowTitle(self.tr("Error"))
        alert.setText(message)
        alert.exec_()

    def on_start_clicked(self):
        conf = self.get_config(check_enabled_widget=True)
        self.logger.info('Start button clicked')
        if not conf['api_key']:
            self.show_error_message(self.tr("You must set API key!"))
            return
        try:
            degensoft_api = DegenSoftApiClient(api_key=conf['api_key'])
            user_info = degensoft_api.get_userinfo()
            self.logger.info(f'API Username: {user_info["user"]}, Points: {user_info["points"]}, '
                             f'Premium points: {user_info["prem_points"]}')
        except Exception as ex:
            self.show_error_message(self.tr("Bad API key or API error: ") + str(ex))
            return
        if not conf['file_name']:
            self.show_error_message(self.tr("You must select file with private keys!"))
            return
        try:
            self.trader.load_private_keys_csv(conf['file_name'])
        except Exception as ex:
            self.show_error_message(self.tr("Failed to load private keys CSV file: ") + str(ex))
            return
        for key in self.bridges:
            if conf[f'bridge_{key}_checkbox'] and not (0 < conf[f'min_eth_{key}_selector'] <= conf[f'max_eth_{key}_selector']):
                self.show_error_message(self.tr("Minimum ETH amount must be non-zero and less then Maximum ETH amount"))
                return
        for key in self.swaps:
            if conf[f'swap_{key}_checkbox'] and not (0 < conf[f'min_price_{key}_selector'] <= conf[f'max_price_{key}_selector']):
                self.show_error_message(self.tr("Minimum USD$ amount must be non-zero and less then Maximum USD$ amount"))
                return
        for key in ('wallet_delay', 'project_delay'):
            if conf[f'{key}_min_sec'] != 0 and conf[f'{key}_min_sec'] > conf[f'{key}_max_sec']:
                self.show_error_message(self.tr("Minimum delay must be less or equal maximum delay"))
                return
        # return
        self.widgets_tr['start_button'].setDisabled(True)
        self.widgets_tr['pause_button'].setDisabled(False)
        self.widgets_tr['stop_button'].setDisabled(False)
        self.worker_thread = TraderThread(trader=self.trader, api=degensoft_api, config=conf,
                                          swaps=self.swaps, bridges=self.bridges)
        self.worker_thread.task_completed.connect(self.on_thread_task_completed)
        self.worker_thread.logger_signal.connect(self._log)
        self.worker_thread.start()

    def on_thread_task_completed(self):
        self.widgets_tr['start_button'].setDisabled(False)
        self.widgets_tr['pause_button'].setDisabled(True)
        self.widgets_tr['stop_button'].setDisabled(True)
        self.logger.info('Task completed')

    def on_pause_clicked(self):
        if not self.worker_thread.paused:
            self.logger.info('Pause button clicked')
            self.worker_thread.pause()
        else:
            self.logger.info('Continue button clicked')
            self.worker_thread.resume()

    def on_stop_clicked(self):
        self.widgets_tr['start_button'].setDisabled(False)
        self.widgets_tr['pause_button'].setDisabled(True)
        self.widgets_tr['stop_button'].setDisabled(True)
        self.logger.info('Stop button clicked')
        self.worker_thread.stop()

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

    def on_open_file_clicked(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*);;Text Files (*.txt)",
                                                   options=options)
        if file_name:
            self.file_name = file_name
            self.logger.debug(f'File selected: {file_name}')

    def closeEvent(self, event):
        self.config.gui_config = self.get_config()
        self.config.save(self.CONFIG_NAME)

    def handle_links(self, url):
        QDesktopServices.openUrl(url)


def main():
    app = QApplication(sys.argv)
    app.setStyle(QStyleFactory.create('Windows'))
    main_window = MainWindow()
    main_window.setMinimumSize(480, 320)
    frame_geometry = main_window.frameGeometry()
    center_point = QDesktopWidget().availableGeometry().center()
    frame_geometry.moveCenter(center_point)
    main_window.move(frame_geometry.topLeft())
    main_window.show()
    sys.exit(app.exec_())
