#!/hint/python3

import os
import os.path as p
import argparse

from .server import UpenwrtHTTPServer, UpenwrtContext, UpenwrtHTTPRequestHandler


def main():
	parser = argparse.ArgumentParser()
	parser.add_argument('-l', '--listen', default='')
	parser.add_argument('-p', '--port', type=int, default=8000)
	parser.add_argument('-d', '--basedir', default='')
	parser.add_argument('-b', '--baseurl', default='http://localhost:8000')
	args = parser.parse_args()

	httpd_address = (args.listen, args.port)
	httpd_context = UpenwrtContext(
		basedir=p.join(os.getcwd(), args.basedir),
		baseurl=args.baseurl,
	)

	httpd = UpenwrtHTTPServer(httpd_address, UpenwrtHTTPRequestHandler, context=httpd_context)
	httpd.serve_forever()
