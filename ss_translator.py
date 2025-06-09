import sys
import threading
import deepl
import os
import ctypes
import json
import re # Metin işleme için Regular Expressions modülü
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QScrollArea, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QComboBox, QMessageBox,
                             QTabWidget, QListWidget, QListWidgetItem)
from PyQt6.QtCore import Qt, QRect, QPoint, QObject, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import (QPainter, QColor, QPen, QGuiApplication, QFont, 
                         QIcon, QAction, QIntValidator, QPixmap)
from pynput import keyboard
from PIL import Image
import pytesseract

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.realpath(__file__))
    return os.path.join(base_path, relative_path)

tesseract_path = resource_path(os.path.join("Tesseract-OCR", "tesseract.exe"))
if os.path.exists(tesseract_path):
    pytesseract.pytesseract.tesseract_cmd = tesseract_path
else:
    print(f"ERROR: Tesseract.exe not found at expected path: {tesseract_path}")

CONFIG_FILE = 'config.json'
HISTORY_FILE = 'history.json'
MAX_HISTORY_ENTRIES = 50
DEFAULT_CONFIG = {
    'api_key': '', 'source_lang': 'Auto', 'target_lang': 'TR',
    'width': 800, 'height': 500
}
SUPPORTED_LANGUAGES = {
    "Auto-Detect": {"deepl": "Auto", "tess": "eng"},
    "English":     {"deepl": "EN", "tess": "eng"},
    "Turkish":     {"deepl": "TR", "tess": "tur"},
    "German":      {"deepl": "DE", "tess": "deu"},
    "French":      {"deepl": "FR", "tess": "fra"},
    "Spanish":     {"deepl": "ES", "tess": "spa"},
    "Italian":     {"deepl": "IT", "tess": "ita"},
    "Japanese":    {"deepl": "JA", "tess": "jpn"},
    "Russian":     {"deepl": "RU", "tess": "rus"}
}

def load_json(file_path, default_data):
    if not os.path.exists(file_path): return default_data
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = default_data.copy(); data.update(json.load(f)); return data
    except Exception: return default_data

def save_json(file_path, data):
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

app_config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
translation_history = load_json(HISTORY_FILE, [])

def add_to_history(source_text, translated_text):
    global translation_history;
    new_entry = {'source': source_text, 'target': translated_text}
    if translation_history and translation_history[0] == new_entry: return
    translation_history.insert(0, new_entry); translation_history = translation_history[:MAX_HISTORY_ENTRIES]
    save_json(HISTORY_FILE, translation_history)
    if communicator: communicator.history_updated.emit()

class HistoryItemWidget(QWidget):
    def __init__(self, source_text, target_text):
        super().__init__(); self.source = source_text; self.target = target_text
        layout = QVBoxLayout(self); layout.setContentsMargins(5, 5, 5, 5); layout.setSpacing(2)
        display_target = self.target.replace('\n', ' ').strip()
        source_preview = (self.source.replace('\n', ' ').strip()[:70] + '...') if len(self.source) > 70 else self.source.replace('\n', ' ').strip()
        self.target_label = QLabel(display_target); self.target_label.setFont(QFont("Arial", 11)); self.target_label.setStyleSheet("color: white;"); self.target_label.setWordWrap(True)
        self.source_label = QLabel(source_preview); self.source_label.setFont(QFont("Arial", 9)); self.source_label.setStyleSheet("color: #aaa;"); self.source_label.setWordWrap(True)
        layout.addWidget(self.target_label); layout.addWidget(self.source_label)

class SettingsWindow(QWidget):
    def __init__(self, icon_path):
        super().__init__(); self.setWindowTitle("API Key Settings"); self.setWindowIcon(QIcon(icon_path)); self.setFixedSize(400, 150)
        layout = QVBoxLayout(self); info_label = QLabel("Please enter your DeepL API Key:"); layout.addWidget(info_label)
        self.api_key_input = QLineEdit(); self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password); self.api_key_input.setText(app_config.get('api_key', '')); layout.addWidget(self.api_key_input)
        self.save_button = QPushButton("Save and Apply Key"); self.save_button.clicked.connect(self.save_api_key); layout.addWidget(self.save_button)
        self.status_label = QLabel(""); layout.addWidget(self.status_label)
    def save_api_key(self):
        global app_config; api_key = self.api_key_input.text().strip()
        if not api_key: self.status_label.setText("API Key cannot be empty."); return
        app_config['api_key'] = api_key; save_json(CONFIG_FILE, app_config); self.status_label.setText("API Key saved successfully!"); print("API Key has been updated and saved."); QTimer.singleShot(1500, self.close)

class MainWindow(QWidget):
    def __init__(self, icon_path):
        super().__init__(); self.icon_path = icon_path; self.settings_window = None
        self.setWindowTitle("SSTranslate Control Panel"); self.setWindowIcon(QIcon(icon_path)); self.setMinimumSize(420, 300)
        main_layout = QVBoxLayout(self); tabs = QTabWidget(); main_layout.addWidget(tabs)
        settings_tab = QWidget(); tabs.addTab(settings_tab, "Settings"); self.setup_settings_tab(settings_tab)
        history_tab = QWidget(); tabs.addTab(history_tab, "History"); self.setup_history_tab(history_tab)
        if communicator: communicator.history_updated.connect(self.populate_history_list)
    def setup_settings_tab(self, tab):
        settings_layout = QVBoxLayout(tab)
        lang_group_label = QLabel("Language Settings"); lang_group_label.setFont(QFont("Arial", 10, QFont.Weight.Bold)); settings_layout.addWidget(lang_group_label)
        source_lang_layout = QHBoxLayout(); source_lang_label = QLabel("Source Language:"); self.source_lang_combo = QComboBox(); self.source_lang_combo.addItems(SUPPORTED_LANGUAGES.keys())
        current_source_lang_code = app_config.get('source_lang', DEFAULT_CONFIG['source_lang']); current_source_lang_name = next((name for name, val in SUPPORTED_LANGUAGES.items() if val['deepl'] == current_source_lang_code), "Auto-Detect"); self.source_lang_combo.setCurrentText(current_source_lang_name)
        source_lang_layout.addWidget(source_lang_label); source_lang_layout.addWidget(self.source_lang_combo); settings_layout.addLayout(source_lang_layout)
        target_lang_layout = QHBoxLayout(); target_lang_label = QLabel("Target Language:"); self.target_lang_combo = QComboBox()
        target_langs = {k: v for k, v in SUPPORTED_LANGUAGES.items() if k != "Auto-Detect"}; self.target_lang_combo.addItems(target_langs.keys())
        current_target_lang_code = app_config.get('target_lang', DEFAULT_CONFIG['target_lang']); current_target_lang_name = next((name for name, val in SUPPORTED_LANGUAGES.items() if val['deepl'] == current_target_lang_code), "Turkish"); self.target_lang_combo.setCurrentText(current_target_lang_name)
        target_lang_layout.addWidget(target_lang_label); target_lang_layout.addWidget(self.target_lang_combo); settings_layout.addLayout(target_lang_layout)
        settings_layout.addStretch()
        button_layout = QHBoxLayout(); self.api_settings_button = QPushButton("API Key Settings"); self.api_settings_button.clicked.connect(self.open_settings_window); self.save_button = QPushButton("Save Language"); self.save_button.clicked.connect(self.save_settings_handler)
        button_layout.addWidget(self.api_settings_button); button_layout.addWidget(self.save_button); settings_layout.addLayout(button_layout)
        self.status_label = QLabel("Press F8 to translate."); self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter); settings_layout.addWidget(self.status_label)
    def setup_history_tab(self, tab):
        history_layout = QVBoxLayout(tab); self.history_list_widget = QListWidget(); self.history_list_widget.itemDoubleClicked.connect(self.history_item_clicked)
        self.history_list_widget.setStyleSheet("QListWidget {border: 1px solid #555;} QListWidget::item {padding: 8px; border-bottom: 1px solid #444;} QListWidget::item:hover {background-color: #2a2a2a;}")
        self.history_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); history_layout.addWidget(self.history_list_widget)
        clear_button = QPushButton("Clear History"); clear_button.clicked.connect(self.clear_history); history_layout.addWidget(clear_button)
        self.populate_history_list()
    def populate_history_list(self):
        self.history_list_widget.clear()
        for entry in translation_history:
            item_widget = HistoryItemWidget(entry['source'], entry['target']); list_item = QListWidgetItem(self.history_list_widget)
            list_item.setSizeHint(item_widget.sizeHint()); self.history_list_widget.addItem(list_item); self.history_list_widget.setItemWidget(list_item, item_widget)
    def history_item_clicked(self, item):
        widget = self.history_list_widget.itemWidget(item)
        if widget: clipboard = QApplication.clipboard(); clipboard.setText(widget.target); self.status_label.setText(f"Copied to clipboard!"); print(f"Copied from history: {widget.target}")
    def clear_history(self):
        global translation_history
        reply = QMessageBox.question(self, "Clear History", "Are you sure you want to delete all translation history?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes: translation_history = []; save_json(HISTORY_FILE, []); self.populate_history_list(); print("History cleared.")
    def open_settings_window(self):
        if self.settings_window is None or not self.settings_window.isVisible(): self.settings_window = SettingsWindow(self.icon_path); self.settings_window.show()
    def save_settings_handler(self):
        global app_config;
        try:
            selected_source_lang = self.source_lang_combo.currentText(); app_config['source_lang'] = SUPPORTED_LANGUAGES[selected_source_lang]['deepl']
            selected_target_lang = self.target_lang_combo.currentText(); app_config['target_lang'] = {k: v for k, v in SUPPORTED_LANGUAGES.items() if k != "Auto-Detect"}[selected_target_lang]['deepl']
            save_json(CONFIG_FILE, app_config); self.status_label.setText("Language settings saved!"); print("Settings saved:", app_config)
        except Exception as e: self.status_label.setText("Error: Could not save settings."); print(f"Error saving settings: {e}")

class Communicator(QObject): f8_pressed = pyqtSignal(); esc_pressed = pyqtSignal(); history_updated = pyqtSignal()
class TranslationOverlay(QWidget):
    def __init__(self, text, width, height):
        super().__init__(); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating); self.setFixedSize(width, height)
        container_layout = QVBoxLayout(self); container_layout.setContentsMargins(15, 15, 15, 15); self.scroll_area = QScrollArea(self); self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar:vertical { border: none; background: #3c3c3c; width: 10px; margin: 0px; } QScrollBar::handle:vertical { background: #808080; min-height: 20px; border-radius: 5px; }")
        self.text_label = QLabel(text, self); self.text_label.setFont(QFont("Arial", 14)); self.text_label.setStyleSheet("background: transparent; color: white;"); self.text_label.setWordWrap(True); self.text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.text_label); container_layout.addWidget(self.scroll_area)
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing); bg_rect = self.rect(); painter.setBrush(QColor(0, 0, 0, 200)); painter.setPen(Qt.PenStyle.NoPen); painter.drawRoundedRect(bg_rect, 15, 15)
class SnippingWidget(QWidget):
    def __init__(self):
        super().__init__(); self.begin = QPoint(); self.end = QPoint(); self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint); self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground); self.setGeometry(QGuiApplication.primaryScreen().geometry()); self.setCursor(Qt.CursorShape.CrossCursor); self.show()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: print("Selection canceled."); self.close()
    def paintEvent(self, event):
        painter = QPainter(self); painter.fillRect(self.rect(), QColor(0, 0, 0, 70)); rect = QRect(self.begin, self.end); pen = QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.SolidLine); painter.setPen(pen); painter.drawRect(rect.normalized())
    def mousePressEvent(self, event): self.begin = event.pos(); self.end = event.pos(); self.update()
    def mouseMoveEvent(self, event): self.end = event.pos(); self.update()
    def mouseReleaseEvent(self, event): self.close(); capture_and_translate(QRect(self.begin, self.end).normalized())
snipping_widget = None; translation_overlay = None; main_window = None; communicator = None

def capture_and_translate(rect):
    global translation_overlay; api_key = app_config.get('api_key')
    if not api_key: QMessageBox.warning(main_window, "API Key Missing", "DeepL API Key is not set. Please enter your key in the settings panel."); return
    try:
        screenshot = QGuiApplication.primaryScreen().grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
        buffer = screenshot.toImage(); image_bits = buffer.bits(); image_bits.setsize(buffer.sizeInBytes()); image_bytes = image_bits.asstring()
        image = Image.frombytes("RGBA", (buffer.width(), buffer.height()), image_bytes, "raw", "BGRA").convert("L")
        
        source_lang_deepl_code = app_config.get('source_lang', 'Auto')
        ocr_lang_code = 'eng'
        for lang_name, codes in SUPPORTED_LANGUAGES.items():
            if codes['deepl'] == source_lang_deepl_code:
                ocr_lang_code = codes['tess']; break
        
        raw_extracted_text = pytesseract.image_to_string(image, lang=ocr_lang_code).strip()
        
        # === YENİ VE GELİŞMİŞ METİN İŞLEME MANTIĞI ===
        text_no_hyphens = re.sub(r'-\s*\n\s*', '', raw_extracted_text)
        text_with_preserved_breaks = text_no_hyphens.replace('\n\n', '[P_BREAK]')
        text_single_line = text_with_preserved_breaks.replace('\n', ' ')
        text_normalized_spaces = re.sub(' +', ' ', text_single_line)
        processed_text = text_normalized_spaces.replace('[P_BREAK]', '\n\n')
        
        if not processed_text: return
        
        translator = deepl.Translator(api_key)
        target_lang = app_config.get('target_lang')
        translate_kwargs = {'target_lang': target_lang}; 
        if source_lang_deepl_code and source_lang_deepl_code != 'Auto': translate_kwargs['source_lang'] = source_lang_deepl_code
        result = translator.translate_text(processed_text, **translate_kwargs); translated_text = result.text
        add_to_history(processed_text, translated_text)
        print(f"Translation ({source_lang_deepl_code} -> {target_lang}): '{translated_text}'")
        if translation_overlay and translation_overlay.isVisible(): translation_overlay.close()
        box_width = app_config.get('width', DEFAULT_CONFIG['width']); box_height = app_config.get('height', DEFAULT_CONFIG['height'])
        translation_overlay = TranslationOverlay(translated_text, box_width, box_height)
        screen_geometry = QGuiApplication.primaryScreen().geometry()
        x_pos = (screen_geometry.width() - box_width) / 2; y_pos = (screen_geometry.height() - box_height) / 2
        translation_overlay.move(int(x_pos), int(y_pos)); translation_overlay.show()
    except deepl.AuthorizationException: QMessageBox.warning(main_window, "Invalid API Key", "The DeepL API Key is invalid or has expired. Please check your key in the API Key Settings.")
    except Exception as e: QMessageBox.critical(main_window, "Unexpected Error", f"An unexpected error occurred: {e}")

def start_snipping(): global snipping_widget; snipping_widget = SnippingWidget()
def close_overlays():
    global translation_overlay, snipping_widget
    if translation_overlay and translation_overlay.isVisible(): print("Translation overlay closed."); translation_overlay.close()
    if snipping_widget and snipping_widget.isVisible(): print("Selection screen closed."); snipping_widget.close()
class HotkeyListener(threading.Thread):
    def __init__(self, comm): super().__init__(); self.communicator = comm; self.daemon = True
    def run(self):
        def on_press(key):
            if key == keyboard.Key.f8: self.communicator.f8_pressed.emit()
            elif key == keyboard.Key.esc: self.communicator.esc_pressed.emit()
        with keyboard.Listener(on_press=on_press) as listener: listener.join()
def main():
    global main_window, communicator
    myappid = 'mycompany.screentranslator.1.0'; ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    app = QApplication(sys.argv)
    script_dir = os.path.dirname(os.path.realpath(__file__)); icon_path = resource_path("icon.ico")
    communicator = Communicator();
    main_window = MainWindow(icon_path); main_window.show()
    communicator.f8_pressed.connect(start_snipping); communicator.esc_pressed.connect(close_overlays)
    hotkey_thread = HotkeyListener(communicator); hotkey_thread.start()
    print("Control Panel opened. Program is running."); sys.exit(app.exec())
if __name__ == '__main__': main()