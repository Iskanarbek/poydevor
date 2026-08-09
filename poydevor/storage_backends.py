"""Custom Django Storage backend for Vercel Blob.

Vercel's serverless functions run on a read-only filesystem, so uploads
saved via Django's default FileSystemStorage silently fail to persist
between requests. This backend sends uploads to Vercel Blob instead,
which is real, persistent, CDN-backed object storage that already
integrates with a Vercel project (no extra third-party account needed).

Only used when BLOB_READ_WRITE_TOKEN is set (see settings.py) — falls
back to the normal local FileSystemStorage otherwise, so local
development is unaffected.

Vercel Blob's `put()` returns a full CDN URL, not a path relative to
some fixed base — there's no way to reconstruct that URL from a bare
"name" the way FileSystemStorage can. So this backend stores the
*entire returned URL* as the FileField/ImageField's `name`, and
`url()` just returns it unchanged. This is the standard adaptation
pattern for storage backends whose upload API hands back a full URL.
"""

import requests
import vercel_blob
from django.core.files.base import ContentFile
from django.core.files.storage import Storage
from django.utils.deconstruct import deconstructible


@deconstructible
class VercelBlobStorage(Storage):
    def _save(self, name, content):
        content.seek(0)
        data = content.read()
        result = vercel_blob.put(name, data, options={"addRandomSuffix": "true"})
        return result["url"]

    def _open(self, name, mode="rb"):
        response = requests.get(name, timeout=10)
        response.raise_for_status()
        return ContentFile(response.content)

    def exists(self, name):
        # `name` is already the full, Vercel-assigned URL for anything this
        # backend saved, and Blob's own addRandomSuffix already guarantees
        # uniqueness on write — so there's nothing local to collide-check.
        return False

    def size(self, name):
        try:
            return vercel_blob.head(name).get("size", 0)
        except Exception:
            return 0

    def url(self, name):
        return name

    def delete(self, name):
        try:
            vercel_blob.delete(name)
        except Exception:
            # Matches FileSystemStorage's delete(), which is also a no-op
            # if the file is already gone.
            pass
