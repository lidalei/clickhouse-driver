from calendar import timegm
from datetime import datetime

from pytz import timezone, utc

from .base import FormatColumn


class DateTimeColumn(FormatColumn):
    ch_type = 'DateTime'
    py_types = (datetime, )
    format = 'I'

    def __init__(self, server_info=None, **kwargs):
        super(DateTimeColumn, self).__init__(server_info=server_info, **kwargs)
        # TODO: tests, detecting TZ from env?
        self.tz = timezone(server_info.timezone) if server_info else utc

    def after_read_item(self, value):
        return datetime.fromtimestamp(value, tz=self.tz).replace(tzinfo=None)

    def before_write_item(self, value):
        return int(timegm(value.timetuple()))
