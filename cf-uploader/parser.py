import logging
import time
import errors

logger = logging.getLogger(__name__)


def _parse_ipv4(ip):

    """ Parse an ipv4 address and port number. """

    addr, port = ip.split(':')
    return addr, port


def _parse_ipv6(ip):

    """ Parse an ipv6 address and port number. """

    addr, port = ip.split(']:')
    return addr.replace("[", ""), port


def isipv6(ip):

    """ Extremely naive IPV6 check. """

    return '[' in ip and ']' in ip


def parse_ip(ip):

    """ Return an ip address and port number from the string """

    if isipv6(ip):
        return _parse_ipv6(ip)
    else:
        return _parse_ipv4(ip)


def read_hard_seeds(hard_seeds_file):

    """ Read the hard seed list from the file. Should just be new line separated list of IP Addresses. """

    logger.debug("Reading hard seeds file: {}".format(hard_seeds_file))

    hard_seeds = []
    with open(hard_seeds_file) as seed_lines:
        for line in seed_lines:
            stripped_line = line.strip()
            if stripped_line:
                if ':' in stripped_line:
                    hard_seed = stripped_line.split(':')[0]
                else:
                    hard_seed = stripped_line

                hard_seeds.append(hard_seed)

    logger.info("Found {} hard seeds.".format(len(hard_seeds)))

    if not hard_seeds:
        raise errors.SeedsNotFound("No seeds read from the hard seeds list: {}".format(hard_seeds_file))

    return hard_seeds


def read_seed_dump(seeds_file, valid_port, required_subversion=None, max_blocks_behind=None, min_proto_version=None, max_seed_age=None, require_node_network=False):

    """Read good IP addresses from the seed dump, optionally filtered by client subversion and height."""

    logger.debug("Reading seeds dump file: {}".format(seeds_file))
    if required_subversion:
        required_subversion = required_subversion.strip().strip('"')
        logger.info("Filtering seed dump by subversion: {}".format(required_subversion))
    if max_blocks_behind not in (None, ""):
        max_blocks_behind = int(max_blocks_behind)
        logger.info("Filtering seed dump by max blocks behind: {}".format(max_blocks_behind))
    else:
        max_blocks_behind = None

    if min_proto_version not in (None, ""):
        min_proto_version = int(min_proto_version)
        logger.info("Filtering seed dump by min protocol version: {}".format(min_proto_version))
    else:
        min_proto_version = None

    now_ts = int(time.time())
    if max_seed_age not in (None, ""):
        max_seed_age = int(max_seed_age)
        logger.info("Filtering seed dump by max seed age (s): {}".format(max_seed_age))
    else:
        max_seed_age = None
    if isinstance(require_node_network, str):
        require_node_network = require_node_network.strip() in ("1", "true", "True", "yes")
    if require_node_network:
        logger.info("Filtering seed dump to NODE_NETWORK peers only")

    candidates = []
    with open(seeds_file) as seeds:

        for line in seeds:
            if line.startswith('#'):
                continue

            if required_subversion and required_subversion not in line:
                continue

            components = line.split()
            if len(components) < 9:
                continue

            try:
                ip_addr, port = parse_ip(components[0])
                block_height = int(components[8])
                proto_version = int(components[10]) if len(components) > 10 else None
                last_success = int(components[2])
                svcs = int(components[9], 16) if len(components) > 9 else 0
                logger.debug("Parsed ip: {}".format(ip_addr))
            except (ValueError, IndexError):
                logger.error("Could not parse seed row from {} - skipping.".format(components[0] if components else line.strip()))
                continue

            if min_proto_version is not None and (proto_version is None or proto_version < min_proto_version):
                continue

            if max_seed_age is not None and (now_ts - last_success) > max_seed_age:
                continue

            if require_node_network and not (svcs & 0x1):
                continue

            if port == valid_port and components[1] == "1":
                candidates.append((ip_addr, block_height))
                logger.debug("Read a good seed: IP {} PORT {} HEIGHT {}".format(ip_addr, port, block_height))

    if max_blocks_behind is not None and candidates:
        max_height = max(height for _, height in candidates)
        min_height = max_height - max_blocks_behind
        logger.info("Filtering seed dump by height: max={}, min={}".format(max_height, min_height))
        candidates = [(ip, height) for ip, height in candidates if height >= min_height]

    addresses = [ip for ip, _ in candidates]
    suffix = " matching {}".format(required_subversion) if required_subversion else ""
    logger.info("Found {} good ip addresses from dump file{}.".format(len(addresses), suffix))

    if not addresses:
        raise errors.SeedsNotFound("No good seeds read from seeds dump file: {}".format(seeds_file))

    return addresses
