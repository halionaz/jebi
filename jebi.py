"""Main entry point for jebi browser."""

import os
import sys
import tkinter

from constants import DEFAULT_FILE
from url import URL
from browser import Browser


def main():
    """Run the jebi browser."""
    if len(sys.argv) > 1:
        raw_url = sys.argv[1]
    else:
        default_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), DEFAULT_FILE
        )
        raw_url = "file://" + default_path

    view_source = raw_url.startswith("view-source:")
    if view_source:
        raw_url = raw_url[len("view-source:") :]

    Browser().load(URL(raw_url), view_source=view_source)
    tkinter.mainloop()


if __name__ == "__main__":
    main()
