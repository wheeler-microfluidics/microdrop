"""
Copyright 2011 Ryan Fobel and Christian Fobel

This file is part of MicroDrop.

MicroDrop is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

MicroDrop is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with MicroDrop.  If not, see <http://www.gnu.org/licenses/>.
"""

import logging

import gtk
from pygtkhelpers.ui.dialogs import open_filechooser

from .. import glade_path
from ..app_context import get_app
from ..gui.plugin_download_dialog import PluginDownloadDialog
from ..plugin_manager import get_service_instance_by_name


class PluginManagerDialog(object):
    '''
    List installed plugins with the following action buttons for each plugin:

     - Enable
     - Disable
     - Update
     - **TODO** Uninstall
    '''
    def __init__(self):
        builder = gtk.Builder()
        builder.add_from_file(glade_path()
                              .joinpath('plugin_manager_dialog.glade'))
        self.window = builder.get_object('plugin_manager')
        self.vbox_plugins = builder.get_object('vbox_plugins')
        builder.connect_signals(self)

    def clear_plugin_list(self):
        self.vbox_plugins.foreach(lambda x: self.vbox_plugins.remove(x))

    @property
    def controller(self):
        plugin_name = 'microdrop.gui.plugin_manager_controller'
        service = get_service_instance_by_name(plugin_name, env='microdrop')
        return service

    def update(self):
        '''
        Update plugin list widget.
        '''
        self.clear_plugin_list()
        self.controller.update()
        for p in self.controller.plugins:
            self.vbox_plugins.pack_start(p.get_widget())

    def run(self):
        app = get_app()
        self.update()
        response = self.window.run()
        self.window.hide()
        for p in self.controller.plugins:
            package_name = p.get_plugin_package_name()
            if p.enabled():
                if package_name not in app.config["plugins"]["enabled"]:
                    app.config["plugins"]["enabled"].append(package_name)
            else:
                if package_name in app.config["plugins"]["enabled"]:
                    app.config["plugins"]["enabled"].remove(package_name)
        app.config.save()
        if self.controller.restart_required:
            logging.warning('Plugins were installed/uninstalled.\n'
                            'Program needs to be closed.\n'
                            'Please start program again for changes to take '
                            'effect.')
            # Use return code of `5` to signal program should be restarted.
            app.main_window_controller.on_destroy(None, return_code=5)
            return response
        return response

    def on_button_download_clicked(self, *args, **kwargs):
        '''
        Launch download dialog and install selected plugins.
        '''
        d = PluginDownloadDialog()
        response = d.run()

        if response == gtk.RESPONSE_OK:
            for p in d.selected_items():
                print 'installing: %s' % p
                self.controller.download_and_install_plugin(p)

    def on_button_install_clicked(self, *args, **kwargs):
        response = open_filechooser('Select plugin file',
                action=gtk.FILE_CHOOSER_ACTION_OPEN,
                patterns=['*.tar.gz', '*.tgz', '*.zip'])
        if response is None:
            return True

        return self.controller.install_from_archive(response)

    def on_button_update_all_clicked(self, *args, **kwargs):
        self.controller.update_all_plugins()


if __name__ == '__main__':
    pm = PluginManagerDialog()
