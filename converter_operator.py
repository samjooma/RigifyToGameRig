from doctest import FAIL_FAST
from email import header
from unittest import TestSuite
import bpy
from bpy.app.handlers import persistent
from . import converter
from . import misc
from difflib import SequenceMatcher

@persistent
def depsgraph_update_handler(scene):
    # Add selected rigs to addon properties.
    bpy.context.scene.rigify_converter.rigs_to_convert.clear()
    for rig_object in (x for x in bpy.context.selected_objects if misc.is_valid_rig(x) and misc.is_rigify_rig(x)):
        rig_property = bpy.context.scene.rigify_converter.rigs_to_convert.add()
        rig_property.rig_object = rig_object

class UIActionList(bpy.types.UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {"DEFAULT", "COMPACT", "GRID"}:
            row = layout.row(align=True)
            row.alignment = "LEFT"
            row.prop(data=item, property="include_in_export", icon_only=True)
            row.label(text=item.name, icon_value=icon)

#
# Property classes.
#

class ActionSelectionProperty(bpy.types.PropertyGroup):
    name: bpy.props.StringProperty()
    include_in_export: bpy.props.BoolProperty(default=False)

class RigObjectProperty(bpy.types.PropertyGroup):
    rig_object: bpy.props.PointerProperty(type = bpy.types.Object)

class RigifyConverterProperties(bpy.types.PropertyGroup):
    rigs_to_convert: bpy.props.CollectionProperty(type = RigObjectProperty)
    add_as_root_bone: bpy.props.StringProperty(
        default="root",
        name="Add as root bone",
        description="Bone that will be added to the converted rig as the root bone"
    )
    actions: bpy.props.CollectionProperty(type=ActionSelectionProperty)
    active_action_index: bpy.props.IntProperty()
    overwrite_existing_objects: bpy.props.EnumProperty(
        name="Overwrite",
        items=(
            ("NONE", "None", ""),
            ("OBJECTS", "Objects", ""),
            ("ACTIONS", "Actions", ""),
            ("BOTH", "Objects and actions", ""),
        ),
        default="BOTH",
    )

#
# Operators.
#

class RigifyConverterOperator(bpy.types.Operator):
    bl_idname = "object.rigify_converter"
    bl_label = "Convert rigify armature"
    bl_description = "Convert selected rigify armature, its mesh, and all actions in scene"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        if len(context.scene.rigify_converter.rigs_to_convert) <= 0: return False
        for rig_object in (x.rig_object for x in context.scene.rigify_converter.rigs_to_convert):
            if not misc.is_valid_rig(rig_object): return False
            if not misc.is_rigify_rig(rig_object): return False
        return True

    def execute(self, context):
        properties = context.scene.rigify_converter
        for rig_object in (x.rig_object for x in properties.rigs_to_convert):
            child_meshes = [x for x in rig_object.children if x.type == "MESH"]
            if len(child_meshes) > 1:
                self.report({"ERROR"}, "Can't convert a rig that is the parent of multiple meshes.")
                return {"CANCELLED"}
            if len(child_meshes) < 1:
                self.report({"ERROR"}, "Can't convert a rig that is not the parent of any mesh.")
                return {"CANCELLED"}
            actions = [bpy.data.actions[x.name] for x in properties.actions if x.include_in_export]

            overwrite_objects = properties.overwrite_existing_objects in {"OBJECTS", "BOTH"}
            overwrite_actions = properties.overwrite_existing_objects in {"ACTIONS", "BOTH"}
            converter.convert_rigify_rig(
                rig_object,
                child_meshes[0],
                actions,
                properties.add_as_root_bone,
                overwrite_objects,
                overwrite_actions,
            )
        return {"FINISHED"}

    def invoke(self, context, event):
        properties = bpy.context.scene.rigify_converter
        properties.active_action_index = 0

        # Remove action properties for actions that don't exist anymore.
        pending_removal = []
        for action_property in properties.actions:
            if action_property.name not in [x.name for x in bpy.data.actions]:
                pending_removal.append(action_property.name)
        for property_name_to_remove in pending_removal:
            i = next((i for i, x in enumerate(properties.actions) if x.name == property_name_to_remove))
            properties.actions.remove(i)

        # Add missing actions as new properties.
        for action in bpy.data.actions:
            if action.name not in [x.name for x in properties.actions]:
                new_action_property = properties.actions.add()
                new_action_property.name = action.name

        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        properties = bpy.context.scene.rigify_converter
        layout.prop(data=properties, property="add_as_root_bone")
        layout.template_list(
            listtype_name="UIActionList",
            list_id="",
            dataptr=properties,
            propname="actions",
            active_dataptr=properties,
            active_propname="active_action_index",
            type="DEFAULT",
        )
        layout.prop(data=properties, property="overwrite_existing_objects")

#
# Registration.
#

def menu_func(self, context):
    self.layout.operator(RigifyConverterOperator.bl_idname, text=RigifyConverterOperator.bl_label)

classes = (
    ActionSelectionProperty,
    RigObjectProperty,
    RigifyConverterProperties,
    RigifyConverterOperator,
)

def register():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.rigify_converter = bpy.props.PointerProperty(type = RigifyConverterProperties)
    bpy.app.handlers.depsgraph_update_post.append(depsgraph_update_handler)
    bpy.types.VIEW3D_MT_object_convert.append(menu_func)
    
def unregister():
    for c in classes:
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.rigify_converter
    bpy.app.handlers.depsgraph_update_post.remove(depsgraph_update_handler)
    bpy.types.VIEW3D_MT_object_convert.remove(menu_func)
    