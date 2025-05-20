import re
from types import FunctionType
from typing import Dict, List, Tuple
import subprocess as sp
from log import setup_logger
from time import sleep
log = setup_logger(__name__)


def parse_data(
    text: str,
    protocol: str
) -> Dict[str, Dict[str, List[Tuple[str, List[str]]]]]:
    """
    Parse an indented hierarchy, filtering leaf nodes by `protocol` substring:
      Country (code)
        City    (code) @ coords…
          Server (ip1, ip2?) – …

    Only include servers whose code contains the given protocol (e.g. '-wg-' or '-ovpn-').
    Remove any cities or countries that end up with zero servers after filtering.

    Returns:
      { country_code: { city_code: [ (server_code, [ip1, ip2?]), … ] } }
    """
    top_re = re.compile(r'^([^\t(][^(\n]*)\s*\(([^)]+)\)')
    mid_re = re.compile(r'^\t([^\t(][^(\n]*)\s*\(([^)]+)\)')
    leaf_re = re.compile(
        r'^\t\t'                    # two tabs
        r'([^\t(][^(\n]*)\s*'       # server code
        r' \(\s*([^,()]+)'           # ip1
        r'(?:,\s*([^,()]+))?'       # optional ip2
        r'\s*\)'
    )

    raw: Dict[str, Dict[str, List[Tuple[str, List[str]]]]] = {}
    current_country = None
    current_city = None

    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            continue

        # Country level
        m = top_re.match(line)
        if m:
            _, country_code = m.groups()
            raw[country_code] = {}
            current_country = country_code
            current_city = None
            continue

        # City level
        m = mid_re.match(line)
        if m:
            _, city_code = m.groups()
            if current_country is None:
                raise ValueError("Found city before country")
            raw[current_country][city_code] = []
            current_city = city_code
            continue

        # Server leaf
        m = leaf_re.match(line)
        if m:
            server_code, ip1, ip2 = m.groups()
            if protocol not in server_code:
                continue
            if current_country is None or current_city is None:
                raise ValueError("Found server before country/city")
            ips = [ip1]
            if ip2:
                ips.append(ip2)
            raw[current_country][current_city].append((server_code, ips))
            continue

    # Prune empty cities and countries
    result: Dict[str, Dict[str, List[Tuple[str, List[str]]]]] = {}
    for country, cities in raw.items():
        filtered_cities: Dict[str, List[Tuple[str, List[str]]]] = {}
        for city, servers in cities.items():
            if servers:
                filtered_cities[city] = servers
        if filtered_cities:
            result[country] = filtered_cities

    return result

def parse_flat(text: str, protocol: str) -> List[str]:
    """
    Return a flat list of all leaf‐node codes, i.e. the server names
    that live on lines with exactly two leading tabs.
    """
    # ^\t\t → line must start with two tabs
    # ([^\t(]+) → capture server code (no tab or '(' in it)
    # \s*\(     → followed by optional space and a '('
    leaf_re = re.compile(r'^\t\t([^\t(]+)\s* \(', re.MULTILINE)
    all_codes = leaf_re.findall(text)
    return [code for code in all_codes if protocol in code]

def run_mullvad_command(cmd: str) -> str:
    #log.debug(f'--> {" ".join((['mullvad'] + cmd.split(' ')))}')
    m = sp.run(['mullvad'] + cmd.split(' '), stdout=sp.PIPE)
    stdout = m.stdout
    #log.debug(f'<-- {stdout}')
    return stdout.decode('UTF-8')

def validate_account() -> bool:
    std = run_mullvad_command('account get')
    if 'mullvad account' in std.lower():
        return True
    return False

def get_relays() -> dict:
    log.info("Getting list of relays")
    std = run_mullvad_command('relay list')
    log.debug("Parsing relays")
    parsed = parse_data(std, '-wg-')
    return parsed

def get_relays_flat() -> list:
    log.info("Getting list of relays")
    std = run_mullvad_command('relay list')
    log.debug("Parsing relays flat")
    parsed = parse_flat(std, '-wg-')
    return parsed

def run_for_all_nodes(func: FunctionType):
    nodes = get_relays()
    for country_code, cities in nodes.items():
        for city_code, servers in cities.items():
            for node, ips in servers:
                log.info(f"Setting mullvad to {node}")
                ret = run_mullvad_command(f'relay set location {country_code} {city_code} {node}')
                if ret.startswith('Error') or "Relay constraints updated" not in ret:
                    log.warning(f"Failed to set mullvad to {node}")
                    continue
                log.debug("Connecting mullvad")
                run_mullvad_command("connect")
                log.debug("Waiting for mullvad to connect")
                not_connected = False
                while True:
                    conn = run_mullvad_command('status')
                    if conn.startswith('Connecting'):
                        sleep(1)
                        continue
                    if conn.startswith('Disconnected'):
                        if not not_connected:
                            not_connected = True
                            sleep(1)
                        else:
                            log.error("Mullvad didn't start connecting after 5 seconds, Imma just stop trying.")
                            return
                    if conn.startswith('Connected'):
                        break
                log.debug("Running func")
                func()
                log.debug("Disconnecting mullvad")
                run_mullvad_command("disconnect")
                while True:
                    conn = run_mullvad_command('status')
                    if conn.startswith('Disconnected'):
                        break
                    if conn.startswith('Disconnecting'):
                        sleep(1)
                        continue

if __name__ == '__main__':
    if not validate_account():
        log.critical("Couldn't validate mullvad login")
        exit(1)

    def test():
        s = sp.run(['curl', 'ifconfig.me/ip'], stdout=sp.PIPE)
        print(s.stdout.decode('UTF-8'))
    run_for_all_nodes(test)