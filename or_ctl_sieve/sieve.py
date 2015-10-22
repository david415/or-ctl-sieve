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
        """cross-connects the client endpoint self.proxyEndpoint,
        with the listener's fount and drain.
        """
        print "new_proxy_flow listening_fount %r listening_drain %r" % (listening_fount, listening_drain)
        def outgoing_tube_factory(connecting_fount, connecting_drain):
            # drain hub takes proxy error messages from us or legit messages from the server
            fan_in = In()
            hub_error_drain = fan_in.newDrain()
            hub_server_drain = fan_in.newDrain()

            # drain hub inputs
            # XXX todo: apply sieve
            connecting_fount.flowTo(hub_server_drain)

            # drain hub input from proxy error generator
            in_err = In()
            err_drain = in_err.newDrain()

            start_fount = listening_fount.flowTo(bytesToLines())
            
            # create a router that flows into proxy_err_tube AND connecting_drain
            router = ErrProxyRouter(self.client_allowed, self.client_allowed_prefixes, start_fount, err_drain, connecting_drain)

            print "err drain FOUNT %r" % (err_drain.fount,)
            err_drain.fount.flowTo(series(replace_with_error_tube(self.filtered_msg)), hub_error_drain)

            
            # drain hub output
            fan_in.fount.flowTo(series(linesToBytes(), listening_drain))
            
        self.proxyEndpoint.connect(factoryFromFlow(outgoing_tube_factory)) # fin.
