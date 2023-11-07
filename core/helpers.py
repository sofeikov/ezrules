from collections import namedtuple

LockRecord = namedtuple("LockRecord", ["rid", "locked_by", "expires_on"])
