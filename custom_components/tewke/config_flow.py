"""Config flow for the Tewke integration."""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import aiocoap
import cbor2
import pytewke
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DOMAIN, LOGGER


class TewkeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for the Tewke integration."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialise the config flow."""
        self._discovered_host: str | None = None
        self._discovered_name: str | None = None
        self._scene_control_types: dict[str, str] | None = None
        self._tap: pytewke.Tap | None = None

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle zeroconf discovery."""
        LOGGER.debug("Zeroconf discovery: %s", discovery_info)

        self._discovered_host = discovery_info.host
        fetched_config_data = await self._get_device_config_details()

        unique_id = discovery_info.properties.get("hardwareId")
        if not unique_id:
            LOGGER.info(
                "Failed to get Unique ID from mDNS TXT records. Trying from device configuration (CoAP)"
            )
            unique_id = fetched_config_data.get("hardwareId") if fetched_config_data else None
        if unique_id is None:
            LOGGER.error("Failed to get Unique ID from mDNS or CoAP")
            return self.async_abort(reason="cannot_identify")
        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured(updates={CONF_HOST: self._discovered_host})

        device_name = discovery_info.properties.get("name")
        if not device_name:
            LOGGER.info(
                "Failed to get device name from mDNS TXT records. Trying from device configuration (CoAP)"
            )
            device_name = fetched_config_data.get("deviceName") if fetched_config_data else None
        if not device_name:
            LOGGER.warning("Failed to get device name, using Serial Number instead")
            device_name = discovery_info.name.replace("._tewke._tcp.local.", "")
        room_name = discovery_info.properties.get("room")
        if not room_name:
            room_name = (
                (fetched_config_data.get("roomName") + ": ")
                if fetched_config_data and fetched_config_data.get("roomName")
                else ""
            )
        self._discovered_name = room_name + device_name

        self.context["title_placeholders"] = {"name": self._discovered_name}

        return self.async_show_form(
            step_id="confirm_control_types",
            description_placeholders={
                "name": self._discovered_name,
                "host": self._discovered_host,
            },
        )

    async def async_step_confirm_control_types(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user which HA platform type to assign to each scene."""
        tap = self._tap if self._tap is not None else pytewke.Tap(self._discovered_host)
        self._tap = tap

        await tap.discover()
        scenes = await tap.get_scenes()
        LOGGER.debug("scenes: %s", scenes)

        if user_input is not None:
            scene_control_types: dict[str, str] = {}
            for scene_id in scenes:
                control_type_key = f"scene_{scene_id}_control_type"
                if control_type_key in user_input:
                    scene_control_types[scene_id] = user_input[control_type_key]

            self._scene_control_types = scene_control_types
            return await self.async_step_placeholder()

        schema_dict: dict = {}
        for scene_id in scenes:
            scene_name = scenes[scene_id].name
            LOGGER.debug("scene_id: %s, scene_name: %s", scene_id, scene_name)
            schema_dict[vol.Required(f"scene_{scene_id}_control_type")] = vol.In(
                ["switch", "light", "fan"]
            )

        if not schema_dict:
            return await self.async_step_placeholder()

        return self.async_show_form(
            step_id="confirm_control_types",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "name": self._discovered_name,
                "host": self._discovered_host,
                "scenes": ", ".join(s.name for s in scenes.values()),
            },
        )

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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle manual setup initiated by the user."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._discovered_host = user_input[CONF_HOST]
            self._discovered_name = user_input.get(CONF_NAME, "Tewke Device")

            if await self._get_device_config_details():
                return await self.async_step_confirm_control_types()
            return await self.async_step_coap_enable()

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
        """Shown when CoAP is not reachable; lets the user retry or continue."""
        if user_input is not None:
            if await self._get_device_config_details():
                return await self.async_step_confirm_control_types()
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

    async def _get_device_config_details(self) -> dict[str, Any] | None:
        """Fetch device info from the CoAP ``/config`` endpoint.

        Returns the decoded payload dict, or ``None`` on any failure.
        Failures are non-fatal — the caller decides whether to abort.
        """
        if not self._discovered_host:
            return None

        context = None
        try:
            context = await aiocoap.Context.create_client_context()

            host = self._discovered_host
            if ":" in host and not host.startswith("["):
                host = f"[{host}]"

            request = aiocoap.Message(code=aiocoap.GET, uri=f"coap://{host}/config")
            response = await asyncio.wait_for(
                context.request(request).response, timeout=5.0
            )
        except TimeoutError:
            LOGGER.debug("CoAP communication timeout with %s", self._discovered_host)
            return None
        except Exception:  # noqa: BLE001
            LOGGER.debug("CoAP communication error with %s", self._discovered_host, exc_info=True)
            return None
        finally:
            if context is not None:
                with contextlib.suppress(Exception):
                    await context.shutdown()

        if not response.code.is_successful():
            LOGGER.error(
                "Could not get device configuration from %s: %s",
                self._discovered_name,
                response.code,
            )
            return None

        if response.payload:
            resp = cbor2.loads(response.payload)
            LOGGER.debug("Received config payload: %s", resp)
            return resp
        return None


