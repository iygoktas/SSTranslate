import sys
import threading
import deepl
import os
import ctypes
import json
from dotenv import load_dotenv

# .env dosyasındaki değişkenleri yükle
load_dotenv()

from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QScrollArea, QVBoxLayout, 
                             QHBoxLayout, QLineEdit, QPushButton, QComboBox)
from PyQt6.QtCore import Qt, QRect, QPoint, QObject, pyqtSignal
from PyQt6.QtGui import (QPainter, QColor, QPen, QGuiApplication, QFont, 
                         QIcon, QAction, QIntValidator)
from pynput import keyboard
from PIL import Image
import pytesseract

# --- Ayar Yönetimi ---
CONFIG_FILE = 'config.json'
# Varsayılan ayarlar ve desteklenen diller
DEFAULT_CONFIG = {
    'width': 800, 
    'height': 500, 
    'source_lang': 'Auto', 
    'target_lang': 'TR'
}
# DeepL API'sinin desteklediği bazı diller (Görünen İsim: API Kodu)
SUPPORTED_LANGUAGES = {
    "Auto-Detect": "Auto", "English": "EN", "Turkish": "TR", "German": "DE", 
    "French": "FR", "Spanish": "ES", "Italian": "IT", "Japanese": "JA", "Russian": "RU"
}

def load_config():
    """config.json dosyasından ayarları yükler. Dosya yoksa varsayılanları döndürür."""
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return DEFAULT_CONFIG

def save_config(config_data):
    """Verilen ayarları config.json dosyasına kaydeder."""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

# Uygulama başlarken ayarları yükle
app_config = load_config()

# --- Geliştirilmiş Kontrol Paneli ---
class MainWindow(QWidget):
    def __init__(self, icon_path):
        super().__init__()
        
        self.setWindowTitle("SSTranslate Control Panel")
        self.setWindowIcon(QIcon(icon_path))
        self.setMinimumSize(380, 250)
        
        main_layout = QVBoxLayout(self)
        
        # Dil Ayarları
        lang_group_label = QLabel("Language Settings")
        lang_group_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        main_layout.addWidget(lang_group_label)
        
        source_lang_layout = QHBoxLayout()
        source_lang_label = QLabel("Source Language:")
        self.source_lang_combo = QComboBox()
        self.source_lang_combo.addItems(SUPPORTED_LANGUAGES.keys())
        current_source_lang_code = app_config.get('source_lang', DEFAULT_CONFIG['source_lang'])
        current_source_lang_name = next((name for name, code in SUPPORTED_LANGUAGES.items() if code == current_source_lang_code), "Auto-Detect")
        self.source_lang_combo.setCurrentText(current_source_lang_name)
        source_lang_layout.addWidget(source_lang_label)
        source_lang_layout.addWidget(self.source_lang_combo)
        main_layout.addLayout(source_lang_layout)

        target_lang_layout = QHBoxLayout()
        target_lang_label = QLabel("Target Language:")
        self.target_lang_combo = QComboBox()
        # Hedef dilde "Auto-Detect" olmaz
        target_langs = {k: v for k, v in SUPPORTED_LANGUAGES.items() if k != "Auto-Detect"}
        self.target_lang_combo.addItems(target_langs.keys())
        current_target_lang_code = app_config.get('target_lang', DEFAULT_CONFIG['target_lang'])
        current_target_lang_name = next((name for name, code in SUPPORTED_LANGUAGES.items() if code == current_target_lang_code), "Turkish")
        self.target_lang_combo.setCurrentText(current_target_lang_name)
        target_lang_layout.addWidget(target_lang_label)
        target_lang_layout.addWidget(self.target_lang_combo)
        main_layout.addLayout(target_lang_layout)
        
        # Boyut Ayarları
        size_group_label = QLabel("Overlay Size Settings")
        size_group_label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
        main_layout.addWidget(size_group_label)
        
        size_layout = QHBoxLayout()
        self.width_input = QLineEdit(str(app_config.get('width')))
        self.width_input.setValidator(QIntValidator(200, 3840)) # Sadece sayısal değerler
        self.height_input = QLineEdit(str(app_config.get('height')))
        self.height_input.setValidator(QIntValidator(100, 2160)) # Sadece sayısal değerler
        size_layout.addWidget(QLabel("Width:"))
        size_layout.addWidget(self.width_input)
        size_layout.addWidget(QLabel("Height:"))
        size_layout.addWidget(self.height_input)
        main_layout.addLayout(size_layout)

        # Kaydet Butonu ve Durum
        self.save_button = QPushButton("Save Settings")
        self.save_button.clicked.connect(self.save_settings_handler)
        self.status_label = QLabel("Press F8 to translate.")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(self.save_button)
        main_layout.addWidget(self.status_label)

    def save_settings_handler(self):
        """Kaydet butonuna basıldığında ayarları günceller ve dosyaya yazar."""
        global app_config
        try:
            # Seçilen dillerin API kodlarını al
            selected_source_lang = self.source_lang_combo.currentText()
            app_config['source_lang'] = SUPPORTED_LANGUAGES[selected_source_lang]
            
            selected_target_lang = self.target_lang_combo.currentText()
            app_config['target_lang'] = {k: v for k, v in SUPPORTED_LANGUAGES.items() if k != "Auto-Detect"}[selected_target_lang]

            # Boyutları al
            app_config['width'] = int(self.width_input.text())
            app_config['height'] = int(self.height_input.text())
            
            save_config(app_config)
            self.status_label.setText("Settings saved successfully!")
            print("Settings saved:", app_config)
        except Exception as e:
            self.status_label.setText(f"Error: Could not save settings.")
            print(f"Error saving settings: {e}")

# --- Diğer Sınıflar ve Fonksiyonlar ---
class Communicator(QObject):
    f8_pressed = pyqtSignal()
    esc_pressed = pyqtSignal()

class TranslationOverlay(QWidget):
    def __init__(self, text, width, height):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(width, height)
        container_layout = QVBoxLayout(self)
        container_layout.setContentsMargins(15, 15, 15, 15)
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; border: none; }
            QScrollBar:vertical {
                border: none; background: #3c3c3c; width: 10px; margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #808080; min-height: 20px; border-radius: 5px;
            }
        """)
        self.text_label = QLabel(text, self)
        self.text_label.setFont(QFont("Arial", 14))
        self.text_label.setStyleSheet("background: transparent; color: white;")
        self.text_label.setWordWrap(True)
        self.text_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.text_label)
        container_layout.addWidget(self.scroll_area)
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg_rect = self.rect()
        painter.setBrush(QColor(0, 0, 0, 200))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(bg_rect, 15, 15)

class SnippingWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.begin = QPoint()
        self.end = QPoint()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setGeometry(QGuiApplication.primaryScreen().geometry())
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.show()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            print("Selection canceled.")
            self.close()
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 70))
        rect = QRect(self.begin, self.end)
        pen = QPen(Qt.GlobalColor.white, 2, Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.drawRect(rect.normalized())
    def mousePressEvent(self, event):
        self.begin = event.pos()
        self.end = event.pos()
        self.update()
    def mouseMoveEvent(self, event):
        self.end = event.pos()
        self.update()
    def mouseReleaseEvent(self, event):
        self.close()
        capture_and_translate(QRect(self.begin, self.end).normalized())

snipping_widget = None
translation_overlay = None

def capture_and_translate(rect):
    global translation_overlay, app_config
    try:
        api_key = os.getenv("DEEPL_API_KEY")
        if not api_key:
            print("ERROR: DEEPL_API_KEY not found in the .env file.")
            return
        
        screenshot = QGuiApplication.primaryScreen().grabWindow(0, rect.x(), rect.y(), rect.width(), rect.height())
        buffer = screenshot.toImage()
        image_bits = buffer.bits()
        image_bits.setsize(buffer.sizeInBytes())
        image_bytes = image_bits.asstring()
        image = Image.frombytes("RGBA", (buffer.width(), buffer.height()), image_bytes, "raw", "BGRA").convert("L")
        
        raw_extracted_text = pytesseract.image_to_string(image, lang='eng').strip()
        
        text_with_preserved_breaks = raw_extracted_text.replace('\n\n', '[P_BREAK]')
        text_single_line = text_with_preserved_breaks.replace('\n', ' ')
        processed_text = text_single_line.replace('[P_BREAK]', '\n\n')
        
        print(f"Recognized Text (Processed):\n---\n{processed_text}\n---")
        if not processed_text: return
        
        translator = deepl.Translator(api_key)
        
        # Ayarlardan kaynak ve hedef dili al
        source_lang = app_config.get('source_lang')
        target_lang = app_config.get('target_lang')
        
        # DeepL'e gönderilecek parametreleri hazırla
        translate_kwargs = {'target_lang': target_lang}
        if source_lang and source_lang != 'Auto':
            translate_kwargs['source_lang'] = source_lang
            
        result = translator.translate_text(processed_text, **translate_kwargs)
        translated_text = result.text

        print(f"Translation ({source_lang} -> {target_lang}): '{translated_text}'")
        if translation_overlay and translation_overlay.isVisible():
            translation_overlay.close()
        
        # Ayarlardan kutu boyutlarını al
        box_width = app_config.get('width')
        box_height = app_config.get('height')
        translation_overlay = TranslationOverlay(translated_text, box_width, box_height)
        
        screen_geometry = QGuiApplication.primaryScreen().geometry()
        x_pos = (screen_geometry.width() - box_width) / 2
        y_pos = (screen_geometry.height() - box_height) / 2
        
        translation_overlay.move(int(x_pos), int(y_pos))
        translation_overlay.show()

    except deepl.DeepLException as e:
        print(f"An error occurred with the DeepL API: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")

def start_snipping():
    global snipping_widget
    snipping_widget = SnippingWidget()

def close_overlays():
    global translation_overlay, snipping_widget
    if translation_overlay and translation_overlay.isVisible():
        print("Translation overlay closed.")
        translation_overlay.close()
    if snipping_widget and snipping_widget.isVisible():
        print("Selection screen closed.")
        snipping_widget.close()

class HotkeyListener(threading.Thread):
    def __init__(self, communicator):
        super().__init__()
        self.communicator = communicator
        self.daemon = True
    def run(self):
        def on_press(key):
            if key == keyboard.Key.f8:
                self.communicator.f8_pressed.emit()
            elif key == keyboard.Key.esc:
                self.communicator.esc_pressed.emit()
        with keyboard.Listener(on_press=on_press) as listener:
            listener.join()

def main():
    myappid = 'mycompany.screentranslator.1.0'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    
    app = QApplication(sys.argv)
    
    script_dir = os.path.dirname(os.path.realpath(__file__))
    icon_path = os.path.join(script_dir, "icon.ico")
    
    main_window = MainWindow(icon_path)
    main_window.show()
    
    communicator = Communicator()
    communicator.f8_pressed.connect(start_snipping)
    communicator.esc_pressed.connect(close_overlays)
    
    hotkey_thread = HotkeyListener(communicator)
    hotkey_thread.start()
    
    print("Control Panel opened. Program is running.")
    sys.exit(app.exec())


if __name__ == '__main__':
    main()