"""Round-trip test of both Supabase buckets (upload -> read -> delete).

    python check_supabase.py

Uses SUPABASE_URL / SUPABASE_SECRET_KEY / SUPABASE_PUBLISHABLE_KEY from the environment
(falling back to the defaults in supabase_client.py). Needs only `requests`.
"""
import os
import sys
import uuid

import requests

import supabase_client as sc


def main():
    url = os.environ.get("SUPABASE_URL", sc.DEFAULT_URL)
    secret = os.environ.get("SUPABASE_SECRET_KEY", "")
    key = secret or os.environ.get("SUPABASE_PUBLISHABLE_KEY", sc.DEFAULT_PUBLISHABLE_KEY)
    public_bucket = os.environ.get("SUPABASE_PUBLIC_BUCKET", "photos")
    private_bucket = os.environ.get("SUPABASE_PRIVATE_BUCKET", "documents")
    client = sc.SupabaseClient(url, key)
    print(f"Project: {url}\nKey in use: {'SECRET key' if secret else 'publishable key'}\n")

    ok = True
    for bucket, is_public in ((public_bucket, True), (private_bucket, False)):
        name = f"healthcheck/{uuid.uuid4().hex}.txt"
        payload = b"homeserve healthcheck"
        try:
            client.upload(bucket, name, payload, "text/plain")
            print(f"[PASS] upload to '{bucket}'")
            if is_public:
                r = requests.get(client.public_url(bucket, name), timeout=30)
                assert r.status_code == 200 and r.content == payload, f"public URL returned HTTP {r.status_code}"
                print(f"[PASS] public URL readable ({bucket})")
            else:
                assert client.download(bucket, name) == payload, "downloaded bytes differ"
                print(f"[PASS] authenticated download ({bucket})")
                r = requests.get(client.public_url(bucket, name), timeout=30)
                if r.status_code == 200:
                    print(f"[FAIL] bucket '{bucket}' is PUBLIC - verification documents would be exposed. "
                          "Make it private.")
                    ok = False
                else:
                    print(f"[PASS] '{bucket}' is not publicly readable (HTTP {r.status_code})")
            client.delete(bucket, name)
            print(f"[PASS] delete from '{bucket}'")
        except (sc.SupabaseStorageError, AssertionError, requests.RequestException) as exc:
            ok = False
            print(f"[FAIL] bucket '{bucket}': {exc}")
    print("\nAll good." if ok else "\nProblems found - see FAIL lines above (did you run supabase_setup.sql?).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
