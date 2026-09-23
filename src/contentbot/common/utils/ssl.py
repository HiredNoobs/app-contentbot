import ssl
from typing import Optional


def create_ssl_context(
    ca_cert_path: Optional[str] = None,
    cert_path: Optional[str] = None,
    key_path: Optional[str] = None,
) -> ssl.SSLContext:
    """
    Create and configure an SSL context.

    Without a CA certificate the system's default trust store is used, and without
    a client certificate and key no client authentication is performed.

    Args:
        ca_cert_path (Optional[str]): Path to the CA certificate file.
        cert_path (Optional[str]): Path to the client certificate file.
        key_path (Optional[str]): Path to the client private key file.

    Returns:
        ssl.SSLContext: A fully configured SSL context.
    """
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    if ca_cert_path:
        context.load_verify_locations(cafile=ca_cert_path)
    if cert_path and key_path:
        context.load_cert_chain(certfile=cert_path, keyfile=key_path)

    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED

    return context
