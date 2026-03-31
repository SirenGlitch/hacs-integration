"""Config flow for the Tewke integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from pytewke import CannotConnect, InvalidAuth, TewkeClient

from homeassistant.components import zeroconf
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY, CONF_HOST

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_API_KEY, default=""): str,
    }
)


class TewkeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a UI config flow for a Tewke device."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow."""
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None

    # ------------------------------------------------------------------
    # Manual entry
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step shown when the user opens the dialog."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            api_key: str = user_input.get(CONF_API_KEY, "")

            unique_id, title, err = await self._validate_and_get_info(host, api_key)
            if err:
                errors["base"] = err
            else:
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=title,
                    data={CONF_HOST: host, CONF_API_KEY: api_key},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    # ------------------------------------------------------------------
    # Zeroconf / mDNS discovery
    # ------------------------------------------------------------------

    async def async_step_zeroconf(
        self, discovery_info: zeroconf.ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a device discovered via zeroconf."""
        host = discovery_info.host
        name: str = discovery_info.name.removesuffix("._tewke._tcp.local.")

        await self.async_set_unique_id(discovery_info.properties.get("id", host))
        self._abort_if_unique_id_configured(updates={CONF_HOST: host})

        self._discovered_host = host
        self._discovered_name = name

        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm the zeroconf-discovered device and optionally collect an API key."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = self._discovered_host
            api_key: str = user_input.get(CONF_API_KEY, "")

            _, title, err = await self._validate_and_get_info(host, api_key)  # type: ignore[arg-type]
            if err:
                errors["base"] = err
            else:
                return self.async_create_entry(
                    title=title,
                    data={CONF_HOST: host, CONF_API_KEY: api_key},
                )

        schema = vol.Schema(
            {vol.Optional(CONF_API_KEY, default=""): str}
        )
        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"name": self._discovered_name or self._discovered_host or ""},
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _validate_and_get_info(
        self, host: str, api_key: str
    ) -> tuple[str, str, str | None]:
        """Try to connect, returning (unique_id, title, error_key | None)."""
        client = TewkeClient(host=host, api_key=api_key or None)
        try:
            await client.async_authenticate()
            devices = await client.async_get_devices()
            # Use the first device's ID as the config entry unique ID so that
            # the user can't add the same hub twice.
            unique_id: str = devices[0].device_id if devices else host
            title: str = devices[0].name if devices else host
            return unique_id, title, None
        except InvalidAuth:
            return "", "", "invalid_auth"
        except CannotConnect:
            return "", "", "cannot_connect"
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Unexpected error connecting to Tewke hub at %s", host)
            return "", "", "unknown"
