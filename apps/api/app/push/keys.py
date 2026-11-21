"""Print a new VAPID key pair for Web Push (decision 0024).

    uv run python -m app.push.keys

prints three lines to paste into apps/api/.env. It never writes a file: the private key goes
only where you paste it. Changing the keys later invalidates every browser's subscription
(each one turns reminders on again).
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def new_keys() -> tuple[str, str]:
    """A P-256 key pair as (public, private): the public key as an uncompressed point (the
    browser's applicationServerKey) and the private key's 32 raw bytes, both base64url."""
    private = ec.generate_private_key(ec.SECP256R1())
    public = private.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    raw = private.private_numbers().private_value.to_bytes(32, "big")
    return _b64url(public), _b64url(raw)


def lines() -> list[str]:
    public, private = new_keys()
    return [
        f"VAPID_PUBLIC_KEY={public}",
        f"VAPID_PRIVATE_KEY={private}",
        "VAPID_SUBJECT=mailto:you@example.com",
    ]


def main() -> None:
    print("# Paste into apps/api/.env (and change the mailto: to your own address):")
    for line in lines():
        print(line)


if __name__ == "__main__":
    main()
