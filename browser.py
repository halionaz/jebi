"""Browser GUI and rendering."""

import tkinter

from constants import WIDTH, HEIGHT, VSTEP, MAX_REDIRECTS
from url import URL
from rendering import lex, layout


class Browser:
    """Main browser window with canvas rendering and scrolling."""

    def __init__(self):
        self.window = tkinter.Tk()
        self.canvas = tkinter.Canvas(
            self.window,
            width=WIDTH,
            height=HEIGHT,
        )
        self.canvas.pack()
        self.scroll = 0
        self.window.bind("<Down>", self.scroll_down)
        self.window.bind("<Up>", self.scroll_up)

    def draw(self):
        """Render the display list on canvas."""
        self.canvas.delete("all")
        for x, y, c in self.display_list:
            if y > self.scroll + HEIGHT:
                continue
            if y + VSTEP < self.scroll:
                continue
            self.canvas.create_text(x, y - self.scroll, text=c)

    def load(self, url: URL, view_source=False):
        """Load URL with redirect handling."""
        redirect_count = 0
        current_url = url

        while True:
            status, headers, body = current_url.request_response()
            if 300 <= status < 400:
                assert redirect_count < MAX_REDIRECTS, "too many redirects"
                assert "location" in headers

                next_url = current_url.resolve(headers["location"])
                current_url = URL(next_url)
                redirect_count += 1
                continue
            break

        text = lex(body, view_source=view_source)
        self.display_list = layout(text)
        self.draw()

    def scroll_down(self, e):
        """Scroll down by 100 pixels."""
        self.scroll += 100
        self.draw()

    def scroll_up(self, e):
        """Scroll up by 100 pixels."""
        self.scroll = max(0, self.scroll - 100)
        self.draw()
