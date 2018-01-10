# Copyright (c) 2017 Shotgun Software Inc.
#
# CONFIDENTIAL AND PROPRIETARY
#
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights
# not expressly granted therein are reserved by Shotgun Software Inc.

import abc
import os
import functools
import pprint

import sgtk

from sgtk.platform.qt import QtCore, QtGui

from sstk.shotgun.class_Performer import Performer
from sstk.shotgun.class_PhysicalAsset import PhysicalAsset

HookBaseClass = sgtk.get_hook_baseclass()

ACTOR_TYPE_LIST = [("Select Type", None), ("Performer", Performer), ("Physical Asset (Props)", PhysicalAsset)]
NAME_IDX = 0
CLASS_IDX = 1


################################################################################
# The following classes are a poor man's framework to have multi value editing
# widgets.


class WidgetHandlerBase(object):
    """
    Base class for widgets that can handle multiple values for a single setting.

    The multi edit mode is a mode where the widget will advertise that updating
    it will affect different tasks that have different values for a given
    setting. It is up to the derived class to decide how it wants to advertise
    that state.
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, editor):
        """
        :param editor: Editing widget.
        """
        self._editor = editor
        self._is_multi_edit_mode = None

    @property
    def editor(self):
        """
        Returns the editing widget.
        """
        return self._editor

    @property
    def multi_edit_mode(self):
        """
        Flag indicating if the widget is in multi edit mode. Setting this to
        ``True`` will flip the widget into multi-edit mode.
        """
        return self._is_multi_edit_mode

    @multi_edit_mode.setter
    def multi_edit_mode(self, is_multi):
        if is_multi == self._is_multi_edit_mode:
            return

        self._is_multi_edit_mode = is_multi
        self._apply_edit_mode()

    @abc.abstractmethod
    def is_value_available(self):
        """
        Indicates if there is a value available to be consumed. This method
        generally returns True unless the widget is in multi-edit mode. In that
        """
        pass

    @abc.abstractmethod
    def _apply_edit_mode(self):
        pass


class ComboBoxHandler(WidgetHandlerBase):
    """
    Shows the editor widget with a label or checkbox depending on whether
    the widget is in multi-edit mode or not.

    When multiple values are available for this widget, the widget will by
    default be disabled and a checkbox will appear unchecked. By checking the
    checkbox, the user indicates they want to override the value with a specific
    one that will apply to all items.
    """

    def __init__(self, layout, text):
        """
        :param layout: Layout to add the widget into.
        :param text: Text on the left of the editor widget.
        """
        super(ComboBoxHandler, self).__init__(QtGui.QComboBox())

        self._layout = QtGui.QHBoxLayout()
        self._label = QtGui.QLabel(text)

        # FIXME: Should take the size of the text + icon as the minimum width.
        self._label.setMinimumWidth(50)

        self._editor.addItems([name for name, cls in ACTOR_TYPE_LIST])

        self._layout.addWidget(self._label)
        self._layout.addWidget(self.editor)

        layout.addRow(self._layout)

    def _apply_edit_mode(self):
        """
        Updates the UI to indicate the widget has multiple values or not.
        """
        # When the multi-edit mode is on we want to
        #  - show the check box
        #  - hide the label
        #  - disable the editor
        self._label.setVisible(self.multi_edit_mode is False)
        self._editor.setEnabled(self.multi_edit_mode is False)

    def is_value_available(self):
        """
        Indicates if a value is available to be consumed.
        """
        # If we're not in multi-edit mode, the value is available.
        if not self.multi_edit_mode:
            return True
        else:
            return True


class ActorsWidgetController(QtGui.QWidget):
    """
    Custom Ui to let the user choose manually which type of actor should be use to stock the information on shotgun
    """
    def __init__(self, parent):
        """
        :param parent: The parent widget of this one
        """
        QtGui.QWidget.__init__(self, parent)

        self.layout = QtGui.QFormLayout(self)
        self.setLayout(self.layout)
        self.actor_widget_dict = {}

    def setup_actors_widget(self, actors, previous_dict=None):
        """
        Create all the needed widget to show the different actor to create on shotgun.

        :param actors: List fo actors to show and give the possibility to change it's type
        :param previous_dict: The previous dictionary giving the info on what already been set or not. It's needed since
                              each time a custom widget is shown, the old one is deleted...
        """

        for act in sorted(actors, key=lambda actor: actor[0]):
            idx_to_set = 0
            if previous_dict and act in previous_dict:
                idx_to_set = previous_dict[act]

            cbh = ComboBoxHandler(self.layout, act)
            cbh.editor.setCurrentIndex(idx_to_set)
            cbh.editor.currentIndexChanged.connect(functools.partial(self._on_index_changed, act))
            self.actor_widget_dict[act] = idx_to_set

    def _on_index_changed(self, act_name, new_idx):
        """
        Used when the event currentIndexChanged is called on on of the ComboBox  (ComboBox)
        It will flag the controller to update the settings

        :param new_idx: The new index set for the combo box
        :param act_name: The name of the actor related to the combo box type
        """

        # Flag the controller to update the settings
        self.actor_widget_dict[act_name] = new_idx

    def update_actor_settings(self, actor_str, new_idx):
        """
        Will update the specific actor_widget_dict dictionary entry to make sure the current selected index is the
        good one

        :param actor_str: String representing the name of the actor (aka, the key in the dict)
        :param new_idx: The new index that changed and need to be set
        """

        if actor_str in self.actor_widget_dict:
            self.actor_widget_dict[actor_str] = new_idx


class RenderUploadTakeVersion(HookBaseClass):
    """
    Plugin for creating generic publishes in Shotgun
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize certain variable needed for the hook
        """
        super(RenderUploadTakeVersion, self).__init__(*args, **kwargs)

        self._actor_widget = None
        self._item = None

    # TODO - Find a specific icon ?
    @property
    def icon(self):
        """
        Path to an png icon on disk
        """

        # look for icon one level up from this hook's folder in "icons" folder
        return os.path.join(
            self.disk_location,
            os.pardir,
            "icons",
            "video.png"
        )

    '''
    def create_settings_widget(self, parent):
        """
        Creates a QT widget, parented below the given parent object, to
        provide viewing and editing capabilities for the given settings.

        :param parent: QWidget to parent the widget under
        :return: QWidget with an editor for the given setting or None if no custom widget is desired.
        """

        # If the widget already exist, do try to recreate it
        actors = self._item.properties.get("actors", None)
        previous_dict = None
        if self._actor_widget:
            previous_dict = self._actor_widget.actor_widget_dict

        self._actor_widget = ActorsWidgetController(parent)
        self._actor_widget.setup_actors_widget(actors, previous_dict)

        return self._actor_widget

    def get_ui_settings(self, controller):
        """
        Returns the modified settings.
        """
        settings = {}

        if controller:
            settings["actors"] = controller.actor_widget_dict

        return settings

    def set_ui_settings(self, controller, tasks_settings):
        """
        Updates the UI with the list of settings.
        """
        pass
    '''

    @property
    def name(self):
        """
        One line display name describing the plugin
        """
        return "Render and Upload Takes Versions"

    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """
        return "This plugin will generate and upload a version for the different takes found in the scene"

    @property
    def settings(self):
        """
        Dictionary defining the settings that this plugin expects to receive
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        A dictionary on the following form::

            {
                "Settings Name": {
                    "type": "settings_type",
                    "default": "default_value",
                    "description": "One line description of the setting"
            }

        The type string should be one of the data types that toolkit accepts as
        part of its environment configuration.
        """
        return {}

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["maya.*", "file.maya"]
        """
        return ["motionbuilder.take"]

    def accept(self, settings, item):
        """
        Method called by the publisher to determine if an item is of any
        interest to this plugin. Only items matching the filters defined via the
        item_filters property will be presented to this method.

        A publish task will be generated for each item accepted here. Returns a
        dictionary with the following booleans:

            - accepted: Indicates if the plugin is interested in this value at
                all. Required.
            - enabled: If True, the plugin will be enabled in the UI, otherwise
                it will be disabled. Optional, True by default.
            - visible: If True, the plugin will be visible in the UI, otherwise
                it will be hidden. Optional, True by default.
            - checked: If True, the plugin will be checked in the UI, otherwise
                it will be unchecked. Optional, True by default.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: dictionary with boolean keys accepted, required and enabled
        """
        self._item = item
        if not self._item.properties.get("cam_list", None):
            return {"accepted": False}
        else:
            return {"accepted": True}

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to publish.

        Returns a boolean to indicate validity.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process

        :returns: True if item is valid, False otherwise.
        """

        # See if we need to validate anything, at the moment, just return true
        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # TODO - Use sstk export_render_mobu functionnality to correctly generate and upload a render to shotgun
        pass

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once
        all the publish tasks have completed, and can for example
        be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # See if we need to to something after the publish (The export render process should correctly
        # clean what's needed
        pass