# On-the-Fly Screen Translator

A powerful desktop tool for Windows that allows you to instantly translate any text on your screen. Simply select an area with your mouse, and get a clean, centered overlay with the high-quality translation provided by the DeepL API.

---

### ✨ Core Features

- **Hotkey Activation:** Press `F8` to activate the screen capture mode at any time.
- **Region Selection:** Simply click and drag to select the exact text you want to translate.
- **High-Quality Translation:** Utilizes the powerful DeepL API for accurate and context-aware translations.
- **Smart Text Processing:** Intelligently handles line breaks to preserve paragraph structure while ensuring correct translation context.
- **Customizable Overlay:** A clean, centered overlay displays the translated text. The overlay size is configurable.
- **Scrollable Text:** Long translations that don't fit in the box can be easily scrolled through.
- **Full Control:** Press `ESC` to close any pop-up window. The application is managed via a simple control panel on your taskbar.

### 🛠️ Technologies Used

- **Python 3**
- **GUI Framework:** PyQt6
- **OCR Engine:** Tesseract
- **Translation Service:** DeepL API
- **Global Hotkeys:** Pynput
- **Image Processing:** Pillow

### 📋 Prerequisites

To run this application, the following must be installed on the system:

1.  **Python 3.9+**
2.  **Tesseract OCR Engine:**
    - Must be installed from the [official Tesseract page](https://github.com/UB-Mannheim/tesseract/wiki).
    - During installation, Tesseract must be added to the system's **PATH** environment variable.

### 📜 License

This project is proprietary and all rights are reserved. Please see the [LICENSE](LICENSE) file for more details.

Copyright (c) 2025 İbrahim Yasin Göktaş
