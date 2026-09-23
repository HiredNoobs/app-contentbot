import ssl

from contentbot.common.utils.ssl import create_ssl_context


def test_create_ssl_context_without_certs():
    context = create_ssl_context(None, None, None)

    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname is True
