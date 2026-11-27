"""Minimal Supabase Storage REST client (needs only `requests`; no Django import).

Auth: sends the key in the `apikey` header only. That works for both the new
`sb_publishable_...` / `sb_secret_...` keys and the legacy anon / service_role JWTs.
"""
from urllib.parse import quote

import requests

DEFAULT_URL = "https://veivaeudhxwgpsuxywws.supabase.co"
DEFAULT_PUBLISHABLE_KEY = "sb_publishable_DIibMgRQFIZ4mwpKIzG3kA_hvkmwc4C"
TIMEOUT = 30


class SupabaseStorageError(OSError):
    """Raised when Supabase Storage rejects or fails a request."""


class SupabaseNotFound(SupabaseStorageError, FileNotFoundError):
    """Object does not exist (HTTP 404 / 400 'not found')."""


class SupabaseClient:
    def __init__(self, url, key, timeout=TIMEOUT):
        if not url or not key:
            raise ValueError("Supabase URL and key are both required.")
        self.base = url.rstrip("/") + "/storage/v1"
        self.key = key
        self.timeout = timeout

    # -- helpers ---------------------------------------------------------
    @staticmethod
    def _path(name):
        return quote(str(name).lstrip("/"), safe="/")

    def _headers(self, extra=None):
        headers = {"apikey": self.key}
        if extra:
            headers.update(extra)
        return headers

    def _request(self, method, url, **kwargs):
        try:
            return requests.request(
                method, url, headers=self._headers(kwargs.pop("headers", None)),
                timeout=self.timeout, **kwargs,
            )
        except requests.RequestException as exc:
            raise SupabaseStorageError(f"Could not reach Supabase Storage: {exc}") from exc

    @staticmethod
    def _fail(resp, action):
        text = (resp.text or "")[:300]
        if resp.status_code == 404 or "not_found" in text.lower() or "not found" in text.lower():
            raise SupabaseNotFound(f"{action}: object not found")
        hint = ""
        if resp.status_code in (400, 401, 403) and (
            "row-level security" in text.lower() or "unauthorized" in text.lower()
        ):
            hint = (" - the bucket's Storage policies block this key. Run supabase_setup.sql "
                    "or set SUPABASE_SECRET_KEY on the server.")
        raise SupabaseStorageError(f"{action} failed (HTTP {resp.status_code}): {text}{hint}")

    # -- operations ------------------------------------------------------
    def public_url(self, bucket, name):
        return f"{self.base}/object/public/{bucket}/{self._path(name)}"

    def upload(self, bucket, name, data, content_type="application/octet-stream"):
        resp = self._request(
            "POST", f"{self.base}/object/{bucket}/{self._path(name)}", data=data,
            headers={"Content-Type": content_type, "x-upsert": "false", "cache-control": "max-age=3600"},
        )
        if resp.status_code not in (200, 201):
            self._fail(resp, f"Upload to '{bucket}'")
        return name

    def download(self, bucket, name):
        resp = self._request("GET", f"{self.base}/object/authenticated/{bucket}/{self._path(name)}")
        if resp.status_code != 200:
            self._fail(resp, f"Download from '{bucket}'")
        return resp.content

    def size(self, bucket, name):
        resp = self._request("HEAD", f"{self.base}/object/authenticated/{bucket}/{self._path(name)}")
        if resp.status_code != 200:
            self._fail(resp, f"Stat in '{bucket}'")
        return int(resp.headers.get("Content-Length", 0))

    def delete(self, bucket, name):
        resp = self._request(
            "DELETE", f"{self.base}/object/{bucket}", json={"prefixes": [str(name).lstrip("/")]},
        )
        if resp.status_code not in (200, 204):
            self._fail(resp, f"Delete from '{bucket}'")
