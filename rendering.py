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
    """Calculate text layout positions with newline support."""
    display_list = []
    cursor_x, cursor_y = HSTEP, VSTEP
    for c in text:
        if c == '\n':
            # 줄바꿈: 새 줄 시작하고 단락 구분을 위해 y 간격 약간 늘림
            cursor_x = HSTEP
            cursor_y += int(VSTEP * 1.5)
            continue

        display_list.append((cursor_x, cursor_y, c))
        cursor_x += HSTEP

        if cursor_x >= WIDTH - HSTEP:
            cursor_x = HSTEP
            cursor_y += VSTEP
    return display_list
