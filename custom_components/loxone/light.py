import asyncio
import logging
from typing import Any

import homeassistant.util.color as color_util
import numpy as np
from homeassistant.components.light import (
    SUPPORT_EFFECT,
    SUPPORT_BRIGHTNESS,
    SUPPORT_COLOR,
    SUPPORT_COLOR_TEMP,
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP,
    ATTR_HS_COLOR,
    Light,
    ToggleEntity
)
from homeassistant.const import (
    CONF_VALUE_TEMPLATE)

from . import get_room_name_from_room_uuid, \
    get_cat_name_from_cat_uuid, \
    get_all_light_controller, \
    get_all_dimmer

_LOGGER = logging.getLogger(__name__)

DEFAULT_NAME = 'Loxone Light Controller V2'
DEFAULT_FORCE_UPDATE = False

CONF_UUID = "uuid"
EVENT = "loxone_event"
DOMAIN = 'loxone'
SENDDOMAIN = "loxone_send"

STATE_ON = "on"
STATE_OFF = "off"


def to_hass_level(level):
    """Convert the given Loxone (0.0-100.0) light level to HASS (0-255)."""
    return int((level * 255) / 100)


def to_loxone_level(level):
    """Convert the given HASS light level (0-255) to Loxone (0.0-100.0)."""
    return float((level * 100) / 255)


def to_hass_color_temp(temp):
    """Linear interpolation between Loxone values from 2700 to 6500"""
    return np.interp(temp, [2700, 6500], [500, 153])


def to_loxone_color_temp(temp):
    """Linear interpolation between HASS values from 153 to 500"""
    return np.interp(temp, [153, 500], [6500, 2700])


async def async_setup_platform(hass, config, async_add_devices,
                               discovery_info=None):
    """Set up Loxone Light Controller."""
    if discovery_info is None:
        return

    value_template = config.get(CONF_VALUE_TEMPLATE)
    if value_template is not None:
        value_template.hass = hass

    config = hass.data[DOMAIN]
    loxconfig = config['loxconfig']
    devices = []
    all_dimmers = []
    all_color_picker = []
    all_switches = []

    for light_controller in get_all_light_controller(loxconfig):
        new_light_controller = LoxonelightcontrollerV2(name=light_controller['name'],
                                                       uuid=light_controller['uuidAction'],
                                                       sensortyp="lightcontrollerv2",
                                                       room=get_room_name_from_room_uuid(loxconfig,
                                                                                         light_controller.get('room',
                                                                                                              '')),
                                                       cat=get_cat_name_from_cat_uuid(loxconfig,
                                                                                      light_controller.get('cat', '')),
                                                       complete_data=light_controller,
                                                       async_add_devices=async_add_devices)

        if 'subControls' in light_controller:
            if len(light_controller['subControls']) > 0:
                for sub_controll in light_controller['subControls']:
                    if light_controller['subControls'][sub_controll]['type'] == "Dimmer":
                        light_controller['subControls'][sub_controll]['room'] = light_controller.get('room', '')
                        light_controller['subControls'][sub_controll]['cat'] = light_controller.get('cat', '')
                        all_dimmers.append(light_controller['subControls'][sub_controll])
                    elif light_controller['subControls'][sub_controll]['type'] == "Switch":
                        light_controller['subControls'][sub_controll]['room'] = light_controller.get('room', '')
                        light_controller['subControls'][sub_controll]['cat'] = light_controller.get('cat', '')
                        all_switches.append(light_controller['subControls'][sub_controll])

                    elif light_controller['subControls'][sub_controll]['type'] == "ColorPickerV2":
                        light_controller['subControls'][sub_controll]['room'] = light_controller.get('room', '')
                        light_controller['subControls'][sub_controll]['cat'] = light_controller.get('cat', '')
                        all_color_picker.append(light_controller['subControls'][sub_controll])

        hass.bus.async_listen(EVENT, new_light_controller.event_handler)
        devices.append(new_light_controller)

    all_dimmers += get_all_dimmer(loxconfig)

    for dimmer in all_dimmers:
        new_dimmer = LoxoneDimmer(name=dimmer['name'],
                                  uuid=dimmer['uuidAction'],
                                  uuid_position=dimmer['states']['position'],
                                  sensortyp="dimmer",
                                  room=get_room_name_from_room_uuid(loxconfig,
                                                                    dimmer.get('room', '')),
                                  cat=get_cat_name_from_cat_uuid(loxconfig,
                                                                 dimmer.get('cat', '')),
                                  complete_data=dimmer,
                                  async_add_devices=async_add_devices)

        hass.bus.async_listen(EVENT, new_dimmer.event_handler)
        devices.append(new_dimmer)

    for switch in all_switches:
        new_switch = LoxoneLight(name=switch['name'],
                                 uuid=switch['states']['active'],
                                 action_uuid=switch['uuidAction'],
                                 sensortyp="switch",
                                 room=get_room_name_from_room_uuid(loxconfig,
                                                                   dimmer.get('room', '')),
                                 cat=get_cat_name_from_cat_uuid(loxconfig,
                                                                dimmer.get('cat', '')),
                                 complete_data=dimmer,
                                 async_add_devices=async_add_devices)

        hass.bus.async_listen(EVENT, new_switch.event_handler)
        devices.append(new_switch)

    for color_picker in all_color_picker:
        new_color_picker = LoxoneColorPickerV2(name=color_picker['name'],
                                               color_uuid=color_picker['states']['color'],
                                               action_uuid=color_picker['uuidAction'],
                                               sensortyp="colorpicker",
                                               room=get_room_name_from_room_uuid(loxconfig,
                                                                                 color_picker.get('room', '')),
                                               cat=get_cat_name_from_cat_uuid(loxconfig,
                                                                              color_picker.get('cat', '')),
                                               complete_data=color_picker,
                                               async_add_devices=async_add_devices)

        hass.bus.async_listen(EVENT, new_color_picker.event_handler)
        devices.append(new_color_picker)

    async_add_devices(devices)
    return True


class LoxonelightcontrollerV2(Light):
    """Representation of a Sensor."""

    def __init__(self, name, uuid, sensortyp, room="", cat="",
                 complete_data=None, async_add_devices=None):
        """Initialize the sensor."""
        self._state = 0.0
        self._name = name
        self._uuid = uuid
        self._room = room
        self._cat = cat
        self._sensortyp = sensortyp
        self._data = complete_data
        self._action_uuid = uuid
        self._active_mood_uuid = ""
        self._moodlist_uuid = ""
        self._favorite_mood_uuid = ""
        self._additional_mood_uuid = ""
        self._active_moods = []
        self._moodlist = []
        self._additional_moodlist = []
        self._async_add_devices = async_add_devices

        if "states" in self._data:
            states = self._data['states']
            if "activeMoods" in states:
                self._active_mood_uuid = states["activeMoods"]

            if "moodList" in states:
                self._moodlist_uuid = states["moodList"]

            if "favoriteMoods" in states:
                self._favorite_mood_uuid = states["favoriteMoods"]

            if "additionalMoods" in states:
                self._additional_mood_uuid = states["additionalMoods"]

    @property
    def name(self):
        return self._name

    @property
    def uuid(self):
        return self._uuid

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._sensortyp

    @property
    def mood_list_uuid(self):
        return self._moodlist_uuid

    @property
    def hidden(self) -> bool:
        """Return True if the entity should be hidden from UIs."""
        return False

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return None

    def get_moodname_by_id(self, _id):
        for mood in self._moodlist:
            if "id" in mood and "name" in mood:
                if mood['id'] == _id:
                    return mood['name']
        return _id

    def get_id_by_moodname(self, _name):
        for mood in self._moodlist:
            if "id" in mood and "name" in mood:
                if mood['name'] == _name:
                    return mood['id']
        return _name

    @property
    def effect_list(self):
        """Return the moods of light controller."""
        moods = []
        for mood in self._moodlist:
            if "name" in mood:
                moods.append(mood['name'])
        return moods

    @property
    def effect(self):
        """Return the current effect."""
        if len(self._active_moods) == 1:
            return self.get_moodname_by_id(self._active_moods[0])
        return None

    def turn_on(self, **kwargs) -> None:
        if 'effect' in kwargs:
            effects = kwargs['effect'].split(",")
            if len(effects) == 1:
                mood_id = self.get_id_by_moodname(kwargs['effect'])
                if mood_id != kwargs['effect']:
                    self.hass.bus.async_fire(SENDDOMAIN,
                                             dict(uuid=self._uuid, value="changeTo/{}".format(mood_id)))
                else:
                    self.hass.bus.async_fire(SENDDOMAIN,
                                             dict(uuid=self._uuid, value="plus"))
            else:
                effect_ids = []
                for _ in effects:
                    mood_id = self.get_id_by_moodname(_.strip())
                    if mood_id != _:
                        effect_ids.append(mood_id)

                self.hass.bus.async_fire(SENDDOMAIN,
                                         dict(uuid=self._uuid, value="off"))

                for _ in effect_ids:
                    self.hass.bus.async_fire(SENDDOMAIN, dict(uuid=self._uuid, value="addMood/{}".format(_)))

        else:
            self.hass.bus.async_fire(SENDDOMAIN,
                                     dict(uuid=self._uuid, value="plus"))
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs) -> None:
        self.hass.bus.async_fire(SENDDOMAIN,
                                 dict(uuid=self._uuid, value="off"))
        self.schedule_update_ha_state()

    @property
    def name(self):
        """Return the name of the device if any."""
        return self._name

    async def event_handler(self, event):
        request_update = False
        if self._uuid in event.data:
            self._state = event.data[self._uuid]
            request_update = True

        if self._active_mood_uuid in event.data:
            self._active_moods = eval(event.data[self._active_mood_uuid])
            request_update = True

        if self._moodlist_uuid in event.data:
            event.data[self._moodlist_uuid] = event.data[self._moodlist_uuid].replace("true", "True")
            event.data[self._moodlist_uuid] = event.data[self._moodlist_uuid].replace("false", "False")
            self._moodlist = eval(event.data[self._moodlist_uuid])
            request_update = True

        if self._additional_mood_uuid in event.data:
            self._additional_moodlist = eval(event.data[self._additional_mood_uuid])
            request_update = True

        if request_update:
            self.async_schedule_update_ha_state()

    @property
    def state(self):
        """Return the state of the entity."""
        return STATE_ON if self.is_on else STATE_OFF

    @property
    def is_on(self) -> bool:
        if self._active_moods != [778]:
            return True
        else:
            return False

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {"uuid": self._uuid, "room": self._room,
                "category": self._cat,
                "selected_scene": self.effect,
                "device_typ": "lightcontrollerv2", "plattform": "loxone"}

    @property
    def supported_features(self):
        return SUPPORT_EFFECT


class LoxoneLight(ToggleEntity):
    """Representation of a light."""

    def __init__(self, name, uuid, action_uuid, sensortyp, room="", cat="",
                 complete_data=None, async_add_devices=None):

        self._state = 0.0
        self._name = name
        self._uuid = uuid
        self._room = room
        self._cat = cat
        self._sensortyp = sensortyp
        self._data = complete_data
        self._action_uuid = action_uuid
        self._async_add_devices = async_add_devices

    @property
    def name(self):
        return self._name

    @property
    def uuid(self):
        return self._uuid

    @property
    def state(self):
        """Return the state of the entity."""
        return STATE_ON if self._state == 1.0 else STATE_OFF

    @property
    def is_on(self) -> bool:
        if self.state == STATE_ON:
            return True
        else:
            return False

    def turn_on(self, **kwargs: Any) -> None:
        self.hass.bus.async_fire(SENDDOMAIN,
                                 dict(uuid=self._action_uuid, value="on"))
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs: Any) -> None:
        self.hass.bus.async_fire(SENDDOMAIN,
                                 dict(uuid=self._action_uuid, value="off"))
        self.schedule_update_ha_state()

    @property
    def state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {"uuid": self._uuid, "room": self._room,
                "category": self._cat,
                "device_typ": "light", "plattform": "loxone"}

    @property
    def supported_features(self):
        """Flag supported features."""
        return 0

    async def event_handler(self, event):
        request_update = False
        if self._uuid in event.data:
            self._state = event.data[self._uuid]
            request_update = True

        if request_update:
            self.async_schedule_update_ha_state()


class LoxoneColorPickerV2(Light):
    def __init__(self, name, color_uuid, action_uuid, sensortyp, room="", cat="",
                 complete_data=None, async_add_devices=None):
        self._name = name
        self._color_uuid = color_uuid
        self._action_uuid = action_uuid
        self._sensortyp = sensortyp
        self._data = complete_data
        self._room = room
        self._cat = cat
        self._async_add_devices = async_add_devices
        self._position = 0
        self._rgb_color = color_util.color_hs_to_RGB(0, 0)
        self._color_temp = 0

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._sensortyp

    @property
    def state(self):
        """Return the state of the entity."""
        return STATE_ON if self.is_on else STATE_OFF

    @property
    def is_on(self) -> bool:
        return self._position > 0

    def turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            self.hass.bus.async_fire(SENDDOMAIN,
                                     dict(uuid=self._action_uuid,
                                          value='temp({},{})'.format(int(to_loxone_level(kwargs[ATTR_BRIGHTNESS])),
                                                                     int(to_loxone_color_temp(self._color_temp)))))

        elif ATTR_COLOR_TEMP in kwargs:
            self.hass.bus.async_fire(SENDDOMAIN,
                                     dict(uuid=self._action_uuid, value='temp({},{})'.format(self._position,
                                                                                             int(to_loxone_color_temp(
                                                                                                 kwargs[
                                                                                                     ATTR_COLOR_TEMP]))
                                                                                             )))
        elif ATTR_HS_COLOR in kwargs:
            r, g, b = color_util.color_hs_to_RGB(kwargs[ATTR_HS_COLOR][0], kwargs[ATTR_HS_COLOR][1])
            h, s, v = color_util.color_RGB_to_hsv(r, g, b)
            self.hass.bus.async_fire(SENDDOMAIN,
                                     dict(uuid=self._action_uuid, value='hsv({},{},{})'.format(h, s, v)))
        else:
            self.hass.bus.async_fire(SENDDOMAIN, dict(uuid=self._action_uuid, value="setBrightness/1"))
        self.schedule_update_ha_state()

    def turn_off(self) -> None:
        self.hass.bus.async_fire(SENDDOMAIN, dict(uuid=self._action_uuid, value="setBrightness/0"))
        self.schedule_update_ha_state()

    @property
    def name(self):
        return self._name

    @property
    def uuid(self):
        return self._uuid

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {"uuid": self._action_uuid, "room": self._room,
                "category": self._cat,
                "device_typ": self._sensortyp, "plattform": "loxone"}

    async def event_handler(self, event):
        request_update = False
        if self._color_uuid in event.data:
            color = event.data[self._color_uuid]
            if color.startswith('hsv'):
                color = color.replace('hsv', '')
                color = eval(color)
                self._rgb_color = color_util.color_hs_to_RGB(color[0], color[1])
                self._position = color[2]
                request_update = True

            elif color.startswith('temp'):
                color = color.replace('temp', '')
                color = eval(color)
                self._color_temp = to_hass_color_temp(color[1])
                self._position = color[0]
                request_update = True

        if self._action_uuid in event.data:
            pass

        if request_update:
            self.async_schedule_update_ha_state()

    @property
    def brightness(self):
        """Return the brightness of the group lights."""
        return to_hass_level(self._position)

    @property
    def hs_color(self):
        return color_util.color_RGB_to_hs(self._rgb_color[0], self._rgb_color[1], self._rgb_color[2])

    @property
    def color_temp(self):
        return self._color_temp

    @property
    def min_mireds(self):
        return 153

    @property
    def max_mireds(self):
        return 500

    @property
    def white_value(self):
        return None

    @property
    def supported_features(self):
        return SUPPORT_BRIGHTNESS | SUPPORT_COLOR | SUPPORT_COLOR_TEMP


class LoxoneDimmer(Light):
    """Representation of a Dimmer."""

    def __init__(self, name, uuid, uuid_position, sensortyp, room="", cat="",
                 complete_data=None, async_add_devices=None):
        """Initialize the sensor."""
        self._state = False
        self._position = 0.0
        self._min = 0.0
        self._max = 100.0
        self._name = name
        self._uuid = uuid
        self._uuid_position = uuid_position
        self._room = room
        self._cat = cat
        self._sensortyp = sensortyp
        self._data = complete_data
        self._action_uuid = uuid
        self._async_add_devices = async_add_devices

    @property
    def name(self):
        return self._name

    @property
    def uuid(self):
        return self._uuid

    @property
    def device_class(self):
        """Return the class of this device, from component DEVICE_CLASSES."""
        return self._sensortyp

    @property
    def hidden(self) -> bool:
        """Return True if the entity should be hidden from UIs."""
        return False

    @property
    def brightness(self):
        """Return the brightness of the group lights."""
        return to_hass_level(self._position)

    @property
    def icon(self):
        """Return the icon to use in the frontend, if any."""
        return None

    def turn_on(self, **kwargs) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            self.hass.bus.async_fire(SENDDOMAIN,
                                     dict(uuid=self._uuid, value=to_loxone_level(kwargs[ATTR_BRIGHTNESS])))
        else:
            self.hass.bus.async_fire(SENDDOMAIN, dict(uuid=self._uuid, value="on"))
        self.schedule_update_ha_state()

    def turn_off(self, **kwargs) -> None:
        self.hass.bus.async_fire(SENDDOMAIN, dict(uuid=self._uuid, value="off"))
        self.schedule_update_ha_state()

    async def event_handler(self, event):
        request_update = False
        if self._uuid_position in event.data:
            self._position = event.data[self._uuid_position]
            request_update = True

        if request_update:
            self.async_schedule_update_ha_state()

    @property
    def state(self):
        """Return the state of the entity."""
        return STATE_ON if self.is_on else STATE_OFF

    @property
    def is_on(self) -> bool:
        return self._position > 0

    @property
    def device_state_attributes(self):
        """Return device specific state attributes.

        Implemented by platform classes.
        """
        return {"uuid": self._uuid, "room": self._room,
                "category": self._cat,
                "device_typ": self._sensortyp, "plattform": "loxone"}

    @property
    def supported_features(self):
        return SUPPORT_BRIGHTNESS
