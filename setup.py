#!/usr/bin/env python3

import setuptools

with open('README.md', 'r') as f:
	long_description = f.read()

setuptools.setup(
	name='upenwrt',
	version='0.1.1',
	author='Ivan Shapovalov',
	author_email='intelfx@intelfx.name',
	description='A tool that generates custom OpenWRT sysupgrade images',
	long_description=long_description,
	long_description_content_type='text/markdown',
	url='https://github.com/intelfx/upenwrt',
	packages=setuptools.find_packages(),
	classifiers=[
		"Programming Language :: Python :: 3 :: Only",
		"Programming Language :: Python :: 3.7",
		"License :: OSI Approved :: GNU Affero General Public License v3",
		"Development Status :: 3 - Alpha",
	],
	python_requires='>=3.7',
	install_requires=[
		'requests',
		'urllib3',
		'asyncio',
		'aiohttp',
		'aiofiles',
	],
	include_package_data=True,
)
