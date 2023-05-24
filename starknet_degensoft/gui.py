import sys
import logging
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox, QPushButton, \
    QTextEdit, QStyleFactory, QLabel, QLineEdit, QMenuBar, QMenu, QAction, QWidget, QDesktopWidget, QFileDialog, \
    QSplitter, QDoubleSpinBox, QSpinBox, QAbstractSpinBox
from PyQt5.QtCore import QTranslator, QLocale


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.logger = logging.getLogger('starknet')
        self.logger.setLevel(level=logging.DEBUG)
        self.bridges = {
            'starkgate': {
                'name': 'Starkgate',
                'networks': ['Ethereum']
            },
            'layerswap': {
                'name': 'Layerswap.io',
                'networks': ['Arbitrum One', 'Arbitrum Nova']
            }
        }
        self.swaps = {
            'myswap': {'name': 'myswap.xyz'},
            '10kswap': {'name': '10kswap'},
            'jediswap': {'name': 'jediswap'},
        }
        self.messages = {
            'window_title': "StarkNet DegenSoft",
            'language_label': "Language",
            'api_key_label': "API Key (you can get it via <a href='http://t.me/degensoftbot'>@DegenSoftBot</a>)",
            'api_key_checkbox': "hide",
            'private_keys_label': "Ethereum private keys file:",
            'bridges_label': "Select bridge",
            'quests_label': "Select quests",
            'options_label': "Options",
            'wallet_delay_label': "Wallet delay",
            'swap_delay_label': "Swap delay",
            'min_sec': "min $:",
            'max_sec': "max $:",
            'min_doll': "min $:",
            "max_doll": "max $:",
            'select_file_button': "Select File",
            'start_button': "Start",
            'stop_button': "Stop",
            'pause_button': "Pause/Continue"
        }
        self.widgets = {}
        self.widgets_config = {}
        self.translator = QTranslator()
        self.init_ui()
        self.retranslate_ui()

    def load_config(self):
        pass

    def save_config(self):
        pass

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
        self.widgets['language_label'] = language_label
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
        self.widgets['api_key_label'] = api_key_label
        self.widgets_config['api_key'] = api_key_field
        self.widgets['api_key_checkbox'] = api_key_checkbox
        api_key_checkbox.stateChanged.connect(self.on_hide_checkbox_changed)
        self.widgets_config['api_key_checkbox'] = api_key_checkbox

        private_keys_layout = QHBoxLayout()
        private_keys_label = QLabel(self.tr("Ethereum private keys file:"))
        private_keys_layout.addWidget(private_keys_label)
        select_file_button = QPushButton(self.tr("Select File"))
        select_file_button.clicked.connect(self.on_open_file_clicked)
        private_keys_layout.addWidget(select_file_button)
        layout.addLayout(private_keys_layout)
        self.widgets['private_keys_label'] = private_keys_label
        self.widgets['select_file_button'] = select_file_button
        self.widgets_config['select_file_button'] = select_file_button

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
        self.widgets['bridges_label'] = bridges_label

        # for bridge in self.bridges:
        #     bridge_layout = QHBoxLayout()
            # bridge['checkbox'] = QCheckBox(bridge['name'])
            # bridge['checkbox'].setChecked(False)
            # bridge_layout.addWidget(bridge['checkbox'])
            # bridge['dropdown'] = QComboBox()
            # for network in bridge['networks']:
            #     bridge['dropdown'].addItem(network)
            # bridge_layout.addWidget(bridge['dropdown'])
            # min_label = QLabel('min ETH:')
            # max_label = QLabel('max ETH:')
            # min_price_selector = QDoubleSpinBox(decimals=4, stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            # max_price_selector = QDoubleSpinBox(decimals=4, stepType=QAbstractSpinBox.StepType.AdaptiveDecimalStepType)
            # bridge_layout.addWidget(min_label)
            # bridge_layout.addWidget(min_price_selector)
            # bridge_layout.addWidget(max_label)
            # bridge_layout.addWidget(max_price_selector)
            # bridge_layout.setStretch(0, 1)
            # bridge_layout.setStretch(1, 1)
            # layout.addLayout(bridge_layout)

        layout.addWidget(QSplitter())

        self.widgets['quests_label'] = QLabel()
        layout.addWidget(self.widgets['quests_label'])

        # for swap in self.swaps:
        #     quest_layout = QHBoxLayout()
        #     self.checkbox = QCheckBox(swap['name'])
        #     self.checkbox.setChecked(True)
        #     quest_layout.addWidget(self.checkbox)
        #     self.min_price_label = QLabel(self.tr('min $:'))
        #     quest_layout.addWidget(self.min_price_label)
        #     self.min_price_selector = QDoubleSpinBox()
        #     self.min_price_selector.setRange(0, 10000)
        #     quest_layout.addWidget(self.min_price_selector)
        #     self.max_price_label = QLabel(self.tr('max $:'))
        #     quest_layout.addWidget(self.max_price_label)
        #     self.max_price_selector = QDoubleSpinBox()
        #     self.max_price_selector.setRange(0, 10000)
        #     quest_layout.addWidget(self.max_price_selector)
        #     quest_layout.setStretch(0, 1)
        #     quest_layout.setStretch(2, 1)
        #     quest_layout.setStretch(4, 1)
        #     layout.addLayout(quest_layout)

        layout.addWidget(QSplitter())

        self.widgets['options_label'] = QLabel()
        layout.addWidget(self.widgets['options_label'])

        # for label_name in ('wallet_delay_label', 'swap_delay_label'):
        #     options_layout = QHBoxLayout()
        #     options_1_label = QLabel()
        #     min_option_1_label = QLabel(self.tr('min sec:'))
        #     min_option_1_selector = QSpinBox()
        #     min_option_1_selector.setRange(0, 10000)
        #     min_option_1_selector.setValue(60)
        #     max_option_1_label = QLabel(self.tr('max sec:'))
        #     max_option_1_selector = QSpinBox()
        #     max_option_1_selector.setRange(0, 10000)
        #     max_option_1_selector.setValue(120)
        #     options_layout.addWidget(options_1_label)
        #     options_layout.addWidget(min_option_1_label)
        #     options_layout.addWidget(min_option_1_selector)
        #     options_layout.addWidget(max_option_1_label)
        #     options_layout.addWidget(max_option_1_selector)
        #     options_layout.setStretch(0, 1)
        #     options_layout.setStretch(2, 1)
        #     options_layout.setStretch(4, 1)
        #     layout.addLayout(options_layout)

        layout.addWidget(QSplitter())

        button_layout = QHBoxLayout()
        self.widgets['start_button'] = QPushButton()
        self.widgets['start_button'].clicked.connect(self.on_start_clicked)
        self.widgets['stop_button'] = QPushButton()
        self.widgets['stop_button'].clicked.connect(self.on_stop_clicked)
        self.widgets['pause_button'] = QPushButton()
        self.widgets['pause_button'].setDisabled(True)
        self.widgets['pause_button'].clicked.connect(self.on_pause_clicked)
        button_layout.addWidget(self.widgets['start_button'])
        button_layout.addWidget(self.widgets['pause_button'])
        button_layout.addWidget(self.widgets['stop_button'])
        layout.addLayout(button_layout)

        # Add a big text field for logs
        self.log_text_edit = QTextEdit()
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
        self.translator.load(f'locale/{languages[index]}.qm')
        QApplication.instance().installTranslator(self.translator)
        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.tr(self.messages.get('window_title')))
        for widget_name in self.widgets:
            if widget_name not in self.messages:
                continue
            # if widget_name.endswith('_label') or widget_name.endswith('_button'):
            self.widgets[widget_name].setText(self.tr(self.messages[widget_name]))

    def log(self, message):
        self.log_text_edit.append(message)
        self.log_text_edit.verticalScrollBar().setValue(self.log_text_edit.verticalScrollBar().maximum())

    def on_start_clicked(self):
        # self.widgets['start_button'].setDisabled(True)
        self.widgets['pause_button'].setDisabled(False)
        # self.widgets['stop_button'].setDisabled(False)
        self.log('Start button clicked')

    def on_pause_clicked(self):
        # self.widgets['start_button'].setDisabled(False)
        # self.widgets['pause_button'].setDisabled(True)
        self.log('Pause button clicked')

    def on_stop_clicked(self):
        self.log('Stop button clicked')

    def on_hide_checkbox_changed(self):
        echo_mode = QLineEdit.Password if self.sender().isChecked() else QLineEdit.Normal
        self.widgets_config['api_key'].setEchoMode(echo_mode)

    def on_open_file_clicked(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getOpenFileName(self, self.tr("Open File"), "", "All Files (*);;Text Files (*.txt)",
                                                   options=options)
        if file_name:
            self.log(f'File selected: {file_name}')


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
