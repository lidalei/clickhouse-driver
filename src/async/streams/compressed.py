from ...streams.compressed import CompressedBlockOutputStream


class AsyncCompressedBlockOutputStream(CompressedBlockOutputStream):
    def finalize(self):
        self._finalize()

        return self.raw_fout.drain()
