import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, CONF_BASE_URL, CONF_API_KEY, CONF_METRIC_ENTITIES

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].rstrip("/")
            try:
                session = async_get_clientsession(self.hass)
                async with session.get(f"{base_url}/health", timeout=8) as response:
                    if response.status != 200:
                        errors["base"] = "cannot_connect"
                    else:
                        await self.async_set_unique_id(base_url)
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(title="Szymon Training Hub", data={**user_input, CONF_BASE_URL: base_url})
            except Exception:
                errors["base"] = "cannot_connect"
        schema = vol.Schema({vol.Required(CONF_BASE_URL, default="http://homeassistant.local:8000"): str, vol.Required(CONF_API_KEY): str, vol.Optional(CONF_METRIC_ENTITIES, default="sensor.garmin_connect_waga;weight;kg\nsensor.szymon_czas_snu;sleep_duration;h"): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
