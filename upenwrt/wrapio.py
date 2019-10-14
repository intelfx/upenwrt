#!/hint/python3

import os
import sys
import asyncio
import aiofiles
import aiofiles.os
import tempfile
import shutil


os_makedirs = aiofiles.os.wrap(os.makedirs)
os_listdir = aiofiles.os.wrap(os.listdir)
tempfile_mkdtemp = aiofiles.os.wrap(tempfile.mkdtemp)
tempfile_mktemp = aiofiles.os.wrap(tempfile.mktemp)
shutil_rmtree = aiofiles.os.wrap(shutil.rmtree)
