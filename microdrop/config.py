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
from shutil import ignore_patterns

from path import path
from configobj import ConfigObj, flatten_errors
from validate import Validator

from logger import logger, logging
from utility.user_paths import home_dir, app_data_dir, common_app_data_dir


def get_skeleton_path(dir_name):
    logger.debug('get_skeleton_path(%s)' % dir_name)
    if os.name == 'nt':
        source_dir = common_app_data_dir().joinpath('Microdrop', dir_name)
        if not source_dir.isdir():
            logger.warning('warning: %s does not exist in common AppData dir'\
                            % dir_name)
            source_dir = path(dir_name)
    else:
        source_dir = path(dir_name)
    if not source_dir.isdir():
        raise IOError, '%s/ directory not available.' % source_dir
    return source_dir


def device_skeleton_path():
    return get_skeleton_path('devices')


def plugins_skeleton_path():
    return get_skeleton_path('plugins')


class ValidationError(Exception):
    pass


class Config():
    default_directory = app_data_dir() / [path('.microdrop'), path('microdrop')][os.name == 'nt']
    default_filename = default_directory / path('microdrop.ini')
    spec = """
        [dmf_device]
        # directory containing DMF device files 
        directory = string(default=None)

        # name of the most recently used protocol
        name = string(default=None)

        [protocol]
        # name of the most recently used protocol
        name = string(default=None)

        [plugins]
        # directory containing microdrop plugins
        directory = string(default=None)
        
        # list of enabled plugins
        enabled = string_list(default=list())

        [logging]
        # enable logging to a file
        enabled = boolean(default=False)

        # path to the log file
        file = string(default=None)

        # log level (valid options are "debug", "info", "warning", and "error")
        level = option('debug', 'info', 'warning', 'error', default='warning')
        """

    def __init__(self):
        self.filename = self.default_filename
        self.load()

    def __getitem__(self, i):
        return self.data[i]

    def load(self, filename=None):
        """
        Load a Config object from a file.

        Args:
            filename: path to file. If None, try loading from the default
                location, and if there's no file, create a Config object
                with the default options.
        Raises:
            IOError: The file does not exist.
            ConfigObjError: There was a problem parsing the config file.
            ValidationError: There was a problem validating one or more fields.
        """
        if filename:
            logger.debug("[Config].load(%f)" % filename)
            logger.info("Loading config file from %s" % self.filename)
            if not path(filename).exists():
                raise IOError
            self.filename = path(filename)
        else:
            logger.debug("[Config].load()")
            if self.filename.exists():
                logger.info("Loading config file from %s" % self.filename)
            else:
                logger.info("Using default configuration.")

        self.data = ConfigObj(self.filename, configspec=self.spec.split("\n"))
        self._validate()

    def set_plugins(self, plugins):
        self.enabled_plugins = plugins

    def save(self, filename=None):
        if filename == None:
            filename = self.filename
        # make sure that the parent directory exists
        path(filename).parent.makedirs_p()
        with open(filename, 'w') as f:
            self.data.write(outfile=f)

    def _validate(self):
        validator = Validator()
        results = self.data.validate(validator, copy=True)
        if results != True:
            logger.error('Config file validation failed!')
            for (section_list, key, _) in flatten_errors(self.data, results):
                if key is not None:
                    logger.error('The "%s" key in the section "%s" failed '
                                 'validation' % (key, ', '.join(section_list)))
                else:
                    logger.error('The following section was missing:%s ' % 
                                 ', '.join(section_list))
            raise ValidationError
        self.data.filename = self.filename
        self._init_devices_dir()
        self._init_plugins_dir()

    def _init_devices_dir(self):
        if self.data['dmf_device']['directory'] is None:
            if os.name == 'nt':
                self.data['dmf_device']['directory'] = home_dir().joinpath('Microdrop', 'devices')
            else:
                self.data['dmf_device']['directory'] = home_dir().joinpath('.microdrop', 'devices')
        dmf_device_directory = path(self.data['dmf_device']['directory'])
        dmf_device_directory.parent.makedirs_p()
        devices = device_skeleton_path()
        if not dmf_device_directory.isdir():
            devices.copytree(dmf_device_directory)

    def _init_plugins_dir(self):
        if self.data['plugins']['directory'] is None:
            if os.name == 'nt':
                self.data['plugins']['directory'] = home_dir().joinpath('Microdrop', 'plugins')
            else:
                self.data['plugins']['directory'] = home_dir().joinpath('.microdrop', 'plugins')
        plugins_directory = path(self.data['plugins']['directory'])            
        plugins_directory.parent.makedirs_p()
        plugins = plugins_skeleton_path()
        if not plugins_directory.isdir():
            # Copy plugins directory to app data directory, keeping symlinks
            # intact.  If we don't keep symlinks as they are, we might end up
            # with infinite recursion.
            plugins.copytree(plugins_directory, symlinks=True,
                ignore=ignore_patterns('*.pyc'))
