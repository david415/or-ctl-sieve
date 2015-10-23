#!/usr/bin/env python

# GPL goes here

from tubes.protocol import factoryFromFlow
from tubes.framing import bytesToLines, linesToBytes
from tubes.tube import tube, series, receiver
from tubes.fan import Out, In
from tubes.itube import IDrain
from tubes.kit import beginFlowingFrom

@tube
class replace_with_error_tube(object):
    def __init__(self, err_msg):
        self.err_msg = err_msg
    def received(self, line):
        yield self.err_msg

@tube
class replace_tube(object):
    def __init__(self, replacements):
        self.replacements = replacements

    def received(self, line):
        if line in self.replacements:
            yield self.replacements[line]
        else:
            yield line

class or_command_filter(object):
    def __init__(self, allowed, allowed_prefixes):
        self.allowed = allowed
        self.allowed_prefixes = allowed_prefixes

    def is_allowed(self, line):
        allow = False
        if line in self.allowed:
            allow = True
        else:
            for prefix in self.allowed_prefixes:
                if line.startswith(prefix):
                    allow = True
                    break
        return allow

def tubeFilter(pred):
    @receiver()
    def received(item):
        if pred(item):
            yield item
    return series(received)

def display_received(label):
    @receiver()
    def received(item):
        print "%r DISPLAY %r" % (label, item)
        yield item
    return series(received)

class proxyOrSieve(object):
    filtered_msg = "510 Tor Control command proxy denied: filtration policy."
    def __init__(self, proxyEndpoint, client_allowed, client_allowed_prefixes, server_allowed, server_allowed_prefixes, client_replacements):
        self.proxyEndpoint = proxyEndpoint
        self.client_allowed = client_allowed
        self.client_allowed_prefixes = client_allowed_prefixes
        self.server_allowed = server_allowed
        self.server_allowed_prefixes = server_allowed_prefixes
        self.client_replacements = client_replacements

    def new_proxy_flow(self, listening_fount, listening_drain):
        def outgoing_tube_factory(connecting_fount, connecting_drain):
            client_filter = or_command_filter(self.client_allowed, self.client_allowed_prefixes)
            client_sieve = tubeFilter(client_filter.is_allowed)
            client_replace = replace_tube(self.client_replacements)
            proxy_client_sieve = series(bytesToLines(), client_replace, client_sieve, linesToBytes())

            client_fanout = Out()
            client_err_fount = client_fanout.newFount()
            client_sieve_fount = client_fanout.newFount()
            client_sieve_fount.flowTo(proxy_client_sieve).flowTo(connecting_drain)

            server_fanin = In()
            server_fanin.fount.flowTo(display_received("server")).flowTo(listening_drain)
            #server_fanin.fount.flowTo(listening_drain)
            server_fanin_proxy_drain = server_fanin.newDrain()
            server_fanin_err_drain = server_fanin.newDrain()

            error_sieve = tubeFilter(lambda item: not client_filter.is_allowed(item))
            proxy_error_sieve = series(bytesToLines(), error_sieve, replace_with_error_tube(self.filtered_msg), linesToBytes())
            client_err_fount.flowTo(series(proxy_error_sieve, server_fanin_err_drain))

            server_filter = or_command_filter(self.server_allowed, self.server_allowed_prefixes)
            server_sieve = tubeFilter(server_filter.is_allowed)
            proxy_server_sieve = series(bytesToLines(), server_sieve, linesToBytes())

            connecting_fount.flowTo(proxy_server_sieve).flowTo(server_fanin_proxy_drain)
            listening_fount.flowTo(series(display_received("client"), client_fanout.drain))
            #listening_fount.flowTo(client_fanout.drain)

        self.proxyEndpoint.connect(factoryFromFlow(outgoing_tube_factory))
