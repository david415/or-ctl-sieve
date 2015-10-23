#!/usr/bin/env python

# GPL goes here

from tubes.protocol import factoryFromFlow
from tubes.framing import bytesToLines, linesToBytes
from tubes.tube import tube, series
from tubes.routing import Router, Routed, to
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
            print "replacing %r with %r" % (line, self.replacements[line])
            yield self.replacements[line]
        else:
            print "not replacing %r" % (line,)
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

@tube
class filter_tube(object):
    def __init__(self, allowed, allowed_prefixes, connecting_drain):
        self.filter = or_command_filter(allowed, allowed_prefixes)
        self.connecting_drain = connecting_drain
        self.listening_drain = listening_drain

    def received(self, line):
        if self.filter.is_allowed():
            print "allowed: %r" % (line,)
            yield to(self.connecting_drain, line)
        else:
            print "filtered: %r" % (line,)

@tube
class ErrProxyRouter(object):
    outputType = Routed(str)

    def __init__(self, allowed, allowed_prefixes, listener_lines_fount, error_drain, connector_drain):
        self.filter = or_command_filter(allowed, allowed_prefixes)
        # create a router which takes input from listenerFount
        self._in = In()
        self._router = Router()
        listener_lines_fount.flowTo(self._in.newDrain())
        self._in.fount.flowTo(self._router.drain) # XXX is self._in needed?

        # route proxy errors back to client error drain
        self.err_route = self._router.newRoute()
        self.err_route.flowTo(error_drain)

        # second route to the proxy destination, connectorDrain
        self.server_route = self._router.newRoute()
        self.server_route.flowTo(connector_drain)

    def received(self, line):
        if self.filter.is_allowed():
            print "allowed: %r" % (line,)
            yield to(self.server_route, line)
        else:
            print "filtered: %r" % (line,)
            yield to(self.err_route, line)

class Hub(object):
    def __init__(self):
        self._out = Out()
        self._in = In()
        self._in.fount.flowTo(self._out.drain)
        self.error_drain = self._in.newDrain()
        self.proxy_drain = self._in.newDrain()

    def get_drain_fount(self):
        return self._out.newFount()

class proxyOrSieve(object):
    filtered_msg = "510 Tor Control command proxy denied: filtration policy."
    def __init__(self, proxyEndpoint, client_allowed, client_allowed_prefixes, server_allowed, server_allowed_prefixes, client_replacements):
        self.proxyEndpoint = proxyEndpoint
        self.client_allowed = client_allowed
        self.client_allowed_prefixes = client_allowed_prefixes
        self.client_replacements = client_replacements

    def new_proxy_flow(self, listening_fount, listening_drain):
        def outgoing_tube_factory(connecting_fount, connecting_drain):
            hub = Hub()
            listening_fount.flowTo(series(bytesToLines(),))
            hub_drain_fount = hub.get_drain_fount()
            connecting_fount.flowTo(series(bytesToLines(), hub.proxy_drain))
            
            error_tube = series(replace_with_error_tube(self.filtered_msg), hub.error_drain)
            connecting_tube = series(linesToBytes(), connecting_drain)
            router = ErrProxyRouter(self.client_allowed, self.client_allowed_prefixes, listening_fount.flowTo(series(bytesToLines())), error_tube, connecting_tube)

            hub_drain_fount.flowTo(series(linesToBytes(), listening_drain))

        self.proxyEndpoint.connect(factoryFromFlow(outgoing_tube_factory))
