#!/hint/python3

import os
import os.path as p
import argparse

from . import util
from .server import UpenwrtContext, UpenwrtApp, upenwrt_serve


def parse_args(argv=None):
	parser = argparse.ArgumentParser()
	parser.add_argument('-l', '--listen', default='0.0.0.0')
	parser.add_argument('-p', '--port', type=int, default=8000)
	parser.add_argument('-d', '--basedir', default='')
	parser.add_argument('-b', '--baseurl', default='http://localhost:8000')
	parser.add_argument('--debug', action='store_true')
	args = parser.parse_args(args=argv)

	context = UpenwrtContext.from_args(
		basedir=p.join(os.getcwd(), args.basedir),
		baseurl=args.baseurl,
	)

	return args, context


def upenwrt():
	args, context = parse_args()
	return UpenwrtApp(context=context)


def main(argv=None):
	args, context = parse_args(argv=argv)
	util.configure_logging(
		prefix='upenwrt',
		debug=args.debug,
	)
	app = UpenwrtApp(context)
	upenwrt_serve(host=args.listen, port=args.port, app=app)
