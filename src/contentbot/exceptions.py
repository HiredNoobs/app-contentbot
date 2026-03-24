class ConfigurationError(Exception):
    pass


class AuthenticationError(Exception):
    pass


class RemovedFromChannelError(Exception):
    pass


class QueueError(Exception):
    pass


class InvalidBlackjackState(Exception):
    pass
