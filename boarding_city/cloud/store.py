"""Vercel Blob as the web builder's only storage. Everything is written once and never overwritten, because public
blobs are CDN-cached: job state is a numbered series of snapshots, and counters are folders of small marker files
whose names carry the value (summing them is a listing, never a read-modify-write, so concurrent jobs can't race)."""
import json
import requests
from vercel.blob import sync as blob


def put(path, body, content_type="application/json"):
    data = body if isinstance(body, bytes) else (body if isinstance(body, str) else json.dumps(body, separators=(",", ":"))).encode()
    return blob.put_blob(path, data, access="public", content_type=content_type, allow_overwrite=True).url


def create(path, body=b"1", content_type="text/plain"):
    """Write only if path doesn't exist yet. -> True if this call created it (a lease or marker it now owns)."""
    try:
        blob.put_blob(path, body, access="public", content_type=content_type, allow_overwrite=False)
        return True
    except blob.BlobError as e:
        if "already exists" in str(e):
            return False
        raise


def delete(paths):
    for i in range(0, len(paths), 100):
        blob.delete_blob(paths[i:i + 100])


def get_json(path_or_url):
    url = path_or_url if path_or_url.startswith("https://") else url_of(path_or_url)
    if not url:
        return None
    r = requests.get(url, timeout=20)
    return r.json() if r.ok else None


def get_bytes(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.content


def listing(prefix):
    """[(pathname, url, uploaded_at)] for every blob under prefix."""
    return [(b.pathname, b.url, b.uploaded_at) for b in blob.query_blobs(prefix=prefix)]


def url_of(path):
    """The public URL of a blob, or None. Existence comes from a listing (fresh), not a HEAD on the CDN, which may
    remember a 404 for a path that is written later."""
    hit = [u for p, u, _ in listing(path) if p == path]
    return hit[0] if hit else None
