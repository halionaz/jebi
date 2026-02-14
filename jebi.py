import os
import socket
import ssl


class URL:
    def __init__(self, url):
        if url.startswith("data:"):
            self.scheme = "data"
            _, self.data = url.split(",", 1)
            return

        self.scheme, url = url.split("://", 1)
        assert self.scheme in ["http", "https", "file"]

        if self.scheme == "file":
            self.path = "/" + url.lstrip("/")
            return

        if "/" not in url:
            url = url + "/"
        self.host, url = url.split("/", 1)
        self.path = "/" + url

        if self.scheme == "http":
            self.port = 80
        elif self.scheme == "https":
            self.port = 443

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def build_headers(self):
        headers = {
            "Host": self.host,
            "User-Agent": "jebi/1.0",
            "Connection": "close",
        }
        return "".join(f"{header}: {value}\r\n" for header, value in headers.items())

    def request(self):
        if self.scheme == "data":
            return self.data

        if self.scheme == "file":
            with open(self.path, "r", encoding="utf8") as f:
                return f.read()

        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        request = f"GET {self.path} HTTP/1.1\r\n"
        request += self.build_headers()
        request += "\r\n"
        s.send(request.encode("utf8"))

        response = s.makefile("r", encoding="utf8", newline="\r\n")
        statusline = response.readline()
        version, status, explanation = statusline.split(" ", 2)
        response_headers = {}
        while True:
            line = response.readline()
            if line == "\r\n":
                break
            header, value = line.split(":", 1)
            response_headers[header.casefold()] = value.strip()

        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers

        body = response.read()
        s.close()
        return body


def show(body, view_source=False):
    if view_source:
        print(body, end="")
        return

    in_tag = False
    i = 0
    while i < len(body):
        c = body[i]
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            if body.startswith("&lt;", i):
                print("<", end="")
                i += 3
            elif body.startswith("&gt;", i):
                print(">", end="")
                i += 3
            else:
                print(c, end="")
        i += 1


def load(url: URL, view_source=False):
    body = url.request()
    show(body, view_source=view_source)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        default_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "default.txt"
        )
        url = "file://" + default_path

    view_source = url.startswith("view-source:")
    if view_source:
        url = url[len("view-source:") :]

    load(URL(url), view_source=view_source)
