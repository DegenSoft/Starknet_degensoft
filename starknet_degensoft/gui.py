import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QHBoxLayout, QCheckBox, QComboBox, QPushButton, \
    QTextEdit, QStyleFactory, QLabel, QLineEdit, QMenuBar, QMenu, QAction, QWidget, QDesktopWidget, QFileDialog, \
    QSplitter, QDoubleSpinBox, QSpinBox
from PyQt5.QtCore import QTranslator, QLocale, Qt


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        language_layout = QHBoxLayout()
        self.language_label = QLabel("Language")
        language_layout.addWidget(self.language_label)
        self.language_selector = QComboBox()
        self.language_selector.addItem("English")
        self.language_selector.addItem("Russian")
        self.language_selector.currentIndexChanged.connect(self.change_language)
        language_layout.addWidget(self.language_selector)
        layout.addLayout(language_layout)

        api_key_layout = QHBoxLayout()
        self.api_key_label = QLabel("API Key")
        api_key_layout.addWidget(self.api_key_label)
        self.password_field = QLineEdit()
        self.password_field.setEchoMode(QLineEdit.Password)
        api_key_layout.addWidget(self.password_field)
        layout.addLayout(api_key_layout)

        private_keys_layout = QHBoxLayout()
        self.private_keys_label = QLabel("Private keys file")
        private_keys_layout.addWidget(self.private_keys_label)
        self.select_file_button = QPushButton("Select File")
        self.select_file_button.clicked.connect(self.on_open_file_clicked)
        private_keys_layout.addWidget(self.select_file_button)
        layout.addLayout(private_keys_layout)

        layout.addWidget(QSplitter())

        self.bridges_label = QLabel("Select bridge")
        # Add 2 dropdowns

        for i in range(1, 3):
            bridge_layout = QHBoxLayout()
            bridge_checkbox = QCheckBox(f'Bridge {i}')
            bridge_checkbox.setChecked(True)
            bridge_layout.addWidget(bridge_checkbox)
            dropdown = QComboBox()
            dropdown.addItem('Network 1')
            dropdown.addItem('Network 2')
            dropdown.addItem('Network 3')
            # dropdown.setCurrentIndex(1)
            bridge_layout.addWidget(dropdown)
            layout.addLayout(bridge_layout)

        layout.addWidget(QSplitter())

        self.quests_label = QLabel("Select quests")
        layout.addWidget(self.quests_label)

        for i in range(1, 4):
            quest_layout = QHBoxLayout()
            self.checkbox = QCheckBox(f'Quest name {i}')
            self.checkbox.setChecked(True)
            quest_layout.addWidget(self.checkbox)
            self.min_price_label = QLabel('min:')
            quest_layout.addWidget(self.min_price_label)
            self.min_price_selector = QDoubleSpinBox()
            self.min_price_selector.setRange(0, 10000)
            quest_layout.addWidget(self.min_price_selector)
            self.max_price_label = QLabel('max:')
            quest_layout.addWidget(self.max_price_label)
            self.max_price_selector = QDoubleSpinBox()
            self.max_price_selector.setRange(0, 10000)
            quest_layout.addWidget(self.max_price_selector)

            quest_layout.setStretch(0, 1)
            quest_layout.setStretch(2, 1)
            quest_layout.setStretch(4, 1)

            layout.addLayout(quest_layout)

        self.options_label = QLabel("Set options")
        layout.addWidget(self.options_label)

        options_layout = QHBoxLayout()
        options_1_label = QLabel("Delay")
        min_option_1_label = QLabel('min:')
        min_option_1_selector = QSpinBox()
        min_option_1_selector.setRange(0, 10000)
        max_option_1_label = QLabel('max:')
        max_option_1_selector = QSpinBox()
        max_option_1_selector.setRange(0, 10000)

        options_layout.addWidget(options_1_label)
        options_layout.addWidget(min_option_1_label)
        options_layout.addWidget(min_option_1_selector)
        options_layout.addWidget(max_option_1_label)
        options_layout.addWidget(max_option_1_selector)
        options_layout.setStretch(0, 1)
        options_layout.setStretch(2, 1)
        options_layout.setStretch(4, 1)
        layout.addLayout(options_layout)

        # Create a horizontal layout for the buttons
        button_layout = QHBoxLayout()

        # Add 'start' and 'stop' buttons
        start_button = QPushButton('Start')
        start_button.clicked.connect(self.on_start_clicked)
        button_layout.addWidget(start_button)

        stop_button = QPushButton('Stop')
        stop_button.clicked.connect(self.on_stop_clicked)
        button_layout.addWidget(stop_button)

        # Add the button_layout to the main layout
        layout.addLayout(button_layout)

        # Add a big text field for logs
        self.log_text_edit = QTextEdit()
        self.log_text_edit.setReadOnly(True)
        layout.addWidget(self.log_text_edit)

        central_widget = QWidget()
        central_widget.setLayout(layout)

        self.setCentralWidget(central_widget)

        exit_action = QAction('Exit', self)
        exit_action.setShortcut('Ctrl+Q')
        exit_action.triggered.connect(self.close)
        self.addAction(exit_action)

        open_file_action = QAction('Open File', self)
        open_file_action.setShortcut('Ctrl+O')
        open_file_action.triggered.connect(self.on_open_file_clicked)
        self.addAction(open_file_action)


        self.setWindowTitle('StarkNet')
        # self.setMinimumSize(640, 480)
        # self.setP

    def change_language(self, index):
        languages = ["en", "ru"]
        language = languages[index]

        translator = QTranslator()
        translator.load(f"{language}.qm")
        QApplication.instance().installTranslator(translator)

        self.retranslate_ui()

    def retranslate_ui(self):
        self.setWindowTitle(self.tr("Your application name"))
        # self.language_selector.setItemText(0, self.tr("English"))
        # self.language_selector.setItemText(1, self.tr("Russian"))

    def on_start_clicked(self):
        self.log_text_edit.append('Start button clicked')
        self.log_text_edit.verticalScrollBar().setValue(self.log_text_edit.verticalScrollBar().maximum())

    def on_stop_clicked(self):
        self.log_text_edit.append('Stop button clicked')
        self.log_text_edit.verticalScrollBar().setValue(self.log_text_edit.verticalScrollBar().maximum())

    def on_open_file_clicked(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_name, _ = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*);;Text Files (*.txt)", options=options)
        if file_name:
            self.log_text_edit.append(f'File selected: {file_name}')


def main():
    app = QApplication(sys.argv)
    # app.setStyle(QStyleFactory.create('Windows'))
    main_window = MainWindow()
    main_window.setMinimumSize(480, 320)
    frame_geometry = main_window.frameGeometry()
    center_point = QDesktopWidget().availableGeometry().center()
    frame_geometry.moveCenter(center_point)
    main_window.move(frame_geometry.topLeft())
    main_window.show()

    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
