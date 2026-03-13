import ssl


def create_ssl_context(ca_cert_path: str, cert_path: str, key_path: str) -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    context.load_verify_locations(cafile=ca_cert_path)
    context.load_cert_chain(certfile=cert_path, keyfile=key_path)

    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED

    return context
