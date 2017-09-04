import asyncio
import logging
import socket
import weakref

import select

from ..block import Block
from .. import errors
from ..connection import Connection


logger = logging.getLogger(__name__)


class AsyncConnection(Connection):
    # Async helpers for waiting before next packet should be read.
    @staticmethod
    def _ready(self_weakref):
        self = self_weakref()
        if self is None:
            return

        self.waiter.set_result(None)

    async def ready_read(self):
        ready_to_read, _, _ = select.select([self._sock_fd], [], [], 0)
        # If there is it data in socket to read we read whole packet
        # without waiting.
        if ready_to_read:
            return

        self.waiter = self.loop.create_future()

        self.loop.add_reader(self._sock_fd, self._ready, weakref.ref(self))

        await asyncio.wait_for(self.waiter, None, loop=self.loop)

        self.loop.remove_reader(self._sock_fd)

    def __init__(self, *args, **kwargs):
        self.loop = kwargs.pop('loop', None) or asyncio.get_event_loop()
        super(AsyncConnection, self).__init__(*args, **kwargs)

    async def force_connect(self):
        if not self.connected:
            await self.connect()

        # Should ping be synchronous?
        elif not self.ping():
            logger.info('Connection was closed, reconnecting.')
            await self.connect()

    async def _create_files_from_socket(self):
        future = asyncio.open_connection(self.host, self.port)

        timeout = self.connect_timeout
        reader, writer = await asyncio.wait_for(future, timeout=timeout)

        self.socket = writer.get_extra_info('socket')
        self._sock_fd = self.socket.fileno()

        self.connected = True
        # TODO: timeouts
        # self.socket.settimeout(self.send_receive_timeout)

        # performance tweak
        self.socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

        # Disable buffering. Required for proper select() call.
        self.fin = self.socket.makefile('rb', buffering=0)
        self.fout = writer

    def get_block_out_stream(self):
        revision = self.server_info.revision

        if self.compression:
            from .streams.compressed import AsyncCompressedBlockOutputStream

            return AsyncCompressedBlockOutputStream(
                self.compressor_cls, self.compress_block_size,
                self.fout, revision
            )
        else:
            from .streams.native import AsyncBlockOutputStream

            return AsyncBlockOutputStream(self.fout, revision)

    async def connect(self):
        try:
            if self.connected:
                self.disconnect()

            logger.info(
                'Connecting. Database: %s. User: %s', self.database, self.user
            )

            await self._create_files_from_socket()

            await self.send_hello()
            await self.ready_read()
            self.receive_hello()

            self.block_in = self.get_block_in_stream()
            self.block_out = self.get_block_out_stream()

        except asyncio.TimeoutError as e:
            self.disconnect()
            raise errors.SocketTimeoutError(
                '{} ({})'.format(e.strerror, self.get_description())
            )

        except socket.error as e:
            self.disconnect()
            raise errors.NetworkError(
                '{} ({})'.format(e.strerror, self.get_description())
            )

    async def send_hello(self):
        self._send_hello()

        await self.fout.drain()

    async def send_data(self, block, table_name=''):
        self._send_data(block, table_name=table_name)

        await self.block_out.finalize()
        self.block_out.reset()

    async def send_query(self, query, query_id=None, settings=None):
        if not self.connected:
            await self.connect()

        self._send_query(query, query_id=query_id, settings=settings)

        await self.fout.drain()

    async def send_external_tables(self, tables):
        for table in tables or []:
            block = Block(table['structure'], table['data'])
            await self.send_data(block, table_name=table['name'])

        # Empty block, end of data transfer.
        await self.send_data(Block())
