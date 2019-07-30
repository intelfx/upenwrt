#!/bin/sh

set -e

log() {
	echo ":: $*" >&2
}

warn() {
	echo "W: $*" >&2
}

err() {
	echo "E: $*" >&2
}

die() {
	err "$@"
	exit 1
}

function log_choice() {
	local name="$1"
	local value="$(eval "echo \"\${${name}}\"")"
	local reason="$(eval "echo \"\${${name}_reason}\"")"
	log "\$$name='$value' ($reason)"
}

AWK_FILTER_PACKAGES='
function pkg_new(pkg)
{
	package = pkg
	p_user = 0
}

function pkg_check()
{
	if (p_user) {
		print package
	}
}

BEGIN { FS = ": " }
/^Package: / { pkg_new($2) }
/^Status: .*\<user\>.*/ { p_user = 1; pkg_check() }
'

opkg_get_user_all() {
	awk "$AWK_FILTER_PACKAGES" "$OPKG_STATUS" | sort
}

opkg_get_user_ovl() {
	PKGS_IN_ROM="$(mktemp)"
	PKGS_IN_OVL="$(mktemp)"
	awk "$AWK_FILTER_PACKAGES" "$OPKG_STATUS_ROM" | sort > "$PKGS_IN_ROM"
	awk "$AWK_FILTER_PACKAGES" "$OPKG_STATUS_OVL" | sort > "$PKGS_IN_OVL"
	# comm -13
	cat "$PKGS_IN_ROM" "$PKGS_IN_ROM" "$PKGS_IN_OVL" | sort | uniq -u
	rm -f "$PKGS_IN_ROM" "$PKGS_IN_OVL"
}

opkg_get_user() {
	#if [ -r "$OPKG_STATUS_ROM" -a -r "$OPKG_STATUS" ]; then
	#	opkg_get_user_ovl
	#else
	#	opkg_get_user_all
	#fi
	opkg_get_user_all \
		| grep -v '^lib' \
		| tr -s ' \n' ' '
}

# determine board path
if test -n "$TARGET_NAME"; then
	TARGET_NAME_reason=override
elif test -f /etc/openwrt_release; then
	. /etc/openwrt_release
	test -n "$DISTRIB_TARGET" || die "\$DISTRIB_TARGET not present in /etc/openwrt_release, exiting"
	TARGET_NAME="$DISTRIB_TARGET"
	TARGET_NAME_reason="/etc/openwrt_release \$DISTRIB_TARGET"
else
	die "/etc/openwrt_release does not exist or is not a regular file, exiting"
fi
log_choice TARGET_NAME

# determine board name
if test -n "$BOARD_NAME"; then
	BOARD_NAME_reason="override"
elif test -f /tmp/sysinfo/board_name; then
	BOARD_NAME="$(cat /tmp/sysinfo/board_name)"
	BOARD_NAME_reason="/tmp/sysinfo/board_name"
else
	die "/tmp/sysinfo/board_name does not exist or is not a regular file, exiting"
fi
log_choice BOARD_NAME

# determine current release & revision
if test -n "$RELEASE"; then
	RELEASE_reason="override"
elif test -n /etc/openwrt_release; then
	. /etc/openwrt_release
	test -n "$DISTRIB_RELEASE" || die "\$DISTRIB_RELEASE not present in /etc/openwrt_release, exiting"
	RELEASE="$DISTRIB_RELEASE"
	RELEASE_reason="/etc/openwrt_release \$DISTRIB_RELEASE"
else
	die "/etc/openwrt_release does not exist or is not a regular file, exiting"
fi
log_choice RELEASE

if test -n "$REVISION"; then
	REVISION_reason="override"
elif test -n /etc/openwrt_release; then
	. /etc/openwrt_release
	test -n "$DISTRIB_REVISION" || die "\$DISTRIB_REVISION not present in /etc/openwrt_release, exiting"
	REVISION="$DISTRIB_REVISION"
	REVISION_reason="/etc/openwrt_release \$DISTRIB_REVISION"
else
	die "/etc/openwrt_release does not exist or is not a regular file, exiting"
fi
log_choice REVISION

# determine user-installed packages
if test -n "$PACKAGES"; then
	PACKAGES_reason="override"
else
	if test -n "$OPKG_STATUS"; then
		OPKG_STATUS_reason="override"
	else
		OPKG_STATUS="/usr/lib/opkg/status"
		OPKG_STATUS_ROM="/rom$OPKG_STATUS"
		OPKG_STATUS_OVL="$OPKG_STATUS"
		OPKG_STATUS_reason="default"
	fi
	log_choice OPKG_STATUS

	PACKAGES="$(opkg_get_user)"
	PACKAGES_reason="$OPKG_STATUS"
fi
log_choice PACKAGES

# determine base URL
BASE_URL="@BASE_URL@"
BASE_URL_reason='hardcode'
log_choice BASE_URL

# determine target release
if test -n "$1"; then
	TARGET="$1"
	TARGET_reason="\$1"
else
	TARGET="snapshot"
	TARGET_reason='hardcode'
fi
log_choice TARGET

# generate CURL call
URL="$BASE_URL/api/get"
CURL="curl '$URL'"
CURL="$CURL -G"
CURL="$CURL -d 'target_name=$TARGET_NAME'"
CURL="$CURL -d 'board_name=$BOARD_NAME'"
CURL="$CURL -d 'current_release=$RELEASE'"
CURL="$CURL -d 'current_revision=$REVISION'"
CURL="$CURL -d 'target_version=$TARGET'"
CURL="$CURL @API_ARGS@"
for p in $PACKAGES; do
	CURL="$CURL -d 'pkgs=$p'"
done
log "\$CURL='$CURL'"

# invoke curl protecting against server errors
TMP_BODY="$(mktemp)"
TMP_STATUS="$(mktemp)"
cleanup() { rm -f "$TMP_BODY" "$TMP_STATUS"; }
trap cleanup EXIT

eval "$CURL -sSL -w '%{http_code}' -o '$TMP_BODY' >'$TMP_STATUS'"
STATUS="$(cat "$TMP_STATUS")"
if [ -n "$STATUS" -a "$STATUS" -ge 200 -a "$STATUS" -lt 400 ]; then
	cat "$TMP_BODY"
	rc=0
else
	cat "$TMP_BODY" >&2
	rc=1
fi

exit $rc
