from __future__ import annotations
from typing import Any

import logging
_LOGGER = logging.getLogger(__name__)

from enum import IntEnum
import time
import bleak_retry_connector

from bleak import BleakClient
from homeassistant.components import bluetooth
from homeassistant.components.light import (ATTR_BRIGHTNESS, ATTR_RGB_COLOR, ATTR_EFFECT, ColorMode, LightEntity,
                                            LightEntityFeature, ATTR_COLOR_TEMP_KELVIN)

from .const import DOMAIN

UUID_CONTROL_CHARACTERISTIC = '00010203-0405-0607-0809-0a0b0c0d2b11'

effects = {
    "Amanecer": 0x00,
    "Atardecer": 0x01,
    "Bosque": 0xd4,
    "Hojas crujiendo": 0xda,
    "Universo A": 0xc8,
    "Universo B": 0xc3,
    "Meteorito": 0xcd,
    "Lluvia de meteoritos": 0xe4,
    "Aurora A": 0xd7,
    "Aurora B": 0xf1,
    "Relampago A": 0xd6,
    "Relampago B": 0x55,
    "Relampago C": 0x34,
    "Cielo estrellado": 0xd9,
    "Estrella": 0xd5,
    "Copo de nieve A": 0x0f,
    "Copo de nieve B": 0x6a,
    "Primavera": 0xd2,
    "Verano A": 0xdf,
    "Verano B": 0xe8
}

class LedCommand(IntEnum):
    """ A control command packet's type. """
    POWER      = 0x01
    BRIGHTNESS = 0x04
    COLOR      = 0x05

class LedMode(IntEnum):
    """
    The mode in which a color change happens in.
    
    Currently only manual is supported.
    """
    MANUAL     = 0x15
    MICROPHONE = 0x06
    SCENES     = 0x05 

async def async_setup_entry(hass, config_entry, async_add_entities):
    light = hass.data[DOMAIN][config_entry.entry_id]
    #bluetooth setup
    ble_device = bluetooth.async_ble_device_from_address(hass, light.address.upper(), False)
    async_add_entities([GoveeBluetoothLight(light, ble_device)])

class GoveeBluetoothLight(LightEntity):
    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_supported_features = LightEntityFeature(
        LightEntityFeature.EFFECT | LightEntityFeature.FLASH | LightEntityFeature.TRANSITION)


    def __init__(self, light, ble_device) -> None:
        """Initialize an bluetooth light."""
        self._mac = light.address
        self._ble_device = ble_device
        self._state = None
        self._brightness = None

    @property
    def effect_list(self) -> list[str] | None:
        """Return the list of effects."""
        effect_list = effects.keys()

        return effect_list

    @property
    def name(self) -> str:
        """Return the name of the switch."""
        return "GOVEE Light"

    @property
    def unique_id(self) -> str:
        """Return a unique, Home Assistant friendly identifier for this entity."""
        return self._mac.replace(":", "")

    @property
    def brightness(self):
        return self._brightness

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        return self._state

    async def async_turn_on(self, **kwargs) -> None:
        await self._sendBluetoothData(LedCommand.POWER, [0x1])
        self._state = True

        if ATTR_BRIGHTNESS in kwargs:
            brightness255 = kwargs.get(ATTR_BRIGHTNESS, 255)
            brightnessPercent = int(brightness255/255.0*100)
            await self._sendBluetoothData(LedCommand.BRIGHTNESS, [brightnessPercent])
            self._brightness = brightness255

        if ATTR_RGB_COLOR in kwargs:
            red, green, blue = kwargs.get(ATTR_RGB_COLOR)
            await self._sendBluetoothData(LedCommand.COLOR, [LedMode.MANUAL, 0x01, red, green, blue, 0x00,  0x00, 0x00, 0x00, 0x00, 0xFF, 0x7F])

        if ATTR_EFFECT in kwargs:
            effect = kwargs.get(ATTR_EFFECT)
            if effect != "EFFECT_OFF":
                await self._sendBluetoothData(LedCommand.COLOR, [0x04, effects[effect]])


    async def async_turn_off(self, **kwargs) -> None:
        await self._sendBluetoothData(LedCommand.POWER, [0x0])
        self._state = False

    async def _connectBluetooth(self) -> BleakClient:
        client = await bleak_retry_connector.establish_connection(BleakClient, self._ble_device, self.unique_id)
        return client

    async def _sendBluetoothData(self, cmd, payload):
        if not isinstance(cmd, int):
            raise ValueError('Invalid command')
        if not isinstance(payload, bytes) and not (isinstance(payload, list) and all(isinstance(x, int) for x in payload)):
            raise ValueError('Invalid payload')
        if len(payload) > 17:
            raise ValueError('Payload too long')

        cmd = cmd & 0xFF
        payload = bytes(payload)

        frame = bytes([0x33, cmd]) + bytes(payload)
        # pad frame data to 19 bytes (plus checksum)
        frame += bytes([0] * (19 - len(frame)))
        
        # The checksum is calculated by XORing all data bytes
        checksum = 0
        for b in frame:
            checksum ^= b
        
        frame += bytes([checksum & 0xFF])
        client = await self._connectBluetooth()
        await client.write_gatt_char(UUID_CONTROL_CHARACTERISTIC, frame, False)