
from ..client import Client
from .connection import AsyncConnection


class AsyncClient(Client):
    connection_cls = AsyncConnection

    def __init__(self, *args, **kwargs):
        self.waiter = None
        super(AsyncClient, self).__init__(*args, **kwargs)

    async def execute(
            self, query, params=None, with_column_types=False,
            external_tables=None, query_id=None, settings=None
    ):
        await self.connection.force_connect()

        try:
            is_insert = params is not None
            if is_insert:
                return await self.process_insert_query(
                    query, params, external_tables=external_tables,
                    query_id=query_id, settings=settings
                )
            else:
                return await self.process_ordinary_query(
                    query, with_column_types=with_column_types,
                    external_tables=external_tables,
                    query_id=query_id, settings=settings
                )

        except Exception:
            self.connection.disconnect()
            raise

    async def process_ordinary_query(
            self, query, with_column_types=False, external_tables=None,
            query_id=None, settings=None
    ):
        await self.connection.send_query(
            query,
            query_id=query_id, settings=settings
        )
        await self.connection.send_external_tables(external_tables)
        return await self.receive_result(with_column_types=with_column_types)

    async def receive_result(self, with_column_types=False):
        data, columns_with_types = [], []

        while True:
            await self.connection.ready_read()

            block = self.receive_block()
            if not block:
                break

            if block is True:
                continue

            # Header block contains no rows. Pick columns from it.
            if block.rows:
                data.extend(block.data)
            elif not columns_with_types:
                columns_with_types = block.columns_with_types

        if with_column_types:
            return data, columns_with_types
        else:
            return data
