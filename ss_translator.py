import sys
import threading
import deepl
import os
import ctypes
from dotenv import load_dotenv

load_dotenv()

from PyQt6.QtWidgets import QApplication, QWidget, QLabel, QScrollArea, QVBoxLayout
from PyQt6.QtCore import Qt, QRect, QPoint, QObject, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QGuiApplication, QFont, QIcon, QAction
from pynput import keyboard
from PIL import Image
import pytesseract

# Translation overlay dimensions
BOX_WIDTH = 800
BOX_HEIGHT = 500


class MainWindow(QWidget):
    def __init__(self, icon_path):
        super().__init__()
        
        # Window settings
        self.setWindowTitle("SSTranslate Info Panel")
        self.setWindowIcon(QIcon(icon_path))
        self.setFixedSize(350, 150)
        
        layout = QVBoxLayout(self)
        info_label = QLabel(
            "Program is running in the background.\n\n"
            "Press F8 to start a translation.\n"
            "You can close the pop-up windows with ESC."
        )
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setFont(QFont("Arial", 10))
        layout.addWidget(info_label)


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
    global translation_overlay
    try:
        api_key = os.getenv("DEEPL_API_KEY")
        if not api_key:
            print("ERROR: DEEPL_API_KEY not found in the .env file.")
            print("Please ensure a .env file exists in the main directory and contains DEEPL_API_KEY='...'")
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
        result = translator.translate_text(processed_text, target_lang="TR")
        translated_text = result.text

        print(f"Translation: '{translated_text}'")
        if translation_overlay and translation_overlay.isVisible():
            translation_overlay.close()
        
        translation_overlay = TranslationOverlay(translated_text, BOX_WIDTH, BOX_HEIGHT)
        
        screen_geometry = QGuiApplication.primaryScreen().geometry()
        x_pos = (screen_geometry.width() - BOX_WIDTH) / 2
        y_pos = (screen_geometry.height() - BOX_HEIGHT) / 2
        
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
    
    print("Info Panel opened. The program is running.")
    
    sys.exit(app.exec())


if __name__ == '__main__':
    main()