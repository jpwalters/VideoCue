"""
Network interface detection and management for NDI connections.

This module helps ensure VideoCue connects to cameras using the correct
network interface, avoiding issues with multiple NICs.
"""

import ipaddress
import logging
import socket

logger = logging.getLogger(__name__)


class NetworkInterface:
    """Represents a network interface with its details."""

    def __init__(self, name: str, ip: str, netmask: str, description: str = ""):
        self.name = name
        self.ip = ip
        self.netmask = netmask
        self.description = description or name

    @property
    def network(self) -> ipaddress.IPv4Network:
        """Get the network this interface belongs to."""
        return ipaddress.IPv4Network(f"{self.ip}/{self.netmask}", strict=False)

    def is_on_same_subnet(self, target_ip: str) -> bool:
        """Check if target IP is on the same subnet as this interface."""
        try:
            target = ipaddress.IPv4Address(target_ip)
            return target in self.network
        except (ValueError, ipaddress.AddressValueError):
            return False

    def __repr__(self):
        return f"NetworkInterface({self.name}, {self.ip}/{self.netmask})"


def get_network_interfaces() -> list[NetworkInterface]:
    """
    Get all network interfaces on this system.

    Returns:
        List of NetworkInterface objects, excluding loopback and down interfaces.
    """
    interfaces = []

    try:
        import psutil

        for iface_name, addrs in psutil.net_if_addrs().items():
            # Skip if interface is down
            stats = psutil.net_if_stats().get(iface_name)
            if stats and not stats.isup:
                continue

            for addr in addrs:
                # Only IPv4 addresses
                if addr.family == socket.AF_INET:
                    ip = addr.address
                    netmask = addr.netmask

                    # Skip loopback
                    if ip.startswith("127."):
                        continue

                    # Skip link-local (169.254.x.x)
                    if ip.startswith("169.254."):
                        continue

                    interfaces.append(
                        NetworkInterface(
                            name=iface_name, ip=ip, netmask=netmask, description=iface_name
                        )
                    )

    except ImportError:
        logger.warning("psutil not available, using fallback method")
        # Fallback: get hostname IPs
        try:
            hostname = socket.gethostname()
            for ip in socket.gethostbyname_ex(hostname)[2]:
                if not ip.startswith("127."):
                    # Default to /24 netmask as fallback
                    interfaces.append(
                        NetworkInterface(
                            name="default", ip=ip, netmask="255.255.255.0", description=ip
                        )
                    )
        except OSError:
            pass

    return interfaces


def find_interface_for_camera(camera_ip: str) -> NetworkInterface | None:
    """
    Find the best network interface to use for connecting to a camera.

    Args:
        camera_ip: IP address of the camera

    Returns:
        NetworkInterface on the same subnet as camera, or None if no match
    """
    interfaces = get_network_interfaces()

    # Find interface on same subnet
    matching_interfaces = [iface for iface in interfaces if iface.is_on_same_subnet(camera_ip)]

    if len(matching_interfaces) == 1:
        logger.info(
            f"Camera {camera_ip} matched to interface {matching_interfaces[0].ip} (subnet: {matching_interfaces[0].network})"
        )
        return matching_interfaces[0]
    if len(matching_interfaces) > 1:
        # Multiple matches - prefer interface with smallest network (most specific)
        best = min(matching_interfaces, key=lambda x: x.network.num_addresses)
        logger.warning(
            f"Camera {camera_ip} matched multiple interfaces, using {best.ip} (smallest subnet)"
        )
        return best
    logger.warning(f"Camera {camera_ip} not on same subnet as any interface")
    return None


def get_preferred_interface_ip(camera_ips: list[str]) -> str | None:
    """
    Get the preferred local interface IP for a list of camera IPs.

    Args:
        camera_ips: List of camera IP addresses

    Returns:
        Local interface IP that matches most cameras, or None
    """
    if not camera_ips:
        return None

    # Count which interface appears most often
    interface_counts = {}
    for camera_ip in camera_ips:
        iface = find_interface_for_camera(camera_ip)
        if iface:
            interface_counts[iface.ip] = interface_counts.get(iface.ip, 0) + 1

    if not interface_counts:
        return None

    # Return the interface that matches the most cameras
    preferred_ip = max(interface_counts, key=interface_counts.get)
    logger.info(
        f"Preferred interface: {preferred_ip} (matches {interface_counts[preferred_ip]} cameras)"
    )
    return preferred_ip
