#!/usr/bin/env python
"""
Listens for logging output on the default TCP logging port (9020) and stores
it in a central log at the given location

Usage:
    dm_log_server.py [options]

Options:
    --log-dir PATH  The directory to store all logs. Default is the value
                    stored as ServerLogDir in the site config file
    --host STR      The ip address to bind the server to. Default is the value
                    stored as LogServer in the site config file
    --port STR      The port to listen to. Default is the default logging TCP
                    port.
"""
import os
import pickle
import logging
import logging.handlers
import socketserver
import struct
import select
import datetime

from docopt import docopt

import datman.config

FORMAT = logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                           "%H:%M:%S")
LOG_DIR = None


class LogRecordStreamHandler(socketserver.StreamRequestHandler):
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
        logger = self.__set_handler(record)
        logger.handle(record)

    def __set_handler(self, record):
        log_name = self.__get_log_name(record)
        log_path = os.path.join(LOG_DIR, log_name)
        logger = logging.getLogger(log_name)
        if not logger.handlers:
            file_handler = logging.FileHandler(log_path)
            file_handler.setFormatter(FORMAT)
            logger.addHandler(file_handler)
        return logger

    def __get_log_name(self, record):
        name = record.name
        date = str(datetime.date.today())
        if name == '__main__':
            log_name = "{}-all.log".format(date)
        else:
            name = name.replace(".py", "")
            log_name = "{}-{}.log".format(date, name)
        return log_name


class LogRecordSocketReceiver(socketserver.ThreadingTCPServer):
    allow_reuse_address = 1

    def __init__(self, host, port, handler=LogRecordStreamHandler):
        socketserver.ThreadingTCPServer.__init__(self, (host, port), handler)
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
    global LOG_DIR
    arguments = docopt(__doc__)
    LOG_DIR = arguments['--log-dir']
    host = arguments['--host']
    port = arguments['--port']

    config = datman.config.config()

    if LOG_DIR is None:
        LOG_DIR = config.get_key('ServerLogDir')

    if host is None:
        host = config.get_key('LogServer')

    if port is None:
        port = logging.handlers.DEFAULT_TCP_LOGGING_PORT

    # Start server
    tcpserver = LogRecordSocketReceiver(host, port)
    tcpserver.serve_until_stopped()


if __name__ == '__main__':
    main()
