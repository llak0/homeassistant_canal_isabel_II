"""The Canal de Isabel II integration."""
import logging
import asyncio
from datetime import timedelta
from homeassistant.helpers.event import async_track_time_interval

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CanalIsabelIIAPI, AuthError
from .const import CONF_JSESSIONID, DOMAIN

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Canal de Isabel II from a config entry."""

    jsessionid = entry.data[CONF_JSESSIONID]
    api = CanalIsabelIIAPI(jsessionid)
    
    async def async_update_data():
        """Fetch data from API."""
        try:
            # Run blocking API call in executor
            data = await hass.async_add_executor_job(api.get_consumption_data)
            return data
        except AuthError as err:
            raise ConfigEntryAuthFailed(err) from err
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(hours=12),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "remove_keep_alive": None
    }

    async def run_keep_alive(now):
        """Keep the session alive and handle expiration."""
        success = await hass.async_add_executor_job(api.keep_alive)
        if not success:
            _LOGGER.warning("Session expired or keep-alive failed. Triggering re-authentication flow.")
            await coordinator.async_request_refresh()

    # Schedule keep-alive every 15 minutes
    remove_keep_alive = async_track_time_interval(
        hass, run_keep_alive, timedelta(minutes=15)
    )
    hass.data[DOMAIN][entry.entry_id]["remove_keep_alive"] = remove_keep_alive
    
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        if data["remove_keep_alive"]:
            data["remove_keep_alive"]()

    return unload_ok
