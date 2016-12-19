#!/usr/bin/env python
"""
Listens for logging output on the default TCP logging port (9020) and stores
it in a central log at the given location

Usage:
    dm_log_server.py [options] <log_file>

Arguments:
    <log_file>      The full path and name of the log that should be written.

Options:
    --host STR      The ip address to bind the server to. Default is the value
                    stored as LOGSERVER in the site config file
    --port STR      The port to listen to. Default is the default logging TCP
                    port.
"""
import pickle
import logging
import logging.handlers
import SocketServer
import struct
import select

from docopt import docopt

import datman.config

class LogRecordStreamHandler(SocketServer.StreamRequestHandler):
    def handle(self):
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack('>L', chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = self.unPickle(chunk)
            record = logging.makeLogRecord(obj)
            self.handleLogRecord(record)

    def unPickle(self, data):
        return pickle.loads(data)

    def handleLogRecord(self, record):
        name = record.name
        logger = logging.getLogger(name)
        logger.handle(record)

class LogRecordSocketReceiver(SocketServer.ThreadingTCPServer):
    allow_reuse_address = 1

    def __init__(self, host, port, handler=LogRecordStreamHandler):
        SocketServer.ThreadingTCPServer.__init__(self, (host, port), handler)
        self.abort = 0
        self.timeout = 1

    def serve_until_stopped(self):
        abort = 0
        while not abort:
            rd, wr, ex = select.select([self.socket.fileno()],
                                       [], [],
                                       self.timeout)
            if rd:
                self.handle_request()
            abort = self.abort

def main():
    arguments = docopt(__doc__)
    log_path = arguments['<log_file>']
    host = arguments['--host']
    port = arguments['--port']

    logging.basicConfig(format="[%(name)s] %(levelname)s: %(message)s",
            filename=log_path, filemode='a')

    if host is None:
        host = datman.config.config().get_key('LOGSERVER')

    if port is None:
        port = logging.handlers.DEFAULT_TCP_LOGGING_PORT

    # Start server
    tcpserver = LogRecordSocketReceiver(host, port)
    tcpserver.serve_until_stopped()

if __name__ == '__main__':
    main()
