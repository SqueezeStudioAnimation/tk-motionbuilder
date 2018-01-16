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
import re

import sgtk

from sgtk.platform.qt import QtCore, QtGui

from sstk.shotgun.class_Performer import Performer
from sstk.shotgun.class_PhysicalAsset import PhysicalAsset
import sstk.jobs.export_render_mobu as job_export_render_mobu

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


# TODO - For x reason, in motionbuilder we have a problem with tri-state. There is no difference between checked and
# partially check...
class CheckboxHandler(WidgetHandlerBase):
    """
    Handles a checkbox in multi-value and single-value scenarios.

    When there's multiple different values available for the checkbox, it will
    be displayed with a partially checked state.
    """
    def __init__(self, layout, text):
        """
        :param layout: Layout in witch to add the widget.
        :param text: Name of the setting.
        """
        super(CheckboxHandler, self).__init__(QtGui.QCheckBox(text))
        layout.addWidget(self.editor)
        self.editor.setTristate(False)

    def _apply_edit_mode(self):
        """
        Updates the UI to indicate the widget has multiple values or not.
        """
        self.editor.setTristate(self.multi_edit_mode)
        # We're into multi-edit mode, so indicate the value is undetermined.
        if self.multi_edit_mode:
            self.editor.setCheckState(QtCore.Qt.PartiallyChecked)

    def is_value_available(self):
        """
        Indicates if a value is available to be consumed.
        """
        # If the checkbox is not partially checked, then the user has settled
        # on a value.
        return self.editor.checkState() != QtCore.Qt.PartiallyChecked


class CamerasWidgetController(QtGui.QWidget):
    """
    Custom Ui to let the user choose manually which type of actor should be use to stock the information on shotgun
    """
    def __init__(self, parent):
        """
        :param parent: The parent widget of this one
        """
        QtGui.QWidget.__init__(self, parent)

        self.cam_checkboxes = []

        self.layout = QtGui.QFormLayout(self)
        self.setLayout(self.layout)

        self._render_type_chk = CheckboxHandler(self.layout, "Send to farm (Currently unavailable)")
        self._render_type_chk.editor.setEnabled(False)
        self._cam_lbl = QtGui.QLabel("Choose which camera(s) you want to render from")
        self.layout.addWidget(self._cam_lbl)

    def setup_cams_widget(self, cams):
        """
        Create all the needed widget to show the different actor to create on shotgun.

        :param cams: List fo actors to show and give the possibility to change it's type
        """

        for cam in sorted(cams, key=lambda cam: cam.Name):
            chkh = CheckboxHandler(self.layout, cam.Name)
            chkh.editor.setChecked(False)
            self.cam_checkboxes.append(chkh)
            # chkh.editor.stateChanged.connect(functools.partial(self._on_state_changed, cam.Name))

    def send_to_farm(self):
        """
        Return the status of the take render to know if we want to send it on the farm or not

        :return: True if the used checked the farm checkbox else False
        """

        return self._render_type_chk.editor.isChecked()

    def _on_state_changed(self, cam, state):
        """
        Used when the state of a cam checkbox is changed. It will be used to maintain information
        about which camera need to be used or not

        :param cam: The new index set for the combo box
        :param state: The new state of the checkbox
        """

        # Flag the controller to update the settings
        self.cam_widget_dict[cam] = state


class RenderUploadTakeVersion(HookBaseClass):
    """
    Plugin for creating generic publishes in Shotgun
    """

    def __init__(self, *args, **kwargs):
        """
        Initialize certain variable needed for the hook
        """
        super(RenderUploadTakeVersion, self).__init__(*args, **kwargs)

        self._cam_widget = None
        self._item = None

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

    def create_settings_widget(self, parent):
        """
        Creates a QT widget, parented below the given parent object, to
        provide viewing and editing capabilities for the given settings.

        :param parent: QWidget to parent the widget under
        :return: QWidget with an editor for the given setting or None if no custom widget is desired.
        """

        # If the widget already exist, do try to recreate it
        cams = self._item.properties.get("cam_list", None)

        self._cam_widget = CamerasWidgetController(parent)
        self._cam_widget.setup_cams_widget(cams)

        return self._cam_widget

    def get_ui_settings(self, controller):
        """
        Returns the modified settings.

        :param: The controller on which the settings should be pulled off
        """

        settings = {}
        # Re-initialize the cams dictionary info
        settings["cams"] = {}

        # Ensure to copy the settings and not only reference them since the ui is not always rebuilt when
        # the user go from the same plugin entry to another one
        if controller:
            # Only set the settings if we are certain to now have a multi-edit mode with different value
            for chk in controller.cam_checkboxes:
                if chk.is_value_available():
                    # Stock the int since deepcopy doesn't seem to support QtCore.Qt.CheckState values
                    settings["cams"][chk.editor.text()] = int(chk.editor.checkState())

        return settings

    def _requires_multi_edit_mode(self, tasks_settings, setting_name):
        """
        Will check the different task settings to see if they are all at the same value. If that's not the case
        multi-edit mode is needed

        :param tasks_settings: All the different tasks setting compare
        :param setting_name: The name of the setting wanted to be compared

        :returns: True if the setting is the same for every task, False otherwise.
        """
        return all(
            tasks_settings[0][setting_name] == task_setting[setting_name]
            for task_setting in tasks_settings
        ) is False

    def _cams_settings_requires_multi_edit_mode(self, tasks_settings, cam_name):
        """
        Check if all the different tasks setting have a specific camera name value in there settings. If it's found,
        compare there value.

        :param tasks_settings: The different task settings to compare
        :param cam_name: The specific name of the same to check
        :return: True if the cam name setting is not the same on each setting or it exists on a setting and not on
                 others one. Else, return False
        """

        cam_exists_setting = []
        for settings in tasks_settings:
            if cam_name in settings["cams"]:
                cam_exists_setting.append(settings)

        # In case all cam name setting don't exist, return False since all param are equal
        if not cam_exists_setting:
            return False

        # If not all settings have the cam param set, check if the existing one are all false
        if len(tasks_settings) != len(cam_exists_setting):
            for setting in cam_exists_setting:
                if setting["cams"][cam_name]:
                    return True
            # No return have been done, everything is false, so all settings will be equal
            return False

        # Finally, if all cam name setting exist, compare there value to know if we need multi-edit mode
        return all(
            tasks_settings[0]["cams"][cam_name] == task_setting["cams"][cam_name]
            for task_setting in tasks_settings
        ) is False

    def set_ui_settings(self, controller, tasks_settings):
        """
        Updates the UI with the list of settings. Happen when the user select the plugin. Settings should be updated
        by the function get_ui_settings

        :param controller: The controller on which we want to update the settings
        """

        # TODO - Support multi edit of send to farm checkbox when it will be implemented

        for chk in controller.cam_checkboxes:
            cam_name = chk.editor.text()
            if cam_name in tasks_settings[0]["cams"]:
                chk.multi_edit_mode = self._cams_settings_requires_multi_edit_mode(tasks_settings, cam_name)
                # The case where other task settings doesn't have it's cams property dict set correctly will is handled
                # by the multi edit mode check
                if chk.multi_edit_mode is False:
                    chk.editor.setCheckState(
                        QtCore.Qt.Checked if tasks_settings[0]["cams"][cam_name] else QtCore.Qt.Unchecked
                    )
            else:
                # Do the check to know if all settings are at the same value
                chk.multi_edit_mode = self._cams_settings_requires_multi_edit_mode(tasks_settings, cam_name)
                if chk.multi_edit_mode is False:
                    chk.editor.setCheckState(QtCore.Qt.Unchecked)

    def manage_ui_settings(self, task, settings):
        """
        Function to help updating settings that would have nested element in it. Instead of just replace the setting
        entry, we will allow the plugin to update it by itself in the current task

        :param task: The task (Which is a combination of item + plugin) on which we want to update settings
        :param settings: The new updated settings
        """
        for k, v in settings.iteritems():
            # In case of cameras, we will want to go through all the entry of the cam to udpate them correctly, since
            # cam setting is a dictionary
            if k == "cams":
                for cam_name, val in v.iteritems():
                    task.settings[k].value[cam_name] = val
            else:
                task.settings[k].value = v

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
        Dictionary defining the settings that this plugin expects to recieve
        through the settings parameter in the accept, validate, publish and
        finalize methods.

        In the current case, we will have a internal setting that will be set to know which camera should be use
        to render a specific take
        """
        return {
            "cams": {
                "type": "dict",
                "default": {},
                "description": "Represent a dictionary of cameras with there render status"
            },
        }

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
            self.logger.info("No cam_list property could be found")
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

        # Right now we will not validate anything, but it could be nice to ensure that
        # TODO - Find a way to know if the publish plugin is active or not.
        # It doesn't work at the moment since we are not able to access the tree node item of the plugin from the
        # current item parent...
        '''
        for t in item.parent.tasks:
            if t.plugin.name.lower() == "publish to shotgun" and t.checked and t.enabled:
                return True
            else:
                self.logger.error("To be able to generate a render, please ensure to check the publish plugin first.")
                return False
        '''

        regex = '^[a-zA-Z0-9_]*$'

        # Validate that the take name (item name) doesn't have any invalid character that shotgun does not support in it
        if not re.match(regex, item.name):
            self.logger.error("Take name should only contain letters, numbers and underscore. Else, problem could"
                              "happen with shotgun. Please fix your take name before publishing")
            return False

        # Also validate the different camera name used to render,
        bad_cam_name = False
        cam_selected = False
        for cam_name, state in settings["cams"].value.iteritems():
            if state:
                cam_selected = True
                if not re.match(regex, cam_name):
                    bad_cam_name = True
                    self.logger.error("Camera named %s should only contain letters, numbers and underscore. Else, "
                                      "problem could happen with shotgun. "
                                      "Please fix the camera name before publishing" % (cam_name,))
        if not cam_selected:
            self.logger.warning("Please select at least one camera to be able to render the scene")
            return False

        if bad_cam_name:
            return False

        return True

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        from pyfbsdk import FBSystem
        system = FBSystem()

        # TODO - Use sstk export_render_mobu functionnality to correctly generate and upload a render to shotgun
        publish_data = item.parent.properties.get("sg_publish_data", None)

        if not publish_data:
            raise Exception("Could not generate render without publishing the file first. Please, ensure to check"
                            "the publish plugin before publishing for video.")
        else:
            # Keep the current cam to set it after the rendering pass
            cur_cam = system.Renderer.CurrentCamera
            # TODO - When needed, support farm render
            cam_list_str = ""
            for cam_name, state in settings["cams"].value.iteritems():
                if state:
                    if not cam_list_str:
                        cam_list_str += cam_name
                    else:
                        cam_list_str += ":" + cam_name
            if cam_list_str:
                render_job = job_export_render_mobu.create_job(publish_data["id"],
                                                               takes=item.name,
                                                               cameras=cam_list_str,
                                                               render_local=True)
                render_job.main()
            if cur_cam:
                system.Renderer.CurrentCamera = cur_cam
            else:
                self.logger.info("No render will be done since no cameras have been selected")

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