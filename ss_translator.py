import sys
import threading
import deepl
import os
import ctypes
import json
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
    print(f"HATA: Tesseract.exe beklenen yolda bulunamadı: {tesseract_path}")
CONFIG_FILE = 'config.json'
HISTORY_FILE = 'history.json'
MAX_HISTORY_ENTRIES = 50
DEFAULT_CONFIG = {
    'api_key': '', 'source_lang': 'Auto', 'target_lang': 'TR',
    'width': 800, 'height': 500
}
SUPPORTED_LANGUAGES = {
    "Auto-Detect": "Auto", "English": "EN", "Turkish": "TR", "German": "DE", 
    "French": "FR", "Spanish": "ES", "Italian": "IT", "Japanese": "JA", "Russian": "RU"
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
    global translation_history
    new_entry = {'source': source_text, 'target': translated_text}
    if translation_history and translation_history[0] == new_entry: return
    translation_history.insert(0, new_entry)
    translation_history = translation_history[:MAX_HISTORY_ENTRIES]
    save_json(HISTORY_FILE, translation_history)
    if communicator: communicator.history_updated.emit()

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
        current_source_lang_code = app_config.get('source_lang', DEFAULT_CONFIG['source_lang']); current_source_lang_name = next((name for name, code in SUPPORTED_LANGUAGES.items() if code == current_source_lang_code), "Auto-Detect"); self.source_lang_combo.setCurrentText(current_source_lang_name)
        source_lang_layout.addWidget(source_lang_label); source_lang_layout.addWidget(self.source_lang_combo); settings_layout.addLayout(source_lang_layout)
        target_lang_layout = QHBoxLayout(); target_lang_label = QLabel("Target Language:"); self.target_lang_combo = QComboBox()
        target_langs = {k: v for k, v in SUPPORTED_LANGUAGES.items() if k != "Auto-Detect"}; self.target_lang_combo.addItems(target_langs.keys())
        current_target_lang_code = app_config.get('target_lang', DEFAULT_CONFIG['target_lang']); current_target_lang_name = next((name for name, code in SUPPORTED_LANGUAGES.items() if code == current_target_lang_code), "Turkish"); self.target_lang_combo.setCurrentText(current_target_lang_name)
        target_lang_layout.addWidget(target_lang_label); target_lang_layout.addWidget(self.target_lang_combo); settings_layout.addLayout(target_lang_layout)
        settings_layout.addStretch()
        button_layout = QHBoxLayout(); self.api_settings_button = QPushButton("API Key Settings"); self.api_settings_button.clicked.connect(self.open_settings_window); self.save_button = QPushButton("Save Language"); self.save_button.clicked.connect(self.save_settings_handler)
        button_layout.addWidget(self.api_settings_button); button_layout.addWidget(self.save_button); settings_layout.addLayout(button_layout)
        self.status_label = QLabel("Press F8 to translate."); self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter); settings_layout.addWidget(self.status_label)

    def setup_history_tab(self, tab):
        history_layout = QVBoxLayout(tab)
        self.history_list_widget = QListWidget()
        self.history_list_widget.itemDoubleClicked.connect(self.history_item_clicked)
        # === DEĞİŞİKLİK BURADA ===
        self.history_list_widget.setStyleSheet("""
            QListWidget {
                border: 1px solid #555;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #444;
            }
            QListWidget::item:hover {
                background-color: #3399ff; /* Arka planı seçim mavisi yap */
            }
            QListWidget::item:selected {
                background-color: #0078d7; /* Tıklandığında kullanılacak renk */
            }
        """)
        self.history_list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        history_layout.addWidget(self.history_list_widget)
        clear_button = QPushButton("Clear History"); clear_button.clicked.connect(self.clear_history)
        history_layout.addWidget(clear_button)
        self.populate_history_list()

    def populate_history_list(self):
        self.history_list_widget.clear()
        for entry in translation_history:
            source_preview = (entry['source'].replace('\n', ' ')[:70] + '...') if len(entry['source']) > 70 else entry['source'].replace('\n', ' ')
            target_preview = entry['target'].replace('\n', ' ')
            display_text = f"{target_preview}\n(Source: {source_preview})"
            item = QListWidgetItem(display_text)
            item.setData(Qt.ItemDataRole.UserRole, entry['target'])
            self.history_list_widget.addItem(item)
            
    def history_item_clicked(self, item):
        original_target_text = item.data(Qt.ItemDataRole.UserRole)
        if original_target_text:
            clipboard = QApplication.clipboard(); clipboard.setText(original_target_text)
            self.status_label.setText(f"Copied to clipboard!")
            print(f"Copied from history: {original_target_text}")
        
    def clear_history(self):
        global translation_history
        reply = QMessageBox.question(self, "Clear History", "Are you sure you want to delete all translation history?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            translation_history = []; save_json(HISTORY_FILE, [])
            self.populate_history_list(); print("History cleared.")
            
    def open_settings_window(self):
        if self.settings_window is None or not self.settings_window.isVisible():
            self.settings_window = SettingsWindow(self.icon_path); self.settings_window.show()

    def save_settings_handler(self):
        global app_config;
        try:
            selected_source_lang = self.source_lang_combo.currentText(); app_config['source_lang'] = SUPPORTED_LANGUAGES[selected_source_lang]
            selected_target_lang = self.target_lang_combo.currentText(); app_config['target_lang'] = {k: v for k, v in SUPPORTED_LANGUAGES.items() if k != "Auto-Detect"}[selected_target_lang]
            save_json(CONFIG_FILE, app_config); self.status_label.setText("Language settings saved!")
        except Exception: self.status_label.setText("Error: Could not save settings.")

class Communicator(QObject): f8_pressed = pyqtSignal(); esc_pressed = pyqtSignal(); history_updated = pyqtSignal()

# ... (Diğer tüm sınıflar ve fonksiyonlar aynı)
class TranslationOverlay(QWidget):
    # Pencere bölgeleri için sabitler (kodun okunabilirliğini artırır)
    TOP_LEFT, TOP, TOP_RIGHT, LEFT, MOVE, RIGHT, BOTTOM_LEFT, BOTTOM, BOTTOM_RIGHT, NONE = range(10)

    def __init__(self, text, width, height):
        super().__init__()
        self.translated_text = text
        self.is_moving = False
        self.is_resizing = False
        self.resize_margin = 5 # Kenarlardan kaç piksellik alanın tutamaç olacağı
        self.resize_region = self.NONE
        
        self.start_pos = QPoint()
        self.start_geom = QRect()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.resize(width, height)
        self.setup_ui(text)

    def setup_ui(self, text):
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(15, 15, 15, 15)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; } QScrollBar:vertical {border: none; background: #3c3c3c; width: 10px; margin: 0px;} QScrollBar::handle:vertical {background: #808080; min-height: 20px; border-radius: 5px;}")
        
        self.text_label = QLabel(text, self)
        self.text_label.setFont(QFont("Arial", 14))
        self.text_label.setStyleSheet("background: transparent; color: white;")
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        
        self.scroll_area.setWidget(self.text_label)
        container_layout.addWidget(self.scroll_area)

        self.copy_button = QPushButton("Copy Text")
        self.copy_button.setStyleSheet("QPushButton { background-color: #555; color: white; border: none; padding: 8px; border-radius: 5px; } QPushButton:hover { background-color: #666; } QPushButton:pressed { background-color: #777; }")
        self.copy_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_button.clicked.connect(self.copy_to_clipboard)
        container_layout.addWidget(self.copy_button)

    def copy_to_clipboard(self):
        clipboard = QApplication.clipboard()
        clipboard.setText(self.translated_text)
        print("Text copied to clipboard.")
        self.copy_button.setText("Copied!")
        QTimer.singleShot(2000, lambda: self.copy_button.setText("Copy Text"))

    def get_region(self, pos):
        """Verilen pozisyonun pencerenin hangi bölgesinde olduğunu döndürür."""
        margin = self.resize_margin
        on_left = pos.x() >= 0 and pos.x() < margin
        on_right = pos.x() >= self.width() - margin and pos.x() < self.width()
        on_top = pos.y() >= 0 and pos.y() < margin
        on_bottom = pos.y() >= self.height() - margin and pos.y() < self.height()

        if on_top and on_left: return self.TOP_LEFT
        if on_top and on_right: return self.TOP_RIGHT
        if on_bottom and on_left: return self.BOTTOM_LEFT
        if on_bottom and on_right: return self.BOTTOM_RIGHT
        if on_top: return self.TOP
        if on_bottom: return self.BOTTOM
        if on_left: return self.LEFT
        if on_right: return self.RIGHT
        return self.MOVE

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.resize_region = self.get_region(event.pos())
            if self.resize_region != self.MOVE:
                self.is_resizing = True
            else:
                self.is_moving = True
            self.start_pos = event.globalPosition().toPoint()
            self.start_geom = self.geometry()

    def mouseMoveEvent(self, event):
        # Önce imlecin şeklini ayarla
        if not self.is_resizing and not self.is_moving:
            region = self.get_region(event.pos())
            if region in (self.TOP, self.BOTTOM): self.setCursor(Qt.CursorShape.SizeVerCursor)
            elif region in (self.LEFT, self.RIGHT): self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif region in (self.TOP_LEFT, self.BOTTOM_RIGHT): self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif region in (self.TOP_RIGHT, self.BOTTOM_LEFT): self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            else: self.setCursor(Qt.CursorShape.ArrowCursor)

        # Sonra taşıma veya yeniden boyutlandırma işlemini yap
        delta = event.globalPosition().toPoint() - self.start_pos
        new_geom = QRect(self.start_geom)

        if self.is_moving:
            self.move(new_geom.topLeft() + delta)
        elif self.is_resizing:
            if self.resize_region == self.TOP: new_geom.setTop(new_geom.top() + delta.y())
            elif self.resize_region == self.BOTTOM: new_geom.setBottom(new_geom.bottom() + delta.y())
            elif self.resize_region == self.LEFT: new_geom.setLeft(new_geom.left() + delta.x())
            elif self.resize_region == self.RIGHT: new_geom.setRight(new_geom.right() + delta.x())
            elif self.resize_region == self.TOP_LEFT: new_geom.setTopLeft(new_geom.topLeft() + delta)
            elif self.resize_region == self.TOP_RIGHT: new_geom.setTopRight(new_geom.topRight() + delta)
            elif self.resize_region == self.BOTTOM_LEFT: new_geom.setBottomLeft(new_geom.bottomLeft() + delta)
            elif self.resize_region == self.BOTTOM_RIGHT: new_geom.setBottomRight(new_geom.bottomRight() + delta)
            
            # Pencerenin çok küçülmesini engelle
            if new_geom.width() > 200 and new_geom.height() > 100:
                self.setGeometry(new_geom)

    def mouseReleaseEvent(self, event):
        self.is_moving = False
        self.is_resizing = False
        self.setCursor(Qt.CursorShape.ArrowCursor)
    
    def paintEvent(self, event):
        painter = QPainter(self); painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg_rect = self.rect(); painter.setBrush(QColor(0, 0, 0, 200)); painter.setPen(Qt.PenStyle.NoPen); painter.drawRoundedRect(bg_rect, 15, 15)
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
        raw_extracted_text = pytesseract.image_to_string(image, lang='eng').strip()
        text_with_preserved_breaks = raw_extracted_text.replace('\n\n', '[P_BREAK]'); text_single_line = text_with_preserved_breaks.replace('\n', ' '); processed_text = text_single_line.replace('[P_BREAK]', '\n\n')
        if not processed_text: return
        translator = deepl.Translator(api_key)
        source_lang = app_config.get('source_lang'); target_lang = app_config.get('target_lang')
        translate_kwargs = {'target_lang': target_lang}; 
        if source_lang and source_lang != 'Auto': translate_kwargs['source_lang'] = source_lang
        result = translator.translate_text(processed_text, **translate_kwargs); translated_text = result.text
        add_to_history(processed_text, translated_text)
        print(f"Translation ({source_lang} -> {target_lang}): '{translated_text}'")
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
    icon_path = resource_path("icon.ico")
    communicator = Communicator();
    main_window = MainWindow(icon_path); main_window.show()
    communicator.f8_pressed.connect(start_snipping); communicator.esc_pressed.connect(close_overlays)
    hotkey_thread = HotkeyListener(communicator); hotkey_thread.start()
    print("Control Panel opened. Program is running."); sys.exit(app.exec())
if __name__ == '__main__': main()