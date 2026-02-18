"""URL handling, HTTP requests, and caching."""

import gzip
import socket
import ssl
import time

from constants import (
    HTTP_PORT,
    HTTPS_PORT,
    MAX_REQUEST_RETRIES,
    USER_AGENT,
)


class URL:
    """Handles URL parsing, HTTP connections, and caching."""

    connections = {}
    cache = {}

    def __init__(self, raw_url):
        if raw_url.startswith("data:"):
            self._parse_data_url(raw_url)
            return

        self.scheme, rest = raw_url.split("://", 1)
        assert self.scheme in ["http", "https", "file"]

        if self.scheme == "file":
            self._parse_file_url(rest)
            return

        self._parse_http_url(rest)

    def _parse_data_url(self, raw_url):
        self.scheme = "data"
        _, self.data = raw_url.split(",", 1)

    def _parse_file_url(self, rest):
        self.path = "/" + rest.lstrip("/")

    def _parse_http_url(self, rest):
        if "/" not in rest:
            rest += "/"

        self.host, path = rest.split("/", 1)
        self.path = "/" + path
        self.port = HTTP_PORT if self.scheme == "http" else HTTPS_PORT

        if ":" in self.host:
            self.host, port = self.host.split(":", 1)
            self.port = int(port)

    def build_headers(self):
        headers = {
            "Host": self.host,
            "User-Agent": USER_AGENT,
            "Accept-Encoding": "gzip",
        }
        return "".join(f"{name}: {value}\r\n" for name, value in headers.items())

    def connection_key(self):
        return (self.scheme, self.host, self.port)

    def cache_key(self):
        return (self.scheme, self.host, self.port, self.path)

    def open_connection(self):
        sock = socket.socket(
            family=socket.AF_INET,
            type=socket.SOCK_STREAM,
            proto=socket.IPPROTO_TCP,
        )
        sock.connect((self.host, self.port))

        if self.scheme == "https":
            context = ssl.create_default_context()
            sock = context.wrap_socket(sock, server_hostname=self.host)

        return (sock, sock.makefile("rb"))

    def get_connection(self):
        key = self.connection_key()
        if key not in URL.connections:
            URL.connections[key] = self.open_connection()
        return URL.connections[key]

    def drop_connection(self):
        key = self.connection_key()
        if key not in URL.connections:
            return

        sock, response = URL.connections.pop(key)
        response.close()
        sock.close()

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
        status_line = response.readline()
        if status_line == b"":
            raise ConnectionError("closed")

        _version, status, _explanation = status_line.decode("utf8").split(" ", 2)
        return int(status)

    def _read_headers(self, response):
        headers = {}
        while True:
            line = response.readline()
            if line == b"\r\n":
                break

            name, value = line.decode("utf8").split(":", 1)
            headers[name.casefold()] = value.strip()
        return headers

    def _read_chunked_body(self, response):
        chunks = []
        while True:
            chunk_size_line = response.readline().decode("utf8").strip()
            chunk_size = int(chunk_size_line.split(";", 1)[0], 16)
            if chunk_size == 0:
                while response.readline() != b"\r\n":
                    pass
                break

            chunks.append(response.read(chunk_size))
            assert response.read(2) == b"\r\n"

        return b"".join(chunks)

    def _read_body_bytes(self, response, headers):
        if headers.get("transfer-encoding") == "chunked":
            return self._read_chunked_body(response)

        assert "transfer-encoding" not in headers
        assert "content-length" in headers

        content_length = int(headers["content-length"])
        return response.read(content_length)

    def _decode_body(self, body_bytes, headers):
        if headers.get("content-encoding") == "gzip":
            body_bytes = gzip.decompress(body_bytes)
        else:
            assert "content-encoding" not in headers
        return body_bytes.decode("utf8")

    def _request_over_http(self):
        retry_errors = (
            ConnectionError,
            BrokenPipeError,
            ConnectionResetError,
            OSError,
        )

        for _ in range(MAX_REQUEST_RETRIES):
            sock, response = self.get_connection()
            try:
                sock.sendall(self._build_http_request().encode("utf8"))

                status = self._read_status(response)
                headers = self._read_headers(response)
                body_bytes = self._read_body_bytes(response, headers)
                body = self._decode_body(body_bytes, headers)
                return (status, headers, body)
            except retry_errors:
                self.drop_connection()

        raise AssertionError("could not fetch response")

    def _read_cache(self):
        key = self.cache_key()
        if key not in URL.cache:
            return None

        status, headers, body, expires_at = URL.cache[key]
        if expires_at is not None and time.time() > expires_at:
            del URL.cache[key]
            return None

        return (status, headers, body)

    def _cache_policy(self, headers):
        cache_control = headers.get("cache-control")
        if cache_control is None:
            return (True, None)

        directives = [token.strip().casefold() for token in cache_control.split(",")]
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

    def _write_cache(self, status, headers, body):
        if status != 200:
            return

        should_cache, expires_at = self._cache_policy(headers)
        if not should_cache:
            return

        URL.cache[self.cache_key()] = (status, headers, body, expires_at)

    def _request_data(self):
        return (200, {}, self.data)

    def _request_file(self):
        with open(self.path, "r", encoding="utf8") as file_obj:
            return (200, {}, file_obj.read())

    def request_response(self):
        if self.scheme == "data":
            return self._request_data()

        if self.scheme == "file":
            return self._request_file()

        cached = self._read_cache()
        if cached is not None:
            return cached

        status, headers, body = self._request_over_http()
        self._write_cache(status, headers, body)
        return (status, headers, body)

    def request(self):
        _, _, body = self.request_response()
        return body
