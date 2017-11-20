# Copyright (c) 2017 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import sgtk
from sgtk import TankError

from pyfbsdk import FBApplication, FBFilePopup, FBFilePopupStyle

mb_app = FBApplication()

HookBaseClass = sgtk.get_hook_baseclass()

# TODO - Possibly define more shotgun entity template info
CONTEXT_TEMPLATE = {
    "routine":
        {
            "work_template": "mobu_routine_work",
            "publish_template": "mobu_routine_publish",
        },
    "routine_subsession":
        {
            "work_template": "mobu_routine_subsession_work",
            "publish_template": "mobu_routine_subsession_publish",
        },
    "mocaptake":
        {
            "work_template": "mobu_mocaptake_work",
            "publish_template": "mobu_mocaptake_publish",
        },
    "mocaptake_subsession":
        {
            "work_template": "mobu_mocaptake_subsession_work",
            "publish_template": "mobu_mocaptake_subsession_publish",
        },
    "asset":
        {
            "work_template": "mobu_asset_work",
            "publish_template": "mobu_asset_publish",
        },
}

class MotionBuilderSessionPublishPlugin(HookBaseClass):
    """
    Plugin for publishing an open Motion Builder session.

    This hook relies on functionality found in the base file publisher hook in
    the publish2 app and should inherit from it in the configuration. The hook
    setting for this plugin should look something like this::

        hook: "{self}/publish_file.py:{engine}/tk-multi-publish2/basic/publish_session.py"

    """

    # NOTE: The plugin icon and name are defined by the base file plugin.
    @property
    def description(self):
        """
        Verbose, multi-line description of what the plugin does. This can
        contain simple html for formatting.
        """

        loader_url = "https://support.shotgunsoftware.com/hc/en-us/articles/219033078"

        return """
        Publishes the file to Shotgun. A <b>Publish</b> entry will be
        created in Shotgun which will include a reference to the file's current
        path on disk. If a publish template is configured, a copy of the
        current session will be copied to the publish template path which
        will be the file that is published. Other users will be able to access
        the published file via the <b><a href='%s'>Loader</a></b> so long as
        they have access to the file's location on disk.

        If the session has not been saved, validation will fail and a button
        will be provided in the logging output to save the file.

        <h3>File versioning</h3>
        If the filename contains a version number, the process will bump the
        file to the next version after publishing.

        The <code>version</code> field of the resulting <b>Publish</b> in
        Shotgun will also reflect the version number identified in the filename.
        The basic worklfow recognizes the following version formats by default:

        <ul>
        <li><code>filename.v###.ext</code></li>
        <li><code>filename_v###.ext</code></li>
        <li><code>filename-v###.ext</code></li>
        </ul>

        After publishing, if a version number is detected in the work file, the
        work file will automatically be saved to the next incremental version
        number. For example, <code>filename.v001.ext</code> will be published
        and copied to <code>filename.v002.ext</code>

        If the next incremental version of the file already exists on disk, the
        validation step will produce a warning, and a button will be provided in
        the logging output which will allow saving the session to the next
        available version number prior to publishing.

        <br><br><i>NOTE: any amount of version number padding is supported. for
        non-template based workflows.</i>

        <h3>Overwriting an existing publish</h3>
        In non-template workflows, a file can be published multiple times,
        however only the most recent publish will be available to other users.
        Warnings will be provided during validation if there are previous
        publishes.
        """ % (loader_url,)

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

        # inherit the settings from the base publish plugin
        base_settings = super(MotionBuilderSessionPublishPlugin, self).settings or {}

        # settings specific to this class
        mobu_publish_settings = {
            "Publish Template": {
                "type": "template",
                "default": None,
                "description": "Template path for published work files. Should"
                               "correspond to a template defined in "
                               "templates.yml.",
            },
            "Force Template": {
                "type": "boolean",
                "default": True,
                "description": "Is the publish plugin allowed to publish without template validation. If not, "
                               "more validation will be done to be able to get the good template for the context"
            },
        }

        # update the base settings
        base_settings.update(mobu_publish_settings)

        return base_settings

    @property
    def item_filters(self):
        """
        List of item types that this plugin is interested in.

        Only items matching entries in this list will be presented to the
        accept() method. Strings can contain glob patters such as *, for example
        ["motionbuilder.*", "file.motionbuilder"]
        """
        return ["motionbuilder.fbx"]

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

        path = _session_path()

        if not path:
            # the session has not been saved before (no path determined).
            # provide a save button. the session will need to be saved before
            # validation will succeed.
            self.logger.warn(
                "The Motion Builder session has not been saved.",
                extra=_get_save_as_action(item.context)
            )

        # because a publish template is configured, disable context change. This
        # is a temporary measure until the publisher handles context switching
        # natively.
        if settings.get("Publish Template").value:
            item.context_change_allowed = False

        self.logger.info(
            "Motion Builder '%s' plugin accepted the current Motion Builder session." %
            ("Publish Session",)
        )
        return {
            "accepted": True,
            "checked": True
        }

    def validate(self, settings, item):
        """
        Validates the given item to check that it is ok to publish. Returns a
        boolean to indicate validity.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        :returns: True if item is valid, False otherwise.
        """

        publisher = self.parent
        path = _session_path()

        force_template = settings.get("Force Template")

        if not path:
            # the session still requires saving. provide a save button.
            # validation fails.
            error_msg = "The Motion Builder session has not been saved."
            self.logger.error(
                error_msg,
                extra=_get_save_as_action(item.context)
            )
            raise Exception(error_msg)

        # Refuse validation if we force template and don't have a task. Right now, template to publish data
        # are only use with task
        if force_template and not item.context.task:
            error_msg = "A task need to be selected before publishing"
            self.logger.error(
                error_msg,
            )
            return False

        # ensure we have an updated project root
        project_root = os.path.dirname(path)
        item.properties["project_root"] = project_root

        # log if no project root could be determined.
        if not project_root:
            self.logger.info(
                "Your session is not part of a Motion Builder project.",
                extra=_get_save_as_action()
            )

        # ---- check the session against any attached work template

        # get the path in a normalized state. no trailing separator,
        # separators are appropriate for current os, no double separators,
        # etc.
        path = sgtk.util.ShotgunPath.normalize(path)

        # if the session item has a known work template, see if the path
        # matches. if not, warn the user and provide a way to save the file to
        # a different path
        work_template = item.properties.get("work_template")
        if not work_template:
            if force_template:
                self._get_templates_from_context(item)
                work_template = item.properties.get("work_template")
                # If we still are not able to find the template, fail the validation
                if not work_template:
                    self.logger.error("No work template configured. "
                                      "Validation failed since Force Template settings is on")
                    return False
            else:
                self.logger.debug("No work template configured.")

        if work_template:
            if not work_template.validate(path):
                msg = "The current session does not match the configured work file template."
                if not force_template:
                    self.logger.warning(msg, extra=_get_save_as_action(context=item.context))
                else:
                    self.logger.error(msg, extra=_get_save_as_action(context=item.context))
                    return False
            else:
                self.logger.debug(
                    "Work template configured and matches session file.")

        # ---- see if the version can be bumped post-publish

        # check to see if the next version of the work file already exists on
        # disk. if so, warn the user and provide the ability to jump to save
        # to that version now
        (next_version_path, version) = self._get_next_version_info(path, item)
        if next_version_path and os.path.exists(next_version_path):

            # determine the next available version_number. just keep asking for
            # the next one until we get one that doesn't exist.
            while os.path.exists(next_version_path):
                (next_version_path, version) = self._get_next_version_info(
                    next_version_path, item)

            error_msg = "The next version of this file already exists on disk."
            self.logger.error(
                error_msg,
                extra={
                    "action_button": {
                        "label": "Save to v%s" % (version,),
                        "tooltip": "Save to the next available version number, "
                                   "v%s" % (version,),
                        "callback": lambda: _save_session(next_version_path)
                    }
                }
            )
            raise Exception(error_msg)

        # ---- populate the necessary properties and call base class validation

        # populate the publish template on the item if found
        publish_template_setting = settings.get("Publish Template")
        publish_template = publisher.engine.get_template_by_name(
            publish_template_setting.value)
        if publish_template:
            item.properties["publish_template"] = publish_template
        else:
            # In these case, we want to determine automatically the context
            if force_template:
                self._get_templates_from_context(item)
                publish_template = item.properties.get("publish_template")
                if not publish_template:
                    # Try to get the good template, else get the one from the config
                    self.logger.error("No publish template configured. Validation failed since Force "
                                      "Template settings is on")
                    return False

        # set the session path on the item for use by the base plugin validation
        # step. NOTE: this path could change prior to the publish phase.
        item.properties["path"] = path

        # run the base class validation
        return super(MotionBuilderSessionPublishPlugin, self).validate(settings, item)

    def publish(self, settings, item):
        """
        Executes the publish logic for the given item and settings.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # get the path in a normalized state. no trailing separator, separators
        # are appropriate for current os, no double separators, etc.
        path = sgtk.util.ShotgunPath.normalize(_session_path())

        # ensure the session is saved
        _save_session(path)

        # update the item with the saved session path
        item.properties["path"] = path

        # let the base class register the publish
        super(MotionBuilderSessionPublishPlugin, self).publish(settings, item)

    def finalize(self, settings, item):
        """
        Execute the finalization pass. This pass executes once all the publish
        tasks have completed, and can for example be used to version up files.

        :param settings: Dictionary of Settings. The keys are strings, matching
            the keys returned in the settings property. The values are `Setting`
            instances.
        :param item: Item to process
        """

        # do the base class finalization
        super(MotionBuilderSessionPublishPlugin, self).finalize(settings, item)

        # bump the session file to the next version
        self._save_to_next_version(item.properties["path"], item, _save_session)

    def _get_templates_from_context(self, item):
        """
        Special function to get the template for an item using the context assigned to it. It will analyze the item
        context and use the variable CONTEXT_TEMPLATE to determine what are the template to return.

        Take into consideration that not all entity type are currently supported with the functionnality. It will also
        be only use if Force Template setting is set to True

        :param item: The UI item on which we will have the context information and where we will stock the template

        :return: Return a tuple containing the work template and publish template
        """

        self.logger.info("Determining template automatically")

        publisher = self.parent

        ctx_entity = item.context.entity
        entity_type = ctx_entity["type"]
        is_routine_or_take = entity_type == "Routine" or entity_type == "MocapTake"

        if entity_type.lower() not in CONTEXT_TEMPLATE:
            self.logger.debug("Could not determine template for entity %s of type %s. "
                              "Context is currently not supported" % (item.context.entity, entity_type,))
            return
        else:
            fields = []
            if is_routine_or_take:
                fields = ["sg_session", "sg_subsession"]

            ctx_entity = self.parent.shotgun.find_one(entity_type, filters=[("id", "is", ctx_entity["id"])],
                                                      fields=fields)
            if not ctx_entity:
                self.logger.debug("Could not determine template for entity %s of type %s. "
                                  "Entity supplementary info could not be found" %
                                  (item.context.entity, ctx_entity["type"],))
                return
            else:
                template_info = CONTEXT_TEMPLATE[entity_type.lower()]
                if is_routine_or_take and ctx_entity["sg_subsession"]:
                    template_info = CONTEXT_TEMPLATE[ctx_entity["type"] + "_subsession"]

                if not item.properties.get("work_template"):
                    item.properties["work_template"] = publisher.engine.get_template_by_name(template_info
                                                                                             ["work_template"])
                if not item.properties.get("publish_template"):
                    item.properties["publish_template"] = publisher.engine.get_template_by_name(template_info
                                                                                                ["publish_template"])


def _session_path():
    """
    Return the path to the current session
    :return:
    """
    path = mb_app.FBXFileName
    if isinstance(path, unicode):
        path = path.encode("utf-8")

    return path


def _save_session(path):
    """
    Save the current session to the supplied path.
    """

    mb_app.FileSave(path)


def _save_as_session():
    """
    Save the current session to the supplied path.
    """

    # Save the file using a dialog box.
    saveDialog = FBFilePopup()
    saveDialog.Style = FBFilePopupStyle.kFBFilePopupSave
    saveDialog.Filter = '*'

    saveDialog.Caption = 'Save As'
    saveDialog.FileName = _session_path()

    if saveDialog.Execute():
        mb_app.FileSave(saveDialog.FullFilename)


def _get_save_as_action(context=None):
    """
    Simple helper for returning a log action dict for saving the session

    :param context: The context in which we want the save dialog to be
    """
    engine = sgtk.platform.current_engine()

    if context and engine.context != context:
        _change_context(context)
        engine = sgtk.platform.current_engine()

    # default save callback
    callback = lambda: _save_as_session()

    # if workfiles2 is configured, use that for file save
    if "tk-multi-workfiles2" in engine.apps:
        app = engine.apps["tk-multi-workfiles2"]
        if hasattr(app, "show_file_save_dlg"):
            callback = app.show_file_save_dlg

    return {
        "action_button": {
            "label": "Save As...",
            "tooltip": "Save the current Motion Builder session to a different file name",
            "callback": callback
        }
    }


def _change_context(ctx):
    """
    Set context to the new context.

    :param ctx: The :class:`sgtk.Context` to change to.

    :raises TankError: Raised when the context change fails.
    """
    engine = sgtk.platform.current_engine()
    engine.log_debug("Changing context from %s to %s" % (engine.context, ctx))

    try:
        sgtk.platform.change_context(ctx)
    except Exception, e:
        engine.log_exception("Context change failed!")
        raise TankError("Failed to change work area - %s" % e)