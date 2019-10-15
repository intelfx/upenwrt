# upenwrt

`upenwrt` is a tool, in form of a (simple) HTTP server, that generates custom
[OpenWRT][1] sysupgrade images with all your user-installed packages baked in,
on the fly.

It is designed to aid end-user upgrade process (saving you the hassle of
reinstalling all your packages by hand), especially if the target device relies
on non-default packages for Internet connectivity.

[1]: https://openwrt.org

# usage

Assuming that the daemon is reachable at <http://upenwrt:8000>:

```
curl http://upenwrt:8000/get | sh > /tmp/sysupgrade.img
sysupgrade -v /tmp/sysupgrade.img
```

Files read by the script:

* `/etc/openwrt_release`
* `/tmp/sysinfo/board_name`
* `/usr/lib/opkg/status`

Command-line arguments and environment variables used by the script:

| Command-line argument                 | Environment variable        | Description                                                                     | Default                                                 |
|---------------------------------------|-----------------------------|---------------------------------------------------------------------------------|---------------------------------------------------------|
| `--debug`                             | `$DEBUG`                    | enable (more) verbose logging in the script itself                              | not set                                                 |
| `--dry-run`                           | `$DRY_RUN`                  | do not call the server, only generate the curl(1) command line                  | not set                                                 |
| `--hw-target`                         | `$TARGET_NAME`              | OpenWRT target name, e. g. `ramips/mt7621`                                      | overrides `$DISTRIB_TARGET` of `/etc/openwrt_release`   |
| `--hw-target`                         | `$TARGET_NAME`              | OpenWRT target name, e. g. `ramips/mt7621`                                      | overrides `$DISTRIB_TARGET` of `/etc/openwrt_release`   |
| `--hw-board`                          | `$BOARD_NAME`               | OpenWRT board name or profile name, e. g. `xiaomi,mir3g` or `mir3g`             | overrides `/tmp/sysinfo/board_name`                     |
| `--current-release`                   | `$RELEASE`                  | current (installed) OpenWRT release, e. g. `SNAPSHOT`                           | overrides `$DISTRIB_RELEASE` of `/etc/openwrt_release`  |
| `--current-revision`                  | `$REVISION`                 | current (installed) OpenWRT revision, e. g. `r10574-273b803623`                 | overrides `$DISTRIB_REVISION` of `/etc/openwrt_release` |
| `--packages`                          | `$PACKAGES`                 | list of packages to install into the image, space-separated                     | overrides `/usr/lib/opkg/status`                        |
| `--packages-add`, `--packages-remove` | `$PKGS_ADD`, `$PKGS_REMOVE` | lists of packages to add/ignore when installing into the image, space-separated | none (supplements `/usr/lib/opkg/status`)               |

# description

`upenwrt` is implemented as a (simple) HTTP server daemon that serves a help
page (`/`), a script (`/get`) and an API endpoint (`/api/get`).

The script must be executed on the target device (presumably in the infamous
`curl | sh` pattern) and will collect user-installed package lists and other
necessary metadata. The API endpoint is supposed to be called by the script
and will return the resulting image in the response body (which will be written
on stdout).

# daemon usage

The daemon keeps all of its data in its "root directory", henceforth `$rootdir`.

Inside its `$rootdir`, the daemon needs:
* a copy of its static file tree under `$rootdir/static`
  (included in upenwrt source tree as `root/static`)
* a copy of [OpenWRT git repository][2] under `$rootdir/repo/openwrt.git`
  (bring your own and fetch regularly, upenwrt will not update it)
* an empty cache directory `$rootdir/cache`
* an empty work directory `$rootdir/work`

It is advised to put the work directory (`$rootdir/work`) on tmpfs and the cache
directory (`$rootdir/cache`) on a persistent read-write medium with sufficient
storage capacity for a few imagebuilders.

In other words:

```
mkdir -p /var/lib/upenwrt
cp -r root/static -T /var/lib/upenwrt/static
mkdir -p /var/lib/upenwrt/repo; git clone --bare https://git.openwrt.org/openwrt/openwrt.git /var/lib/upenwrt/repo/openwrt.git
mkdir -p /var/lib/upenwrt/cache
mkdir -p /var/lib/upenwrt/work; mount tmpfs -t tmpfs /var/lib/upenwrt/work

python -m upenwrt --rootdir /var/lib/upenwrt --baseurl http://upenwrt:8000 --listen '0.0.0.0' --port 8000
```

[2]: https://git.openwrt.org/openwrt/openwrt.git

# trivia

The main problem is to separate truly user-installed packages from default
packages (which are marked "user" in the opkg database as well), because while
it is possible to pass all "user" packages to `make image`, the default package
set is much more prone to change between revisions than user packages.

The obvious idea would be to compare opkg databases between the squashfs and the
overlay. However, this will not work if the user already runs an image with some
of their packages baked in (or, by extension, if the tool is used twice or more
in a row). The only viable idea known to the author is to get a vanilla openwrt
image of a matching revision and use its package list as the base.

However, it is infeasible to download and keep vanilla images corresponding to
all possible source revisions (as they are, naturally, rotated daily). Instead,
the openwrt source tree is downloaded and cached. Upon each request, the source
tree is checked out at the revision matching the pre-existing firmware and
targetinfo files are generated by calling the buildsystem. "Vanilla" package
lists are then extracted from targetinfo files and subtracted from submitted
package lists.

# license

This project is distributed under the terms of the [GNU Affero General Public
License (AGPL), version 3][4].

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License, version 3
    as published by the Free Software Foundation.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

[4]: https://www.gnu.org/licenses/agpl-3.0.en.html
