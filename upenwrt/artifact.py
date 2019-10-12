#!/hint/python3

import os
import os.path as p
import tempfile

from . import util
from .targetinfo import OpenwrtTargetinfo


class OpenwrtArtifact:
	def openwrt_base_url(self):
		return f'https://downloads.openwrt.org/{self.release_path}/targets/{self.target_name}'

	def openwrt_imagebuilder_name(self):
		if self.version_id == 'snapshot':
			return f'openwrt-imagebuilder-{self.target_name.replace("/", "-")}.Linux-x86_64.tar.xz'
		else:
			return f'openwrt-imagebuilder-{self.version_id}-{self.target_name.replace("/", "-")}.Linux-x86_64.tar.xz'

	def __init__(self, *, context, target_name, version_id):
		self.context = context
		self.target_name = target_name

		if '/' in version_id:
			raise ValueError(f'OpenwrtArtifact: bad version id: {version_id}')
		elif version_id == 'snapshot':
			self.release_path = 'snapshots'
		else:
			self.release_path = f'releases/{version_id}'

		self.version_id = version_id

		self.base_url = self.openwrt_base_url()
		self.imagebuilder_file = None
		self.targetinfo = None

	def get_imagebuilder(self, target_dir):
		if not self.imagebuilder_file:
			imagebuilder_name = self.openwrt_imagebuilder_name()
			imagebuilder_url = f'{self.base_url}/{imagebuilder_name}'
			imagebuilder_file = p.join(self.context.cachedir, imagebuilder_name)
			util.get_file(imagebuilder_url, dest=imagebuilder_file)

			self.imagebuilder_file = imagebuilder_file

		target_path = tempfile.mkdtemp(dir=target_dir, prefix='imagebuilder')
		untar_imagebuilder = util.run(
			[ 'tar', '-xaf', self.imagebuilder_file ],
			cwd=target_path,
		)

		filelist = os.listdir(target_path)
		if len(filelist) != 1:
			raise RuntimeError(f'Got {len(filelist)} != 1 files after unpacking imagebuilder: {filelist}')

		return p.join(target_path, filelist[0])

	def get_targetinfo(self, imagebuilder_dir):
		if self.targetinfo is None:
			self.targetinfo = OpenwrtTargetinfo(p.join(imagebuilder_dir, '.targetinfo'))
		return self.targetinfo

