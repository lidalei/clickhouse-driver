from ...streams.native import BlockOutputStream


class AsyncBlockOutputStream(BlockOutputStream):
    def finalize(self):
        return self.fout.drain()
