import os
import socket
import ssl
import time


HTTP_PORT = 80
HTTPS_PORT = 443
MAX_REDIRECTS = 10
USER_AGENT = "jebi/1.0"
DEFAULT_FILE = "default.txt"


class URL:
    connections = {}
    cache = {}

    def __init__(self, raw_url):
        if raw_url.startswith("data:"):
            self._parse_data_url(raw_url)
            return

        self.scheme, url = raw_url.split("://", 1)
        assert self.scheme in ["http", "https", "file"]

        if self.scheme == "file":
            self._parse_file_url(url)
            return

        self._parse_http_url(url)

    def _parse_data_url(self, raw_url):
        self.scheme = "data"
        _, self.data = raw_url.split(",", 1)

    def _parse_file_url(self, url):
        self.path = "/" + url.lstrip("/")

    def _parse_http_url(self, url):
        if "/" not in url:
            url += "/"

        self.host, path = url.split("/", 1)
        self.path = "/" + path
        self.port = HTTP_PORT if self.scheme == "http" else HTTPS_PORT

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def build_headers(self):
        headers = {
            "Host": self.host,
            "User-Agent": USER_AGENT,
        }
        return "".join(f"{header}: {value}\r\n" for header, value in headers.items())

    def connection_key(self):
        return (self.scheme, self.host, self.port)

    def cache_key(self):
        return (self.scheme, self.host, self.port, self.path)

    def open_connection(self):
        s = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        s.connect((self.host, self.port))

        if self.scheme == "https":
            ctx = ssl.create_default_context()
            s = ctx.wrap_socket(s, server_hostname=self.host)

        return (s, s.makefile("rb"))

    def get_connection(self):
        key = self.connection_key()
        if key not in URL.connections:
            URL.connections[key] = self.open_connection()
        return URL.connections[key]

    def drop_connection(self):
        key = self.connection_key()
        if key not in URL.connections:
            return

        s, response = URL.connections.pop(key)
        response.close()
        s.close()

    def origin(self):
        if self.scheme == "http" and self.port == HTTP_PORT:
            return f"{self.scheme}://{self.host}"
        if self.scheme == "https" and self.port == HTTPS_PORT:
            return f"{self.scheme}://{self.host}"
        return f"{self.scheme}://{self.host}:{self.port}"

    def resolve(self, location):
        if location.startswith("/"):
            return self.origin() + location
        return location

    def _build_http_request(self):
        request = f"GET {self.path} HTTP/1.1\r\n"
        request += self.build_headers()
        request += "\r\n"
        return request

    def _read_status(self, response):
        statusline = response.readline()
        if statusline == b"":
            raise ConnectionError("closed")

        _version, status, _explanation = statusline.decode("utf8").split(" ", 2)
        return int(status)

    def _read_headers(self, response):
        response_headers = {}
        while True:
            line = response.readline()
            if line == b"\r\n":
                break

            header, value = line.decode("utf8").split(":", 1)
            response_headers[header.casefold()] = value.strip()
        return response_headers

    def _read_http_body(self, response, response_headers):
        assert "transfer-encoding" not in response_headers
        assert "content-encoding" not in response_headers
        assert "content-length" in response_headers

        content_length = int(response_headers["content-length"])
        return response.read(content_length).decode("utf8")

    def _request_over_http(self):
        retry_errors = (
            ConnectionError,
            BrokenPipeError,
            ConnectionResetError,
            OSError,
        )

        for _ in range(2):
            s, response = self.get_connection()
            try:
                request = self._build_http_request()
                s.sendall(request.encode("utf8"))

                status = self._read_status(response)
                response_headers = self._read_headers(response)
                body = self._read_http_body(response, response_headers)
                return (status, response_headers, body)
            except retry_errors:
                self.drop_connection()

        raise AssertionError("could not fetch response")

    def _read_cache(self):
        key = self.cache_key()
        if key not in URL.cache:
            return None

        status, response_headers, body, expires_at = URL.cache[key]
        if expires_at is not None and time.time() > expires_at:
            del URL.cache[key]
            return None

        return (status, response_headers, body)

    def _cache_policy(self, response_headers):
        if "cache-control" not in response_headers:
            return (True, None)

        directives = [
            item.strip().casefold()
            for item in response_headers["cache-control"].split(",")
        ]
        max_age = None
        for directive in directives:
            if directive == "no-store":
                return (False, None)
            if directive.startswith("max-age="):
                value = directive.split("=", 1)[1]
                if not value.isdigit():
                    return (False, None)
                max_age = int(value)
                continue
            return (False, None)

        if max_age is None:
            return (True, None)
        return (True, time.time() + max_age)

    def _write_cache(self, status, response_headers, body):
        if status != 200:
            return

        should_cache, expires_at = self._cache_policy(response_headers)
        if not should_cache:
            return

        URL.cache[self.cache_key()] = (status, response_headers, body, expires_at)

    def request_response(self):
        if self.scheme == "data":
            return (200, {}, self.data)

        if self.scheme == "file":
            with open(self.path, "r", encoding="utf8") as f:
                return (200, {}, f.read())

        cached = self._read_cache()
        if cached is not None:
            return cached

        status, response_headers, body = self._request_over_http()
        self._write_cache(status, response_headers, body)
        return (status, response_headers, body)

    def request(self):
        _, _, body = self.request_response()
        return body


def show(body, view_source=False):
    if view_source:
        print(body, end="")
        return

    in_tag = False
    i = 0
    while i < len(body):
        if not in_tag and body.startswith("&lt;", i):
            print("<", end="")
            i += 4
            continue

        if not in_tag and body.startswith("&gt;", i):
            print(">", end="")
            i += 4
            continue

        c = body[i]
        if c == "<":
            in_tag = True
        elif c == ">":
            in_tag = False
        elif not in_tag:
            print(c, end="")
        i += 1


def load(url: URL, view_source=False):
    redirect_count = 0
    current_url = url

    while True:
        status, response_headers, body = current_url.request_response()
        if 300 <= status < 400:
            assert redirect_count < MAX_REDIRECTS, "too many redirects"
            assert "location" in response_headers
            next_url = current_url.resolve(response_headers["location"])
            current_url = URL(next_url)
            redirect_count += 1
            continue
        break

    show(body, view_source=view_source)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        url = sys.argv[1]
    else:
        default_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), DEFAULT_FILE
        )
        url = "file://" + default_path

    view_source = url.startswith("view-source:")
    if view_source:
        url = url[len("view-source:") :]

    load(URL(url), view_source=view_source)
