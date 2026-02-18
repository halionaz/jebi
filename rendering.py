"""HTML parsing and text layout."""

from constants import WIDTH, HSTEP, VSTEP


def lex(body, view_source=False):
    """Parse HTML and remove tags, handle HTML entities."""
    if view_source:
        return body

    text = ""
    in_tag = False
    index = 0

    while index < len(body):
        if not in_tag and body.startswith("&lt;", index):
            text += "<"
            index += 4
            continue

        if not in_tag and body.startswith("&gt;", index):
            text += ">"
            index += 4
            continue

        char = body[index]
        if char == "<":
            in_tag = True
        elif char == ">":
            in_tag = False
        elif not in_tag:
            text += char

        index += 1

    return text


def layout(text):
    """Calculate text layout positions."""
    display_list = []
    cursor_x, cursor_y = HSTEP, VSTEP
    for c in text:
        display_list.append((cursor_x, cursor_y, c))
        cursor_x += HSTEP

        if cursor_x >= WIDTH - HSTEP:
            cursor_x = HSTEP
            cursor_y += VSTEP
    return display_list
