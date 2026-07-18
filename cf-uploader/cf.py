""" Cloudflare interface - rewritten for CF API v4 using requests """
import logging
import requests
import errors

logger = logging.getLogger(__name__)

CF_API = "https://api.cloudflare.com/client/v4"

def isipv6(ip):
    return ip.count(":") > 1

def _lookup_zone_id(headers, domain):
    r = requests.get(f"{CF_API}/zones", params={"name": domain}, headers=headers)
    data = r.json()
    if not data.get("success"):
        raise errors.ZoneNotFound("CF API error: {}".format(data.get("errors")))
    zones = data["result"]
    if not zones:
        raise errors.ZoneNotFound("Could not find zone named: {}".format(domain))
    if len(zones) > 1:
        raise errors.TooManyZones("More than one zone found named: {}".format(domain))
    return zones[0]["id"]

class CloudflareSeeder(object):

    @staticmethod
    def from_configuration(configuration):
        user = configuration["cf_username"].replace('"', "")
        key = configuration["cf_api_key"].replace('"', "")
        domain = configuration["cf_domain"].replace('"', "")
        name = configuration["cf_domain_prefix"].replace('"', "")
        return CloudflareSeeder(user, key, domain, name)

    def __init__(self, user, key, domain, name):
        self.headers = {
            "Authorization": "Bearer " + key,
            "Content-Type": "application/json",
        }
        self.domain = domain
        self.name = name
        self._zone_id = None

    @property
    def zone_id(self):
        if self._zone_id is None:
            self._zone_id = _lookup_zone_id(self.headers, self.domain)
        return self._zone_id

    def get_seed_records(self, flags=False):
        name_parts = [self.name, self.domain]
        if flags:
            name_parts.insert(0, "x9")
        full_name = ".".join(name_parts)
        records = []
        page = 1
        while True:
            r = requests.get(
                f"{CF_API}/zones/{self.zone_id}/dns_records",
                params={"name": full_name, "per_page": 100, "page": page},
                headers=self.headers,
            )
            data = r.json()
            if not data.get("success"):
                logger.error("Error fetching DNS records: {}".format(data.get("errors")))
                break
            records.extend(data["result"])
            info = data.get("result_info", {})
            if page >= info.get("total_pages", 1):
                break
            page += 1
        return records

    def get_seeds(self):
        return [rec["content"] for rec in self.get_seed_records()]

    def _set_seed(self, seed, ttl=None, flags=False):
        name = ("x9." if flags else "") + self.name
        record = {
            "name": name,
            "type": "AAAA" if isipv6(seed) else "A",
            "content": seed,
            "ttl": ttl if ttl else 120,
            "proxied": False,
        }
        r = requests.post(
            f"{CF_API}/zones/{self.zone_id}/dns_records",
            json=record,
            headers=self.headers,
        )
        data = r.json()
        if not data.get("success"):
            logger.error("Error setting seed {}: {}".format(seed, data.get("errors")))

    def set_seed(self, seed, ttl=None):
        self._set_seed(seed, ttl=ttl)
        self._set_seed(seed, ttl=ttl, flags=True)

    def delete_seeds(self, seeds):
        for rec in self.get_seed_records() + self.get_seed_records(flags=True):
            if rec["content"] in seeds:
                requests.delete(
                    f"{CF_API}/zones/{self.zone_id}/dns_records/{rec['id']}",
                    headers=self.headers,
                )

    def set_seeds(self, seeds, ttl=None):
        for seed in seeds:
            self.set_seed(seed, ttl)
