"""Config flow for the Tewke integration."""

from __future__ import annotations

from typing import Any

import pytewke
from pytewke.error import TewkeError
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers import selector
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DOMAIN, LOGGER

_CONTROL_TYPE_OPTIONS = [
    selector.SelectOptionDict(value="light", label="Light"),
    selector.SelectOptionDict(value="switch", label="Switch"),
    selector.SelectOptionDict(value="fan", label="Fan"),
]


class TewkeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for the Tewke integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None
        self._room_name: str | None = None
        self._scene_control_types: dict[str, str] | None = None
        self._tap: pytewke.Tap | None = None

    # ------------------------------------------------------------------
    # Zeroconf discovery
    # ------------------------------------------------------------------

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        LOGGER.debug("Zeroconf discovery: %s", discovery_info)

        self._discovered_host = discovery_info.host

        unique_id = discovery_info.properties.get("hardwareId")
        if not unique_id:
            LOGGER.error("Failed to get Unique ID from mDNS TXT records")
            return self.async_abort(reason="cannot_identify")
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._discovered_host})

        self._discovered_name = discovery_info.properties.get("name") or discovery_info.name.replace(
            "._tewke-coap._udp.local.", ""
        )
        self._room_name = discovery_info.properties.get("room") or None

        self.context["title_placeholders"] = {"name": self._discovered_name}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show discovered device info and ask the user to confirm."""
        if user_input is not None:
            return await self.async_step_confirm_control_types()

        room_suffix = f" ({self._room_name})" if self._room_name else ""

        return self.async_show_form(
            step_id="zeroconf_confirm",
            description_placeholders={
                "name": self._discovered_name,
                "room_suffix": room_suffix,
            },
        )

    # ------------------------------------------------------------------
    # Scene control type selection
    # ------------------------------------------------------------------

    async def async_step_confirm_control_types(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user assign a platform type (light/switch/fan) to each scene."""
        if self._tap is None:
            self._tap = pytewke.Tap(self._discovered_host)

        if not self._tap.resources:
            await self._tap.discover()

        scenes = await self._tap.get_scenes()
        LOGGER.debug("scenes: %s", scenes)

        if user_input is not None:
            # Map scene name keys back to scene IDs
            name_to_id = {scene.name: scene_id for scene_id, scene in scenes.items()}
            self._scene_control_types = {
                name_to_id[name]: control_type
                for name, control_type in user_input.items()
                if name in name_to_id
            }
            return await self.async_step_placeholder()

        if not scenes:
            return await self.async_step_placeholder()

        schema_dict: dict = {
            vol.Required(scene.name, default="light"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=_CONTROL_TYPE_OPTIONS,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            for scene in scenes.values()
        }

        return self.async_show_form(
            step_id="confirm_control_types",
            data_schema=vol.Schema(schema_dict),
        )

    # ------------------------------------------------------------------
    # Final placeholder / entry creation
    # ------------------------------------------------------------------

    async def async_step_placeholder(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Final confirmation step before creating the config entry."""
        if user_input is not None:
            config_data: dict[str, Any] = {
                CONF_HOST: self._discovered_host,
                CONF_NAME: self._discovered_name,
            }
            if self._scene_control_types is not None:
                config_data["scene_control_types"] = self._scene_control_types

            return self.async_create_entry(
                title=self._discovered_name or "Tewke Device",
                data=config_data,
            )

        return self.async_show_form(
            step_id="placeholder",
            description_placeholders={"name": self._discovered_name},
        )

    # ------------------------------------------------------------------
    # Manual setup
    # ------------------------------------------------------------------

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._discovered_host = user_input[CONF_HOST]
            self._discovered_name = user_input.get(CONF_NAME) or "Tewke Device"

            try:
                tap = pytewke.Tap(self._discovered_host)
                await tap.discover()
                self._tap = tap
            except TewkeError:
                return await self.async_step_coap_enable()

            return await self.async_step_confirm_control_types()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Optional(CONF_NAME, default="Tewke Device"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_coap_enable(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Shown when CoAP is not reachable; lets the user retry."""
        if user_input is not None:
            try:
                tap = pytewke.Tap(self._discovered_host)
                await tap.discover()
                self._tap = tap
                return await self.async_step_confirm_control_types()
            except TewkeError:
                return self.async_show_form(
                    step_id="coap_enable",
                    description_placeholders={
                        "name": self._discovered_name,
                        "host": self._discovered_host,
                    },
                    errors={"base": "coap_still_failed"},
                )

        return self.async_show_form(
            step_id="coap_enable",
            description_placeholders={
                "name": self._discovered_name,
                "host": self._discovered_host,
            },
        )

