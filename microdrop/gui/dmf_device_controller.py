"""
Copyright 2011 Ryan Fobel

This file is part of Microdrop.

Microdrop is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

Microdrop is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with Microdrop.  If not, see <http://www.gnu.org/licenses/>.
"""

import os
import traceback

import gtk
import numpy as np
from xml.etree import ElementTree as et
from pyparsing import Literal, Combine, Optional, Word, Group, OneOrMore, nums

from dmf_device_view import DmfDeviceView
from dmf_device import DmfDevice
from protocol import Protocol
from experiment_log import ExperimentLog
from plugin_manager import IPlugin, SingletonPlugin, ExtensionPoint, \
    implements, emit_signal, PluginGlobals
from utility import is_float
from app_context import get_app
from logger import logger


PluginGlobals.push_env('microdrop')

class DmfDeviceOptions(object):
    def __init__(self, state_of_channels=None):
        app = get_app()
        if state_of_channels is None:
            self.state_of_channels = np.zeros(app.protocol.n_channels)
        else:
            self.state_of_channels = deepcopy(state_of_channels)


class DmfDeviceController(SingletonPlugin):
    implements(IPlugin)
    
    def __init__(self):
        self.name = "microdrop.gui.dmf_device_controller"        
        self.view = None
        self.popup = None
        self.last_electrode_clicked = None
        
    def on_app_init(self):        
        app = get_app()
        self.view = DmfDeviceView(app.builder.get_object("dmf_device_view"))
        app.builder.add_from_file(os.path.join("gui",
                                   "glade",
                                   "right_click_popup.glade"))
        self.popup = app.builder.get_object("popup")
        app.signals["on_dmf_device_view_button_press_event"] = self.on_button_press
        app.signals["on_dmf_device_view_key_press_event"] = self.on_key_press
        app.signals["on_dmf_device_view_expose_event"] = self.view.on_expose
        app.signals["on_menu_load_dmf_device_activate"] = self.on_load_dmf_device
        app.signals["on_menu_import_dmf_device_activate"] = \
                self.on_import_dmf_device
        app.signals["on_menu_rename_dmf_device_activate"] = self.on_rename_dmf_device 
        app.signals["on_menu_save_dmf_device_activate"] = self.on_save_dmf_device 
        app.signals["on_menu_save_dmf_device_as_activate"] = self.on_save_dmf_device_as 
        app.signals["on_menu_edit_electrode_channels_activate"] = self.on_edit_electrode_channels
        app.signals["on_menu_edit_electrode_area_activate"] = self.on_edit_electrode_area
        app.dmf_device_controller = self

    def get_default_options(self):
        return DmfDeviceOptions()

    def get_step_options(self, step=None):
        """
        Return a FeedbackOptions object for the current step in the protocol.
        If none exists yet, create a new one.
        """
        app = get_app()
        protocol_options = app.protocol.get_data('microdrop.gui.protocol_controller')
        if step is None:
            step = protocol_options.current_step_number
        
        options = app.protocol.current_step().get_data(self.name)
        if options is None:
            # No data is registered for this plugin (for this step).
            options = self.get_default_options()
            app.protocol.current_step().set_data(self.name, options)
        return options

    def on_button_press(self, widget, event):
        '''
        Modifies state of channel based on mouse-click.
        '''
        app = get_app()
        self.view.widget.grab_focus()
        options = self.get_step_options()
        state_updated = False
        for electrode in app.dmf_device.electrodes.values():
            if electrode.contains(
                    event.x / self.view.scale - self.view.offset[0],
                    event.y / self.view.scale - self.view.offset[1]):
                self.last_electrode_clicked = electrode
                if event.button == 1:
                    state = options.state_of_channels
                    if len(electrode.channels): 
                        for channel in electrode.channels:
                            if state[channel] > 0:
                                state[channel] = 0
                            else:
                                state[channel] = 1
                            state_updated = True
                    else:
                        logger.error("no channel assigned to electrode.")
                elif event.button == 3:
                    self.popup.popup(None, None, None, event.button,
                                     event.time, data=None)
                break
        if state_updated:
            protocol_options = app.protocol\
                .get_data('microdrop.gui.protocol_controller')
            #app.main_window_controller.update()
            emit_signal('on_step_options_changed',
                        [self.name, protocol_options.current_step_number],
                        interface=IPlugin)
        return True

    def on_key_press(self, widget, data=None):
        pass
    
    def on_load_dmf_device(self, widget, data=None):
        app = get_app()
        dialog = gtk.FileChooserDialog(title="Load device",
                                       action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=(gtk.STOCK_CANCEL,
                                                gtk.RESPONSE_CANCEL,
                                                gtk.STOCK_OPEN,
                                                gtk.RESPONSE_OK))
        dialog.set_default_response(gtk.RESPONSE_OK)
        dialog.set_current_folder(app.config.dmf_device_directory)
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self.filename = dialog.get_filename()
            emit_signal("on_dmf_device_changed", [DmfDevice.load(self.filename)])
        dialog.destroy()
        app.main_window_controller.update()
        
    def on_import_dmf_device(self, widget, data=None):
        app = get_app()
        dialog = gtk.FileChooserDialog(title="Import device",
                                       action=gtk.FILE_CHOOSER_ACTION_OPEN,
                                       buttons=(gtk.STOCK_CANCEL,
                                                gtk.RESPONSE_CANCEL,
                                                gtk.STOCK_OPEN,
                                                gtk.RESPONSE_OK))
        filter = gtk.FileFilter()
        filter.set_name("*.svg")
        filter.add_pattern("*.svg")
        dialog.add_filter(filter)  
        dialog.set_default_response(gtk.RESPONSE_OK)
        response = dialog.run()

        if response == gtk.RESPONSE_OK:
            filename = dialog.get_filename()
            
            # Pyparsing grammar for svg:
            #
            # This code is based on Don C. Ingle's svg2py program, available at:
            # http://annarchy.cairographics.org/svgtopycairo/
            dot = Literal(".")
            comma = Literal(",").suppress()
            floater = Combine(Optional("-") + Word(nums) + dot + Word(nums))
            couple = floater + comma + floater
            M_command = "M" + Group(couple)
            C_command = "C" + Group(couple + couple + couple)
            L_command = "L" + Group(couple)
            Z_command = "Z"
            svgcommand = M_command | C_command | L_command | Z_command
            phrase = OneOrMore(Group(svgcommand))
            
            dmf_device = DmfDevice()
            try:
                tree = et.parse(filename)

                ns = "http://www.w3.org/2000/svg" # The XML namespace.
                for group in tree.getiterator('{%s}g' % ns):
                    for e in group.getiterator('{%s}path' % ns):
                        is_closed = False
                        p = e.get("d")

                        tokens = phrase.parseString(p.upper())
                        
                        # check if the path is closed
                        if tokens[-1][0]=='Z':
                            is_closed = True
                        else: # or if the start/end points are the same
                            try:
                                start_point = tokens[0][1].asList()
                                end_point = tokens[-1][1].asList()
                                if start_point==end_point:
                                    is_closed = True
                            except ValueError:
                                logger.error("ValueError")
                        if is_closed:
                            path = []
                            for step in tokens:
                                command = step[0]
                                if command=="M" or command=="L":
                                    x,y = step[1].asList()
                                    path.append({'command':step[0],
                                                 'x':x, 'y':y})
                                elif command=="Z":
                                    path.append({'command':step[0]})
                                else:
                                    logger.error("error")
                            dmf_device.add_electrode_path(path)
                emit_signal("on_dmf_device_changed", [dmf_device])
            except Exception, why:
                app.main_window_controller.error(why)
        dialog.destroy()
        app.main_window_controller.update()

    def on_rename_dmf_device(self, widget, data=None):
        app = get_app()
        app.config_controller.save_dmf_device(rename=True)

    def on_save_dmf_device(self, widget, data=None):
        app = get_app()
        app.config_controller.save_dmf_device()

    def on_save_dmf_device_as(self, widget, data=None):
        app = get_app()
        app.config_controller.save_dmf_device(save_as=True)
        
    def on_edit_electrode_channels(self, widget, data=None):
        # TODO: set default value
        channel_list = ""
        for i in self.last_electrode_clicked.channels:
            channel_list += str(i) + ','
        channel_list = channel_list[:-1]
        app = get_app()
        channel_list = app.main_window_controller.get_text_input(
            "Edit electrode channels",
            "Channels",
            channel_list)
        if channel_list:
            channels = channel_list.split(',')
            try: # convert to integers
                if len(channels[0]):
                    for i in range(0,len(channels)):
                        channels[i] = int(channels[i])
                else:
                    channels = []
                if channels and max(channels) >= app.protocol.n_channels:
                    app.protocol.set_number_of_channels(max(channels)+1)
                self.last_electrode_clicked.channels = channels
            except:
                app.main_window_controller.error("Invalid channel.")
        app.main_window_controller.update()
        
    def on_edit_electrode_area(self, widget, data=None):
        app = get_app()
        if app.dmf_device.scale is None:
            area = ""
        else:
            area = self.last_electrode_clicked.area() * app.dmf_device.scale
        area = app.main_window_controller.get_text_input(
            "Edit electrode area",
            "Area of electrode in mm<span rise=\"5000\" font_size=\"smaller\">"
            "2</span>:",
            str(area))
        if area:
            if is_float(area):
                app.dmf_device.scale = \
                    float(area)/self.last_electrode_clicked.area()
            else:
                app.main_window_controller.error("Area value is invalid.")
    
    def on_dmf_device_changed(self, dmf_device):
        self.view.fit_device()

    def on_step_options_changed(self, plugin_name, step_number):
        '''
        The step options for the current step have changed.
        If the change was to options affecting this plugin, update state.
        '''
        app = get_app()
        protocol_options = app.protocol.get_data('microdrop.gui.protocol_controller')
        if protocol_options.current_step_number == step_number\
                and plugin_name == self.name:
            self.update()

    def update(self):
        app = get_app()
        options = self.get_step_options()
        state_of_all_channels = options.state_of_channels
        for id, electrode in app.dmf_device.electrodes.iteritems():
            channels = app.dmf_device.electrodes[id].channels
            if channels:
                # get the state(s) of the channel(s) connected to this electrode
                states = state_of_all_channels[channels]
    
                # if all of the states are the same
                if len(np.nonzero(states == states[0])[0]) == len(states):
                    electrode.state = states[0]
                    if states[0] > 0:
                        self.view.electrode_color[id] = (1,1,1)
                    else:
                        self.view.electrode_color[id] = (0,0,1)
                else:
                    #TODO: this could be used for resistive heating 
                    logger.error("not supported yet")
            else:
                self.view.electrode_color[id] = (1,0,0)
        self.view.update()


PluginGlobals.pop_env()
