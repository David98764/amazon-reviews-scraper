from dataclasses import dataclass
from typing import Dict

@dataclass
class DomainConfig:
    domain_map: Dict[str, str]
    default_code: str = "com"

    def get_domain(self, code: str) -> str:
        """
        Return TLD/domain component for a given code.
        Accepts inputs like 'com', 'co.uk', 'de' etc.
        """
        if not code:
            code = self.default_code
        code = code.lower().strip()
        # If provided directly as tld, pass through; else map using aliases
        if "." in code or code in {"com", "de", "fr", "it", "es", "nl", "co.uk", "com.au", "ca", "co.jp", "com.mx", "com.tr", "ae", "sg", "sa"}:
            return code
        return self.domain_map.get(code, self.default_code)