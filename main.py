"""
RealSense RGB-D 采集工具 —— 程序入口。

运行方式:
    python main.py
"""

import sys
import logging
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RealSense RGB-D 采集工具")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
