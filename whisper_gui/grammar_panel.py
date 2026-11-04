from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QTextBrowser, QVBoxLayout, QWidget


class GrammarPanel(QWidget):
    analyze_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.clicked.connect(self.analyze_requested)

        self.status_label = QLabel("")

        self.result_view = QTextBrowser()
        self.result_view.setReadOnly(True)

        layout = QVBoxLayout(self)
        layout.addWidget(self.analyze_button)
        layout.addWidget(self.status_label)
        layout.addWidget(self.result_view)

    def set_analyze_enabled(self, enabled: bool) -> None:
        self.analyze_button.setEnabled(enabled)

    def set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def set_result(self, markdown_text: str) -> None:
        self.result_view.setMarkdown(markdown_text)
        self.status_label.setText("")

    def clear(self) -> None:
        self.result_view.clear()
        self.status_label.setText("")
