#!/usr/bin/env python

# GPL goes here

from tubes.protocol import factoryFromFlow
from tubes.framing import bytesToLines, linesToBytes
from tubes.tube import tube, series


@tube
class replace_tube(object):
    def __init__(self, replacements):
        self.replacements = replacements

    def received(self, line):
        if line in self.replacements:
            print "replacing %r with %r" % (line, self.replacements[line])
            yield self.replacements[line]
        else:
            yield line

@tube
class filter_tube(object):
    def __init__(self, allowed, allowed_prefixes):
        if len(allowed) == 0 and len(allowed_prefixes) == 0:
            self.filter = False
        else:
            self.filter = True
        self.allowed = allowed
        self.allowed_prefixes = allowed_prefixes

    def received(self, line):
        if self.filter is False:
            print "filtering turned off"
            yield line
        allow = False
        if line in self.allowed:
            allow = True
        else:
            for prefix in self.allowed_prefixes:
                if line.startswith(prefix):
                    allow = True
                    break
        if allow:
            print "allowed: %r" % (line,)
            yield line


class proxyOrSieve(object):

    def __init__(self, proxyEndpoint, client_allowed, client_allowed_prefixes, server_allowed, server_allowed_prefixes, client_replacements):
        self.proxyEndpoint = proxyEndpoint
        self.client_allowed = client_allowed
        self.client_allowed_prefixes = client_allowed_prefixes
        self.server_allowed = server_allowed
        self.server_allowed_prefixes = server_allowed_prefixes
        self.client_replacements = client_replacements

    def tube_factory(self, listeningFount, listeningDrain):
        """cross-connects the client endpoint self.proxyEndpoint,
        with the listener's fount and drain.
        """
        def outgoingTubeFactory(connectingFount, connectingDrain):
            client_sieve = filter_tube(self.client_allowed, self.client_allowed_prefixes)
            client_replace = replace_tube(self.client_replacements)
            server_sieve = filter_tube(self.server_allowed, self.server_allowed_prefixes)
            proxy_client_sieve = series(bytesToLines(), client_replace, client_sieve, linesToBytes())
            proxy_server_sieve = series(bytesToLines(), server_sieve, linesToBytes())
            listeningFount.flowTo(proxy_client_sieve).flowTo(connectingDrain)
            connectingFount.flowTo(proxy_server_sieve).flowTo(listeningDrain)        
        self.proxyEndpoint.connect(factoryFromFlow(outgoingTubeFactory))
