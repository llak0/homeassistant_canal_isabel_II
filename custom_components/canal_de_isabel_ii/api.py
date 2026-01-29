"""API Client for Canal de Isabel II."""
import logging
import requests
from bs4 import BeautifulSoup
import csv
from io import StringIO
from typing import Dict, List, Optional
from .const import BASE_URL, CONSUMPTION_URL

_LOGGER = logging.getLogger(__name__)

class AuthError(Exception):
    """Exception raised for authentication errors."""
    pass

class CanalIsabelIIAPI:
    """API Client for Canal de Isabel II."""

    def __init__(self, jsessionid: str) -> None:
        """Initialize the API client."""
        self._jsessionid = jsessionid
        self._session = requests.Session()
        self._session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
        })
        # Set the session cookie
        self._session.cookies.set('JSESSIONID', self._jsessionid, domain='oficinavirtual.canaldeisabelsegunda.es')

    def check_auth(self) -> bool:
        """Check if the session is valid by accessing the consumption page."""
        try:
            response = self._session.get(CONSUMPTION_URL, timeout=30, allow_redirects=False)
            # If 302 redirect to login, it means auth failed. 
            # If 200 and we are on the page, success.
            if response.status_code == 200 and "export-csv" in response.text:
                return True
            if response.status_code in (302, 401, 403):
                return False
            # Check for login form or similar in content if 200 OK but wrong page
            if "login" in response.url or "inicio" in response.url:
                return False
                
            _LOGGER.warning("Auth check failed. Status: %s. Content preview: %s", response.status_code, response.text[:200])
            return False
        except Exception as e:
            _LOGGER.error("Error checking auth: %s", e)
            return False

    def keep_alive(self) -> None:
        """Ping the server to keep the session alive."""
        try:
            _LOGGER.debug("Sending keep-alive ping...")
            self.check_auth()
        except Exception as e:
            _LOGGER.error("Error sending keep-alive ping: %s", e)

    def get_consumption_data(self) -> List[Dict]:
        """Fetch and parse consumption CSV data."""
        # 1. Get the consumption page to find the dynamic CSV link and form data
        try:
            response = self._session.get(CONSUMPTION_URL, timeout=30, allow_redirects=True)
            
            # Check for auth strings or redirects
            if response.status_code in (401, 403):
                 raise AuthError(f"Authentication failed: Status {response.status_code}")
            
            # If we were redirected to login page
            if "login" in response.url or "inicio" in response.url:
                raise AuthError("Authentication failed: Redirected to login page")

            if response.status_code != 200:
                _LOGGER.error("Failed to load consumption page, status: %s", response.status_code)
                return []

            soup = BeautifulSoup(response.text, 'html.parser')

            # 2. Switch to Hourly Resolution
            # Find the resolution selector
            resolution_select = soup.find("select", id="selectPeriodicidad")
            if resolution_select:
                select_name = resolution_select.get("name")
                form = resolution_select.find_parent("form")
                
                if select_name and form:
                    form_action = form.get("action")
                    
                    # Prepare data for POST
                    data = {}
                    for inp in form.find_all("input"):
                        name = inp.get("name")
                        value = inp.get("value", "")
                        if name:
                            data[name] = value
                    
                    # Handle contract selection if present (preserve selection)
                    contract_select = soup.find("select", id="contratosSelect")
                    if contract_select:
                        c_name = contract_select.get("name")
                        selected_opt = contract_select.find("option", selected=True)
                        c_val = selected_opt["value"] if selected_opt else contract_select.find("option")["value"]
                        data[c_name] = c_val

                    # Set Resolution to Horaria
                    data[select_name] = "Horaria"
                    
                    _LOGGER.debug("Switching to Hourly resolution...")
                    # Post to apply filter
                    post_response = self._session.post(form_action, data=data, timeout=30)
                    if post_response.status_code == 200:
                        # Update soup with the new page content
                        soup = BeautifulSoup(post_response.text, 'html.parser')
                    else:
                        _LOGGER.error("Failed to switch resolution, status: %s", post_response.status_code)

            # 3. Find CSV Link
            csv_link_tag = soup.find('a', href=lambda x: x and 'export-csv' in x)
            
            if not csv_link_tag:
                title = soup.title.string.strip() if soup.title else "No Title"
                _LOGGER.error("Could not find CSV download link on the consumption page. URL: %s, Title: %s.", response.url, title)
                return []
            
            csv_url = csv_link_tag['href']
            if not csv_url.startswith('http'):
                csv_url = BASE_URL + csv_url
                
            _LOGGER.debug(f"Found CSV URL: {csv_url}")
            
            # 4. Download the CSV
            csv_response = self._session.get(csv_url, timeout=60)
            csv_response.raise_for_status()
            
            # 5. Parse CSV
            content = csv_response.content.decode('utf-8')
            csv_file = StringIO(content)
            reader = csv.DictReader(csv_file)
            
            results = []
            for row in reader:
                results.append(row)
                
            return results
            
        except AuthError:
            raise
        except Exception as e:
            _LOGGER.error("Error fetching consumption data: %s", e)
            return []
