"""Google Translate Integration Module for YouTube Auto Dub.

This module provides robust translation capabilities by implementing a dual-strategy 
approach: the internal 'batchexecute' RPC API for high-quality results, and a 
mobile web scraping fallback for maximum reliability.

Acknowledgement: 
This implementation is inspired by and adapted from the logic found in the 
'deep-translator' library (nidhaloff/deep-translator). Optimized and 
refactored for the YouTube Auto Dub pipeline requirements.

Author: Nguyen Cong Thuan Huy (mangodxd)
Version: 1.0.0
"""

import json
import re
import httpx
from urllib.parse import quote
from bs4 import BeautifulSoup
from browserforge.headers import HeaderGenerator


class GoogleTranslator:
    """A unified Google Translator that attempts to use the internal 'batchexecute' API (RPC)
    first, and falls back to web scraping the mobile site if that fails.
    """
    
    def __init__(self, proxy=None):
        """Initialize Google Translator.
        
        Args:
            proxy: Optional proxy configuration.
        """
        self.base_url_rpc = "https://translate.google.com/_/TranslateWebserverUi/data/batchexecute"
        self.base_url_scrape = "https://translate.google.com/m"
        
        self.headers = HeaderGenerator().generate()
        
        self.proxy = proxy
        self.client = httpx.Client(proxy=self.proxy, timeout=10)
        
        self.bl = None

    def _refreshRpcToken(self):
        """Refreshes the 'cfb2h' token required for the RPC interface.
        
        Returns:
            None
        """
        try:
            response = self.client.get("https://translate.google.com/", headers=self.headers)
            bl_match = re.search(r'"cfb2h":"(.*?)"', response.text)
            if bl_match:
                self.bl = bl_match.group(1)
            else:
                self.bl = "boq_translate-webserver_20251215.06_p0"
        except Exception as e:
            print(f"[Warning] Token refresh failed: {e}. Using fallback.")
            self.bl = "boq_translate-webserver_20251215.06_p0"

    def _parseRpcResponse(self, raw_text):
        """Parses the nested JSON response from the RPC endpoint.
        
        Args:
            raw_text: Raw response text from RPC endpoint.
            
        Returns:
            Translated text string.
            
        Raises:
            ValueError: If parsing fails.
        """
        try:
            match = re.search(r'\["wrb.fr","MkEWBc","(.*?)",null,null,null,"generic"\]', raw_text, re.DOTALL)
            if not match:
                raise ValueError("Could not find translation data in RPC response.")

            inner_json_str = match.group(1).replace('\\"', '"').replace('\\\\', '\\')
            data = json.loads(inner_json_str)
            
            translation_parts = data[1][0][0][5]
            
            final_text = " ".join([part[0] for part in translation_parts if part[0]])
            return final_text
        except Exception as e:
            raise ValueError(f"RPC Parse Error: {e}")

    def _translateRpc(self, text, source, target):
        """Method 1: Internal API (batchexecute). Higher quality, mimics browser app.
        
        Args:
            text: Text to translate.
            source: Source language code.
            target: Target language code.
            
        Returns:
            Translated text string.
            
        Raises:
            Exception: If translation fails.
        """
        if not self.bl:
            self._refreshRpcToken()
        
        rpc_arg = json.dumps([[text, source, target, True, [1]]], ensure_ascii=False)
        f_req = json.dumps([["MkEWBc", rpc_arg, None, "generic"]])

        params = {
            "rpcids": "MkEWBc",
            "bl": self.bl,
            "hl": "en",
            "rt": "c"
        }
        
        response = self.client.post(
            self.base_url_rpc, 
            headers=self.headers, 
            params=params, 
            data={"f.req": f_req}
        )

        if response.status_code != 200:
            raise Exception(f"RPC HTTP Error: {response.status_code}")
        
        return self._parseRpcResponse(response.text)

    def _translateScrape(self, text, source, target):
        """Method 2: Web Scraping (Mobile Site). Simple fallback.
        
        Args:
            text: Text to translate.
            source: Source language code.
            target: Target language code.
            
        Returns:
            Translated text string.
            
        Raises:
            Exception: If translation fails.
        """
        params = {
            "sl": source,
            "tl": target,
            "q": text
        }
        
        response = self.client.get(self.base_url_scrape, params=params, headers=self.headers)
        
        if response.status_code == 429:
            raise Exception("Too Many Requests (429)")
        if response.status_code != 200:
            raise Exception(f"Scrape HTTP Error: {response.status_code}")

        soup = BeautifulSoup(response.text, "html.parser")
        
        element = soup.find("div", {"class": "t0"})
        if not element:
            element = soup.find("div", {"class": "result-container"})
        
        if not element:
            raise Exception("Could not find translation element in HTML.")
            
        return element.get_text(strip=True)

    def translate(self, text, source="auto", target="vi"):
        """Main interface. Tries RPC first, falls back to Scraping.
        
        Args:
            text: Text to translate.
            source: Source language code. Default 'auto'.
            target: Target language code. Default 'vi'.
            
        Returns:
            Translated text string or error message.
        """
        if not text:
            return ""
            
        try:
            return self._translateRpc(text, source, target)
        except Exception:
            pass

        try:
            return self._translateScrape(text, source, target)
        except Exception as e:
            return f"Error: All translation methods failed. Last error: {e}"

    def close(self):
        """Close the HTTP client.
        
        Returns:
            None
        """
        self.client.close()