upenwrt(1)                          UPENWRT                           upenwrt(1)

NAME

    upenwrt - generate an OpenWRT sysupgrade image with all your packages

SYNOPSIS

    curl @BASE_URL@/get | sh -s RELEASE >/tmp/sysupgrade.img
    sysupgrade /tmp/sysupgrade.img

OPTIONS

    RELEASE
        OpenWRT release (e. g. "18.06.4") or the string "snapshot".

FILES

    /etc/openwrt_release
        Used to determine OpenWRT target name and current (installed) OpenWRT
        release and revision.

    /tmp/sysinfo/board_name
        Used to determine OpenWRT device name.

    /usr/lib/opkg/status
        Used to determine the list of packages to integrate into the image.

ENVIRONMENT

    TARGET_NAME
        OpenWRT target name (e. g. "ramips/mt7621").
        Overrides DISTRIB_TARGET= of /etc/openwrt_release.

    BOARD_NAME
        OpenWRT board or profile name (e. g. "xiaomi,mir3g" or "mir3g").
        Overrides contents of /tmp/sysinfo/board_name.

    RELEASE
        Current (installed) OpenWRT release, e. g. "snapshot".
        Overrides DISTRIB_RELEASE= of /etc/openwrt_release.

    REVISION
        Current (installed) OpenWRT revision, e. g. "r10574-273b803623".
        Overrides DISTRIB_REVISION= of /etc/openwrt_release.

    PACKAGES
        List of packages to integrate into the image (space-separated).
        Overrides contents of /usr/lib/opkg/status.

WWW

    https://github.com/intelfx/upenwrt

upenwrt 0.1.0                                                         upenwrt(1)
