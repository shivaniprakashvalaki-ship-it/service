
"""Django storage backend that keeps uploaded files in Supabase Storage."""

import mimetypes
import os
import posixpath
import unicodedata
import uuid

from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible
from django.utils.text import get_valid_filename

from supabase_client import SupabaseClient


@deconstructible
class SupabaseStorage(Storage):

    def __init__(self, bucket, public, url, key):
        self.bucket = bucket
        self.public = public
        self.client = SupabaseClient(url, key)

    def get_available_name(self, name, max_length=None):

        dirname, basename = posixpath.split(
            str(name).replace("\\", "/")
        )

        ascii_name = (
            unicodedata.normalize("NFKD", basename)
            .encode("ascii", "ignore")
            .decode()
        )

        stem, ext = os.path.splitext(
            get_valid_filename(ascii_name) or "file"
        )

        stem = stem or "file"

        token = uuid.uuid4().hex[:12]

        budget = (
            (max_length or 100)
            - len(dirname)
            - len(token)
            - len(ext)
            - 2
        )

        stem = stem[:max(budget, 1)]

        return posixpath.join(
            dirname,
            f"{token}_{stem}{ext.lower()}"
        )

    def _save(self, name, content):

        if hasattr(content, "seek"):
            content.seek(0)

        data = content.read()

        ctype = (
            mimetypes.guess_type(name)[0]
            or getattr(content, "content_type", None)
            or "application/octet-stream"
        )

        self.client.upload(
            self.bucket,
            name,
            data,
            ctype
        )

        return name

    def _open(self, name, mode="rb"):

        return ContentFile(
            self.client.download(self.bucket, name),
            name=name
        )

    def delete(self, name):

        if name:
            self.client.delete(self.bucket, name)

    def exists(self, name):

        return False

    def size(self, name):

        return self.client.size(self.bucket, name)

    def url(self, name):

        if self.public:
            return self.client.public_url(
                self.bucket,
                name
            )

        return ""
