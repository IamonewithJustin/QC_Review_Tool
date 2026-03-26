"""Entry point for the AI QC Document Reviewer application."""

import sys
from pathlib import Path

# Ensure the project root is on sys.path regardless of working directory
sys.path.insert(0, str(Path(__file__).parent))

from ui.main_window import MainWindow


def main():
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
